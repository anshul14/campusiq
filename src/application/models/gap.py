# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.application.models import dynamodb_keys as keys


@dataclass
class KnowledgeGap:
    """
    This class is to track a student's weakness in a specific concept.
    After every quiz submission the Gap Detection Agent will write and update this file.


    gap_severity is the inverse of mastery:
        0.0 = fully mastered
        1.0 = completely unknown
    Calculated as: 1 - weighted_average(concept_scores across attempts)

    At-risk threshold: gap_severity > 0.7
    Faculty alert fires when this threshold is crossed.

    DynamoDB:
        PK = STUDENT#{cognito_sub}
        SK = GAP#{concept_id}

    GSI2 (gap severity sort — Orchestrator context enrichment):
        GSI2_PK = STUDENT#{cognito_sub}
        GSI2_SK = zero-padded severity string e.g. "0.600"
        Query ScanIndexForward=False to get worst gaps first.

    GSI3 (at-risk detection — faculty dashboard alerts):
        GSI3_PK = COURSE#{course_id}
        GSI3_SK = zero-padded severity string
        Query GSI3_SK >= "0.700" to find at-risk students.
    """
    cognito_sub: str
    concept_id: str  # e.g. "friction" — matches question.concept
    concept_name: str  # human-readable e.g. "Friction and Surface Forces"
    course_id: str
    gap_severity: float  # 0.0 to 1.0
    last_quiz_score: float  # most recent concept score from quiz
    detection_count: int  # how many times this gap has been flagged
    first_detected_at: str  # ISO 8601
    last_updated_at: str  # ISO 8601

    @property
    def pk(self) -> str:
        return keys.student_pk(self.cognito_sub)

    @property
    def sk(self) -> str:
        return keys.gap_sk(self.concept_id)

    @property
    def gsi2_pk(self) -> str:
        return keys.student_pk(self.cognito_sub)

    @property
    def gsi2_sk(self) -> str:
        # Zero-padded to 5 chars so string sort = numeric sort
        return f"{self.gap_severity:.3f}"

    @property
    def gsi3_pk(self) -> str:
        return keys.course_pk(self.course_id)

    @property
    def gsi3_sk(self) -> str:
        return f"{self.gap_severity:.3f}"


@dataclass
class LearningPath:
    """
    The currently active personalised learning path for a student in a course.
    Written by the Recommendation Agent after querying Amazon Personalize.
    Read by the Orchestrator to enrich context before every agent call.

    Expires after 24 hours (TTL) — forces Personalize re-recommendation
    on next student interaction after a period of inactivity.

    DynamoDB:
        PK = STUDENT#{cognito_sub}
        SK = PATH#{course_id}
    """
    cognito_sub: str
    course_id: str
    recommended_modules: list[str]  # ordered list of module IDs
    current_module_id: str
    rationale: str  # why this path — from Personalize/agent
    generated_at: str  # ISO 8601
    expires_at: str  # ISO 8601 — 24 hours from generated_at
    ttl: Optional[int] = None  # Unix timestamp for DynamoDB TTL

    @property
    def pk(self) -> str:
        return keys.student_pk(self.cognito_sub)

    @property
    def sk(self) -> str:
        return keys.path_sk(self.course_id)
