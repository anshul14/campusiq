# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Content Adaptation Lambda

Triggered by EventBridge GapDetected event when gap_severity > 0.85.
Rewrites module Markdown content at a lower difficulty level using
Claude 3 Haiku via Bedrock InvokeModel.

Scope:
    Only works on Markdown content — PDF and video cannot be adapted.
    The adapted variant is saved alongside the original in S3.
    The module record is updated to point to the adapted variant.

Trigger:    EventBridge — source: campusiq.gap, detail-type: GapDetected
Memory:     512 MB
Timeout:    30 seconds
"""

import os
import logging

import boto3

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger(service="content-adaptation")

dynamodb              = boto3.resource("dynamodb")
s3                    = boto3.client("s3")
bedrock               = boto3.client("bedrock-runtime")
DYNAMODB_TABLE        = os.getenv("DYNAMODB_TABLE_NAME", "")
S3_CONTENT_BUCKET     = os.getenv("S3_CONTENT_BUCKET", "")
BEDROCK_MODEL_ID      = os.getenv("BEDROCK_MODEL_ID_HAIKU", "anthropic.claude-3-haiku-20240307-v1:0")
ADAPTATION_THRESHOLD  = float(os.getenv("ADAPTATION_SEVERITY_THRESHOLD", "0.85"))


@logger.inject_lambda_context
def handler(event: dict, context: LambdaContext) -> None:
    """
    Process GapDetected event and adapt module content if severity > 0.85.

    Args:
        event:   EventBridge event with detail containing gap info
        context: Lambda context object
    """
    detail        = event["detail"]
    student_id    = detail["student_id"]
    gap_severity  = float(detail["gap_severity"])
    course_id     = detail["course_id"]

    # Only adapt if severity exceeds the higher threshold
    if gap_severity <= ADAPTATION_THRESHOLD:
        logger.info("Severity below adaptation threshold — skipping", extra={
            "gap_severity": gap_severity,
            "threshold":    ADAPTATION_THRESHOLD,
        })
        return

    logger.info("Starting content adaptation", extra={
        "student_id":  student_id,
        "gap_severity": gap_severity,
    })

    # TODO: Phase 3 — implement content adaptation
    # 1. Look up student's current module from LearningPath in DynamoDB
    # 2. Read module record — check content_type
    #    If content_type != MARKDOWN → log and return (cannot adapt PDF/video)
    # 3. Read original content.md from S3
    # 4. Call Bedrock InvokeModel (Claude 3 Haiku)
    #    Prompt: rewrite at lower difficulty for student with gap in {concept}
    # 5. Save adapted content to S3 as content_adapted_{student_id}.md
    # 6. Update module record in DynamoDB to point to adapted variant

    logger.info("Content adaptation complete", extra={
        "student_id": student_id,
        "course_id":  course_id,
    })