# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Stream Processor Lambda — Entry Point

Triggered by the CampusIQ DynamoDB table's Stream (NEW_AND_OLD_IMAGES).
Translates raw stream records into EventBridge events that drive the
Cognitive Learning Loop. Contains no business logic — its only job is
pattern-matching on SK prefix and forwarding a normalised event.

  RESULT# write  -> QuizCompleted   -> Gap Detection Agent
  GAP# write, severity > 0.7 -> GapDetected -> Recommendation Agent

Trigger:    DynamoDB Streams (TRIM_HORIZON, batch_size=10, bisect_on_error)
Memory:     256 MB
Timeout:    30 seconds

TARGET PATH IN REPO: src/application/lambdas/stream_processor/handler.py
(matches ComputeStack._event_lambda's handler convention: {entry}/handler.handler —
this is a plain Lambda handler, not FastAPI/Mangum, since this Lambda is
event-driven, not HTTP.)

REQUIRED CDK CHANGE (compute_stack.py, _build_event_driven_lambdas):
The existing DynamoEventSource block must add report_batch_item_failures=True,
or this handler's batchItemFailures return value is silently ignored by the
poller and failed records are never retried:

    self.stream_processor_lambda.add_event_source(
        event_sources.DynamoEventSource(
            self.table,
            starting_position=lambda_.StartingPosition.TRIM_HORIZON,
            batch_size=10,
            bisect_batch_on_error=True,
            retry_attempts=3,
            report_batch_item_failures=True,   # <-- add this line
        )
    )

