# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""
Recommendation Lambda

Triggered by EventBridge GapDetected event (gap_severity > 0.7).
Reads student gap profile and generates personalised learning path
via Amazon Personalize.

Flow:
    1. Read student gap profile from DynamoDB via GSI2
    2. Call Amazon Personalize get_recommendations with gap context
    3. Map Personalize results to CampusIQ module IDs
    4. Write updated LearningPath to DynamoDB with 24hr TTL

Trigger:    EventBridge — source: campusiq.gap, detail-type: GapDetected
Memory:     512 MB
Timeout:    30 seconds
"""

import os
import logging

import boto3

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger(service="recommendation")

dynamodb               = boto3.resource("dynamodb")
personalize_runtime    = boto3.client("personalize-runtime")
DYNAMODB_TABLE         = os.getenv("DYNAMODB_TABLE_NAME", "")
PERSONALIZE_CAMPAIGN   = os.getenv("PERSONALIZE_CAMPAIGN_ARN", "")
PERSONALIZE_TRACKER    = os.getenv("PERSONALIZE_EVENT_TRACKER_ID", "")


@logger.inject_lambda_context
def handler(event: dict, context: LambdaContext) -> None:
    """
    Process GapDetected event and update student learning path.

    Args:
        event:   EventBridge event with detail containing gap info
        context: Lambda context object

    Event shape:
        {
            "source": "campusiq.gap",
            "detail-type": "GapDetected",
            "detail": {
                "student_id":   "cognito-sub-abc",
                "concept_id":   "friction",
                "gap_severity": 0.8,
                "course_id":    "phys101"
            }
        }
    """
    detail     = event["detail"]
    student_id = detail["student_id"]
    course_id  = detail["course_id"]

    logger.info("Processing recommendation", extra={
        "student_id": student_id,
        "course_id":  course_id,
    })

    # TODO: Phase 3 — implement learning path recommendation
    # 1. Query DynamoDB GSI2 for student's top gaps
    #    PK = STUDENT#{student_id}, ScanIndexForward=False, Limit=5
    # 2. Call Personalize get_recommendations
    #    userId = student_id
    #    context = { "gap_concepts": "friction|newtons_third", "gap_severity": "0.8" }
    # 3. Map Personalize item IDs to CampusIQ module IDs
    # 4. Write LearningPath to DynamoDB
    #    PK = STUDENT#{student_id}, SK = PATH#{course_id}
    #    TTL = now + 24 hours

    logger.info("Recommendation complete", extra={
        "student_id": student_id,
        "course_id":  course_id,
    })