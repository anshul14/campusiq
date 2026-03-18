# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.application.models import dynamodb_keys as keys


class ProgressStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class ModuleProgress:
    """
    Tracks a student's progress through a single module.
    Written when a student starts a module, updated as they
    progress, and marked complete when the completion threshold
    is reached (85% video watched, last page of PDF/doc reached).

    DynamoDB:
        PK = STUDENT#{cognito_sub}
        SK = PROGRESS#{course_id}#{module_id}

    GSI1 (course-scoped — enables teacher dashboard):
        GSI1_PK = COURSE#{course_id}
        GSI1_SK = PROGRESS#{cognito_sub}#{module_id}
    """
    cognito_sub: str
    course_id: str
    module_id: str
    completion_pct: int  # 0 to 100
    status: ProgressStatus
    started_at: str  # ISO 8601
    time_spent_seconds: int = 0
    tutor_interactions_count: int = 0
    completed_at: Optional[str] = None  # ISO 8601 — set on completion

    @property
    def pk(self) -> str:
        return keys.student_pk(self.cognito_sub)

    @property
    def sk(self) -> str:
        return keys.progress_sk(self.course_id, self.module_id)

    @property
    def gsi1_pk(self) -> str:
        return keys.gsi1_course_pk(self.course_id)

    @property
    def gsi1_sk(self) -> str:
        return keys.gsi1_progress_sk(self.cognito_sub, self.module_id)
