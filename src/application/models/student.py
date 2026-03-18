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

from src.application.models import dynamodb_keys as keys


class EnrolmentStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    DROPPED = "dropped"


class TeacherRole(str, Enum):
    LEAD = "lead"
    ASSISTANT = "assistant"


@dataclass
class StudentProfile:
    """
    Represents a student's identity and deployment-level attributes.
    Cognito is the authoritative user store — this record holds
    learning-specific attributes only.

    DynamoDB:
        PK = STUDENT#{cognito_sub}
        SK = PROFILE
    """
    cognito_sub: str
    student_id: str  # institution-assigned student number
    email: str
    name: str
    domain: str  # university | k12 | corporate
    grade: str  # sophomore | Grade 5 | etc.
    idp_provider: str  # EntraID | Google | SAML
    enrollment_status: str  # active | suspended
    created_at: str  # ISO 8601
    last_active_at: str  # ISO 8601

    @property
    def pk(self) -> str:
        return keys.student_pk(self.cognito_sub)

    @property
    def sk(self) -> str:
        return keys.profile_sk()


@dataclass
class Enrolment:
    """
    Links a student to a course.
    Written when a student is enrolled — either via CMS sync
    (Google Classroom) or directly by an admin.

    DynamoDB:
        PK = STUDENT#{cognito_sub}
        SK = ENROL#{course_id}

    GSI1 (course-scoped — enables teacher to list all students):
        GSI1_PK = COURSE#{course_id}
        GSI1_SK = STUDENT#{cognito_sub}
    """
    cognito_sub: str
    course_id: str
    enrolled_at: str  # ISO 8601
    enrolled_by: str  # ADMIN#{sub} or SYSTEM (CMS sync)
    status: EnrolmentStatus = EnrolmentStatus.ACTIVE

    @property
    def pk(self) -> str:
        return keys.student_pk(self.cognito_sub)

    @property
    def sk(self) -> str:
        return keys.enrol_sk(self.course_id)

    @property
    def gsi1_pk(self) -> str:
        return keys.gsi1_course_pk(self.course_id)

    @property
    def gsi1_sk(self) -> str:
        return keys.gsi1_student_sk(self.cognito_sub)


@dataclass
class TeacherCourseAssignment:
    """
    Links a teacher to a course they are responsible for.
    Written by an admin when assigning teaching duties.

    DynamoDB:
        PK = TEACHER#{cognito_sub}
        SK = TEACHES#{course_id}

    GSI1 (course-scoped — enables admin to list all teachers for a course):
        GSI1_PK = COURSE#{course_id}
        GSI1_SK = TEACHER#{cognito_sub}

    Used by Lambda Authorizer to verify a teacher owns a course
    before allowing write operations.
    """
    cognito_sub: str
    course_id: str
    role: TeacherRole  # lead | assistant
    assigned_at: str  # ISO 8601
    assigned_by: str  # ADMIN#{cognitoSub}

    @property
    def pk(self) -> str:
        return keys.teacher_pk(self.cognito_sub)

    @property
    def sk(self) -> str:
        return keys.teaches_sk(self.course_id)

    @property
    def gsi1_pk(self) -> str:
        return keys.gsi1_course_pk(self.course_id)

    @property
    def gsi1_sk(self) -> str:
        return keys.gsi1_student_sk(self.cognito_sub)