NOTE ON GSI NAMING: this file does not read or write any GSI directly —
it only reads NewImage attributes off the stream record and republishes
an EventBridge event. GSI names (GapSeverityIndex, AtRiskIndex) are only
relevant to the Gap Detection Agent that consumes QuizCompleted, and to
whichever Lambda queries the GSIs later.
"""

import json
import logging
import os
from decimal import Decimal
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

eb_client = boto3.client("events")

EVENT_BUS_NAME = os.environ["EVENT_BUS_NAME"]  # e.g. "campusiq-vnit-dev-events"
GAP_SEVERITY_AT_RISK_THRESHOLD = Decimal("0.7")


def handler(event: dict, context: Any) -> dict:
    """
    Entry point invoked by the Lambda DynamoDB Streams event source mapping.

    event["Records"] is a list of stream records. Each record's dynamodb.NewImage
    is in DynamoDB's low-level JSON format ({"S": "..."}, {"N": "..."}, {"M": {...}}),
    not a plain Python dict — values must be unmarshalled before use.

    RETURN VALUE — Partial Batch Item Failure Reporting:
    This handler implements the DynamoDB Streams "reportBatchItemFailures" protocol.
    Returning {"batchItemFailures": [{"itemIdentifier": "<sequenceNumber>"}]} tells
    the poller to retry only the failed records (and everything after the FIRST
    failure in the batch — DynamoDB Streams retries are cursor-based, not per-record
    replay of arbitrary items) instead of silently discarding them or blindly
    retrying/discarding the whole batch.

    This ONLY works if the DynamoEventSource in CDK has
    report_batch_item_failures=True set. Without that flag, returning
    batchItemFailures here has no effect — the poller ignores it.

    Correctness matters here specifically because a dropped RESULT# record means
    a QuizCompleted event never fires, which means Gap Detection never runs for
    that submission — the entire Cognitive Loop silently fails to start, with no
    error surfaced anywhere else in the system.
    """
    processed = 0
    skipped = 0
    batch_item_failures: list[dict] = []

    for record in event.get("Records", []):
        sequence_number = record.get("dynamodb", {}).get("SequenceNumber")

        try:
            if record.get("eventName") not in ("INSERT", "MODIFY"):
                skipped += 1
                continue

            new_image_raw = record.get("dynamodb", {}).get("NewImage")
            if not new_image_raw:
                # REMOVE events or malformed records with no NewImage — nothing to act on.
                skipped += 1
                continue

            new_image = _unmarshall(new_image_raw)
            sk = new_image.get("SK", "")

            if sk.startswith("RESULT#"):
                _fire_quiz_completed(new_image)
                processed += 1
            elif sk.startswith("GAP#"):
                severity = new_image.get("gap_severity")
                if severity is not None and Decimal(str(severity)) > GAP_SEVERITY_AT_RISK_THRESHOLD:
                    _fire_gap_detected(new_image)
                    processed += 1
                else:
                    skipped += 1
            else:
                # Not a record type this loop cares about (e.g. PROFILE, ENROL#, PROGRESS#).
                skipped += 1

        except Exception:
            logger.exception(
                "Failed to process stream record — will be retried by the poller",
                extra={
                    "event_id": record.get("eventID"),
                    "event_name": record.get("eventName"),
                    "sequence_number": sequence_number,
                },
            )
            if sequence_number is not None:
                batch_item_failures.append({"itemIdentifier": sequence_number})
            else:
                # Should not happen in practice — every real stream record carries
                # a SequenceNumber. Logged loudly because if it does happen, this
                # record silently falls through the partial-failure protocol and
                # is treated as succeeded even though it wasn't.
                logger.error(
                    "Stream record missing SequenceNumber — cannot report as a "
                    "batch item failure, this record will NOT be retried",
                    extra={"event_id": record.get("eventID")},
                )

    logger.info(
        "Stream batch processed",
        extra={
            "processed": processed,
            "skipped": skipped,
            "failed": len(batch_item_failures),
            "total": len(event.get("Records", [])),
        },
    )

    return {"batchItemFailures": batch_item_failures}


def _unmarshall(raw_image: dict) -> dict:
    """
    Convert a DynamoDB Streams NewImage (low-level {"S": ...} / {"N": ...} / {"M": ...}
    format) into a plain Python dict. boto3's TypeDeserializer expects this exact shape,
    so we use it rather than hand-rolling the conversion.
    """
    from boto3.dynamodb.types import TypeDeserializer

    deserializer = TypeDeserializer()
    return {k: deserializer.deserialize(v) for k, v in raw_image.items()}


def _fire_quiz_completed(image: dict) -> None:
    """
    Fired when a QuizResult record (SK begins with RESULT#) is written.
    Carries concept_scores forward — this is the signal the Gap Detection
    Agent needs to update the student's per-concept weakness model.
    """
    student_id = image["PK"].replace("STUDENT#", "")
    concept_scores = image.get("concept_scores", {})

    detail = {
        "student_id": student_id,
        "course_id": image["course_id"],
        "module_id": image["module_id"],
        "attempt_id": image.get("SK", "").split("#")[-1],
        # Decimal is not JSON-serialisable — cast to float for the EventBridge payload.
        "concept_scores": {concept: float(score) for concept, score in concept_scores.items()},
    }

    _put_event(source="campusiq.quiz", detail_type="QuizCompleted", detail=detail)


def _fire_gap_detected(image: dict) -> None:
    """
    Fired when a KnowledgeGap record (SK begins with GAP#) is written or updated
    with gap_severity exceeding the at-risk threshold (0.7). Triggers the
    Recommendation Agent (and, at higher severity, Content Adaptation).
    """
    student_id = image["PK"].replace("STUDENT#", "")
    concept_id = image["SK"].replace("GAP#", "")

    detail = {
        "student_id": student_id,
        "concept_id": concept_id,
        "gap_severity": float(image["gap_severity"]),
        "course_id": image.get("course_id"),
    }

    _put_event(source="campusiq.gap", detail_type="GapDetected", detail=detail)


def _put_event(source: str, detail_type: str, detail: dict) -> None:
    response = eb_client.put_events(
        Entries=[
            {
                "Source": source,
                "DetailType": detail_type,
                "Detail": json.dumps(detail),
                "EventBusName": EVENT_BUS_NAME,
            }
        ]
    )

    if response.get("FailedEntryCount", 0) > 0:
        # put_events partially fails silently (HTTP 200 with per-entry errors) —
        # must check FailedEntryCount explicitly or failures go unnoticed.
        logger.error(
            "EventBridge put_events partial failure",
            extra={"detail_type": detail_type, "entries": response.get("Entries")},
        )
        raise RuntimeError(f"Failed to publish {detail_type} event to EventBridge")