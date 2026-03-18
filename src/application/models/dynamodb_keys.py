# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
DynamoDB key builder utilities for CampusIQ.

Centralises all PK and SK construction in one place.
Every Lambda function that reads or writes DynamoDB should
import from here rather than constructing key strings inline.

This prevents typos and ensures key format is consistent
across the entire application.
"""


# ── Partition Keys ──────────────────────────────────────────

def course_pk(course_id: str) -> str:
    return f"COURSE#{course_id}"


def student_pk(cognito_sub: str) -> str:
    return f"STUDENT#{cognito_sub}"


def teacher_pk(cognito_sub: str) -> str:
    return f"TEACHER#{cognito_sub}"


def parent_pk(cognito_sub: str) -> str:
    return f"PARENT#{cognito_sub}"


def quiz_pk(quiz_id: str) -> str:
    return f"QUIZ#{quiz_id}"


def config_cms_pk() -> str:
    return "CONFIG#cms_plugin"


def config_domain_pk() -> str:
    return "CONFIG#domain"


def deployment_pk() -> str:
    """Used as GSI1_PK when listing all courses in deployment."""
    return "DEPLOYMENT#main"


# ── Sort Keys ───────────────────────────────────────────────

def metadata_sk() -> str:
    return "METADATA"


def module_sk(module_id: str) -> str:
    return f"MODULE#{module_id}"

def profile_sk() -> str:
    return "PROFILE"

def enrol_sk(course_id: str) -> str:
    return f"ENROL#{course_id}"


def teaches_sk(course_id: str) -> str:
    return f"TEACHES#{course_id}"


def progress_sk(course_id: str, module_id: str) -> str:
    return f"PROGRESS#{course_id}#{module_id}"


def result_sk(course_id: str, module_id: str, attempt_id: str) -> str:
    """
    attempt_id should be formatted as {YYYYMMDDTHHMMSS}-{uuid}
    so that sort order is chronological — latest attempt is last.
    Query with ScanIndexForward=False + Limit=1 for the latest attempt.
    """
    return f"RESULT#{course_id}#{module_id}#{attempt_id}"


def gap_sk(concept_id: str) -> str:
    return f"GAP#{concept_id}"


def path_sk(course_id: str) -> str:
    return f"PATH#{course_id}"


def child_sk(child_cognito_sub: str) -> str:
    return f"CHILD#{child_cognito_sub}"


def ingest_sk(module_id: str) -> str:
    return f"INGEST#{module_id}"


def active_sk() -> str:
    return "ACTIVE"


# ── GSI Keys ────────────────────────────────────────────────

def gsi1_course_pk(course_id: str) -> str:
    """GSI1 partition key for course-scoped queries."""
    return f"COURSE#{course_id}"


def gsi1_student_sk(cognito_sub: str) -> str:
    """GSI1 sort key for student enrolment records."""
    return f"STUDENT#{cognito_sub}"


def gsi1_teacher_sk(cognito_sub: str) -> str:
    """GSI1 sort key for teacher assignment records."""
    return f"TEACHER#{cognito_sub}"


def gsi1_progress_sk(cognito_sub: str, module_id: str) -> str:
    """GSI1 sort key for progress records."""
    return f"PROGRESS#{cognito_sub}#{module_id}"


def gsi1_result_sk(cognito_sub: str, module_id: str, attempt_id: str) -> str:
    """GSI1 sort key for quiz result records."""
    return f"RESULT#{cognito_sub}#{module_id}#{attempt_id}"


def gsi2_gap_severity_sk(gap_severity: float) -> str:
    """
    GSI2 sort key for gap severity sorting.
    Zero-padded to 5 chars so string sort equals numeric sort.
    Query ScanIndexForward=False to get highest severity first.
    """
    return f"{gap_severity:.3f}"


def gsi3_course_pk(course_id: str) -> str:
    """GSI3 partition key for at-risk detection queries."""
    return f"COURSE#{course_id}"


# ── Attempt ID ──────────────────────────────────────────────

def build_attempt_id(submitted_at: str, uuid: str) -> str:
    """
    Builds a sortable attempt ID from submission timestamp and UUID.
    Format: {YYYYMMDDTHHMMSS}-{uuid}
    Example: 20260315T142200-550e8400-e29b-41d4-a716-446655440000

    The timestamp prefix ensures attempts sort chronologically
    when queried via SK begins_with.
    """
    compact_ts = submitted_at.replace("-", "").replace(":", "").replace("Z", "")[:15]
    return f"{compact_ts}-{uuid}"
