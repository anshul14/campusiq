# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
EventBridge emission service — src/application/services/events.py

New file, not an addition to dynamodb.py — putting events isn't a
DynamoDB concern, bundling it in there would be the same kind of
category mixing already avoided elsewhere in this codebase.

Reads EVENTBRIDGE_BUS_NAME directly via os.environ[...], not
os.getenv(..., "some-fallback-name") — a hardcoded fallback bus name is
exactly the bug already hit once on this project (Stream Processor's
EVENTBRIDGE_BUS_NAME typo + hardcoded fallback pointing at a bus that
didn't exist, root-caused via a confusing AccessDeniedException). A
missing env var should fail loudly and immediately, not silently degrade
to writing at the wrong bus.
"""

from __future__ import annotations

import json
import os

import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="events-service")
eventbridge_client = boto3.client("events")


class EventEmitFailedError(Exception):
    """Raised when EventBridge reports a failed entry in put_events().
    Distinct from a boto3/network exception, which propagates as itself."""
    pass


def emit_module_published(course_id: str, module_id: str) -> None:
    """
    Emits ModulePublished to EventBridge — the trigger the ingestion
    Lambda subscribes to for Path A (see ingestion Lambda handler.py).
    Called by the Publish handler AFTER its own synchronous DynamoDB
    write already succeeded and returned — this is the async half, not
    on the request's critical path.
    """
    bus_name = os.environ["EVENTBRIDGE_BUS_NAME"]

    response = eventbridge_client.put_events(
        Entries=[{
            "Source": "campusiq.courses",
            "DetailType": "ModulePublished",
            "Detail": json.dumps({"course_id": course_id, "module_id": module_id}),
            "EventBusName": bus_name,
        }]
    )

    # put_events can partially fail per-entry rather than raise — same
    # shape as Stream Processor's batchItemFailures handling (ADR-017).
    # With only one entry here, "partial" means "failed", so raise rather
    # than log-and-continue.
    if response.get("FailedEntryCount", 0) > 0:
        failure = response["Entries"][0]
        logger.error("EventBridge put_events failed", extra={
            "course_id": course_id, "module_id": module_id,
            "error_code": failure.get("ErrorCode"), "error_message": failure.get("ErrorMessage"),
        })
        raise EventEmitFailedError(
            f"Failed to emit ModulePublished for course_id={course_id!r} "
            f"module_id={module_id!r}: {failure.get('ErrorMessage')}"
        )
