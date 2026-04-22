# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Stream Processor Lambda

Triggered by DynamoDB Streams on every write to the main table.
Reads each record and fires the appropriate EventBridge event.

Rules:
    - SK starts with RESULT# → fire EventBridge: QuizCompleted
    - SK starts with GAP# AND gap_severity > threshold → fire EventBridge: GapDetected
    - All other writes → ignored

Trigger:    DynamoDB Streams
Memory:     256 MB
Timeout:    60 seconds
"""

import os
import json
import logging
import boto3

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger(service="stream-processor")

eventbridge = boto3.client("events")

GAP_SEVERITY_THRESHOLD = float(os.getenv("GAP_SEVERITY_THRESHOLD", "0.7"))
EVENTBRIDGE_BUS_NAME   = os.getenv("EVENTBRIDGE_BUS_NAME", "campusiq-event-bus")


@logger.inject_lambda_context
def handler(event: dict, context: LambdaContext) -> None:
    """
    Process DynamoDB Stream records and fire EventBridge events.

    Args:
        event:   DynamoDB Streams event containing list of records
        context: Lambda context object
    """
    for record in event.get("Records", []):
        if record["eventName"] not in ("INSERT", "MODIFY"):
            continue

        new_image = record["dynamodb"].get("NewImage", {})
        sk = new_image.get("SK", {}).get("S", "")

        if sk.startswith("RESULT#"):
            _fire_quiz_completed(new_image)

        elif sk.startswith("GAP#"):
            severity = float(new_image.get("gap_severity", {}).get("N", "0"))
            if severity >= GAP_SEVERITY_THRESHOLD:
                _fire_gap_detected(new_image, severity)


def _fire_quiz_completed(image: dict) -> None:
    """
    Fire EventBridge QuizCompleted event from a QuizResult DynamoDB record.

    Args:
        image: DynamoDB NewImage from the stream record
    """
    # TODO: Phase 3 — extract concept_scores from DynamoDB image format
    # DynamoDB Streams returns typed attributes e.g. {"S": "value"} {"N": "0.4"}
    # concept_scores is stored as a Map type {"M": {"friction": {"N": "0.4"}}}

    detail = {
        "student_id":     image.get("PK", {}).get("S", "").replace("STUDENT#", ""),
        "course_id":      image.get("course_id", {}).get("S", ""),
        "module_id":      image.get("module_id", {}).get("S", ""),
        "concept_scores": {},  # TODO: deserialise from DynamoDB Map format
    }

    eventbridge.put_events(Entries=[{
        "Source":       "campusiq.quiz",
        "DetailType":   "QuizCompleted",
        "Detail":       json.dumps(detail),
        "EventBusName": EVENTBRIDGE_BUS_NAME,
    }])

    logger.info("Fired QuizCompleted event", extra={"student_id": detail["student_id"]})


def _fire_gap_detected(image: dict, severity: float) -> None:
    """
    Fire EventBridge GapDetected event from a KnowledgeGap DynamoDB record.

    Args:
        image:    DynamoDB NewImage from the stream record
        severity: gap_severity value already extracted from image
    """
    detail = {
        "student_id":   image.get("PK", {}).get("S", "").replace("STUDENT#", ""),
        "concept_id":   image.get("SK", {}).get("S", "").replace("GAP#", ""),
        "gap_severity": severity,
        "course_id":    image.get("course_id", {}).get("S", ""),
    }

    eventbridge.put_events(Entries=[{
        "Source":       "campusiq.gap",
        "DetailType":   "GapDetected",
        "Detail":       json.dumps(detail),
        "EventBusName": EVENTBRIDGE_BUS_NAME,
    }])

    logger.info("Fired GapDetected event", extra={
        "student_id": detail["student_id"],
        "concept_id": detail["concept_id"],
        "severity":   severity,
    })