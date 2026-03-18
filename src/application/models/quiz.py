# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.application.models import dynamodb_keys as keys


class QuestionType(str, Enum):
    SINGLE = "SINGLE"  # one correct answer — radio button
    MULTIPLE = "MULTIPLE"  # multiple correct answers — checkboxes


class QuizStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


@dataclass
class QuizOption:
    """A single answer option within a quiz question."""
    id: str  # a | b | c | d
    text: str


@dataclass
class QuizQuestion:
    """
    A single question within a quiz.
    The concept field is used by the Knowledge Gap Agent
    to map quiz performance back to specific concepts.
    """
    id: str
    type: QuestionType
    text: str
    options: list[QuizOption]
    correct_ids: list[str]  # list of option IDs that are correct
    explanation: str  # shown to student after submission
    concept: str  # concept being tested — e.g. "friction"
    difficulty: str  # easy | medium | hard


@dataclass
class QuizDefinition:
    """
    The quiz template created by a teacher (or AI-generated
    and edited by a teacher). Contains all questions and settings.
    Students read this when taking the quiz.

    DynamoDB:
        PK = QUIZ#{quiz_id}
        SK = METADATA
    """
    quiz_id: str
    course_id: str
    module_id: str
    title: str
    questions: list[QuizQuestion]
    status: QuizStatus
    created_by: str  # TEACHER#{cognitoSub}
    created_at: str  # ISO 8601
    max_attempts: int = 2
    passing_score_pct: int = 60
    randomise_order: bool = True
    time_limit_seconds: Optional[int] = None  # null = no time limit

    @property
    def pk(self) -> str:
        return keys.quiz_pk(self.quiz_id)

    @property
    def sk(self) -> str:
        return keys.metadata_sk()


@dataclass
class QuizAnswer:
    """A student's answer to a single question."""
    question_id: str
    selected_ids: list[str]  # which options the student selected
    correct: bool  # was the answer correct
    concept: str  # concept from the question — copied here for Gap Agent


@dataclass
class QuizResult:
    """
    A student's completed quiz attempt.
    Written to DynamoDB when a student submits a quiz.
    Triggers the Cognitive Loop via DynamoDB Streams.

    The attempt_id uses a timestamp prefix so that SK sorts
    chronologically — the latest attempt is always last.
    Query with ScanIndexForward=False + Limit=1 for latest attempt.

    DynamoDB:
        PK = STUDENT#{cognito_sub}
        SK = RESULT#{course_id}#{module_id}#{attempt_id}
             where attempt_id = {YYYYMMDDTHHMMSS}-{uuid}

    GSI1 (course-scoped — teacher sees all student results):
        GSI1_PK = COURSE#{course_id}
        GSI1_SK = RESULT#{cognito_sub}#{module_id}#{attempt_id}
    """
    cognito_sub: str
    course_id: str
    module_id: str
    attempt_id: str  # {YYYYMMDDTHHMMSS}-{uuid}
    quiz_id: str
    score_pct: int  # 0 to 100
    passed: bool
    submitted_at: str  # ISO 8601
    time_taken_seconds: int
    answers: list[QuizAnswer]

    # concept_scores maps concept name → score (0.0 to 1.0)
    # Built from answers — used directly by the Gap Detection Agent
    # Example: {"friction": 0.4, "inertia": 0.9, "acceleration": 0.7}
    concept_scores: dict[str, float] = field(default_factory=dict)

    # TTL — quiz results auto-deleted after 2 years (configurable)
    ttl: Optional[int] = None  # Unix timestamp

    @property
    def pk(self) -> str:
        return keys.student_pk(self.cognito_sub)

    @property
    def sk(self) -> str:
        return keys.result_sk(self.course_id, self.module_id, self.attempt_id)

    @property
    def gsi1_pk(self) -> str:
        return keys.course_pk(self.course_id)

    @property
    def gsi1_sk(self) -> str:
        return keys.gsi1_result_sk(self.cognito_sub, self.module_id, self.attempt_id)
