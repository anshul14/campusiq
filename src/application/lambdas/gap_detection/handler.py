# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Gap Detection Lambda

Triggered by EventBridge QuizCompleted event.
Translates quiz concept_scores into gap_severity per concept.

Flow:
    1. Read concept_scores from QuizCompleted event
    2. Look up existing gap records for each concept in DynamoDB
    3. Calculate new gap_severity using weighted average of historical scores
    4. Write updated KnowledgeGap records to DynamoDB

Trigger:    EventBridge — source: campusiq.quiz, detail-type: QuizCompleted
Memory:     512 MB
Timeout:    30 seconds
"""

import os
import logging

import boto3

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger(service="gap-detection")

dynamodb          = boto3.resource("dynamodb")
DYNAMODB_TABLE    = os.getenv("DYNAMODB_TABLE_NAME", "")
BEDROCK_MODEL_ID  = os.getenv("BEDROCK_MODEL_ID_SONNET", "anthropic.claude-3-5-sonnet-20241022-v2:0")


@logger.inject_lambda_context
def handler(event: dict, context: LambdaContext) -> None:
    """
    Process QuizCompleted event and update student gap records.

    Args:
        event:   EventBridge event with detail containing concept_scores
        context: Lambda context object

    Event shape:
        {
            "source": "campusiq.quiz",
            "detail-type": "QuizCompleted",
            "detail": {
                "student_id":     "cognito-sub-abc",
                "course_id":      "phys101",
                "module_id":      "week3-newtons-laws",
                "concept_scores": { "friction": 0.4, "inertia": 0.9 }
            }
        }
    """
    detail         = event["detail"]
    student_id     = detail["student_id"]
    concept_scores = detail["concept_scores"]

    logger.info("Processing gap detection", extra={
        "student_id": student_id,
        "concepts":   list(concept_scores.keys()),
    })

    # TODO: Phase 3 — implement gap severity calculation
    # 1. For each concept in concept_scores:
    #    a. Query DynamoDB for existing KnowledgeGap record
    #       PK = STUDENT#{student_id}, SK = GAP#{concept_id}
    #    b. Get historical scores list from the record
    #    c. Append new score from concept_scores
    #    d. Calculate gap_severity = 1.0 - weighted_average(historical_scores)
    #       (recent attempts weighted more than older ones)
    #    e. Write updated gap record back to DynamoDB
    #       — update gap_severity
    #       — update GSI2_SK = zero-padded severity string
    #       — update GSI3_PK = COURSE#{course_id}

    logger.info("Gap detection complete", extra={
        "student_id":         student_id,
        "concepts_processed": len(concept_scores),
    })