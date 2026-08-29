# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
EventBridge emission service — src/application/services/events.py

Separate from dynamodb.py — putting events isn't a DynamoDB concern.

Reads EVENT_BUS_NAME directly via os.environ[...], not os.getenv(...,
"some-fallback-name"). A hardcoded fallback bus name risks silently
writing events to a bus that doesn't exist, with no error until
something downstream notices events are missing. A missing env var
should fail loudly and immediately instead.
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
    bus_name = os.environ["EVENT_BUS_NAME"]

    response = eventbridge_client.put_events(
        Entries=[{
            "Source": "campusiq.courses",
            "DetailType": "ModulePublished",
            "Detail": json.dumps({"course_id": course_id, "module_id": module_id}),
            "EventBusName": bus_name,
        }]
    )

    # put_events can fail per-entry rather than raising an exception.
    # With only one entry here, "partial" failure means total failure,
    # so raise rather than log-and-continue.
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
