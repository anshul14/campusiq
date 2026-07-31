# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0


import logging
from typing import Optional

from fastapi import APIRouter, Query, Request, HTTPException

from application.schemas import (
    EnrolmentListResponse,
    EnrolmentResponse,
    ProgressUpsertRequest,
    ProgressUpsertResponse,
    StudentProfileResponse, StudentQuizResultsResponse, QuizAttemptSummary,
)
from application.services import dynamodb as db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/students", tags=["students"])


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------

def _map_enrolment_to_response(item: dict) -> EnrolmentResponse:
    """
    Enrolment record SK = ENROL#{courseId}
    Strip the prefix to get the bare course_id.
    """
    course_id = item["SK"].removeprefix("ENROL#")
    return EnrolmentResponse(
        course_id=course_id,
        enrolled_at=item["enrolled_at"],
        status=item.get("status", "active"),
    )


def _map_progress_to_response(
        item: dict, course_id: str, module_id: str
) -> ProgressUpsertResponse:
    return ProgressUpsertResponse(
        course_id=course_id,
        module_id=module_id,
        progress_pct=float(item["progress_pct"]),  # Decimal → float for Pydantic
        status=item["status"],
        updated_at=item["updated_at"],
    )


# ------------------------------------------------------------------
# GET /students/me  (already implemented — shown for context)
# ------------------------------------------------------------------

@router.get("/me", response_model=StudentProfileResponse)
async def get_my_profile(request: Request):
    user_id = request.state.authorizer["userId"]
    item = db.get_student_profile(user_id)
    if not item:
        raise HTTPException(status_code=404, detail="Profile not found")

    return StudentProfileResponse(**item)


# ------------------------------------------------------------------
# GET /students/me/courses
# Returns enrolment records for the logged-in student.
# PK = STUDENT#{sub}   SK begins_with ENROL#
# ------------------------------------------------------------------

@router.get("/me/courses", response_model=EnrolmentListResponse)
async def list_my_courses(
        request: Request,
        cursor: Optional[str] = Query(None, description="Pagination cursor from previous response"),
        page_size: int = Query(20, ge=1, le=100),
):
    """
    List courses the logged-in student is enrolled in.
    Returns lightweight enrolment records (enrolled_at, status, course_id).
    Does NOT hydrate full course details — use GET /courses/{course_id} for that.

    Pagination: pass next_cursor from the response as cursor in the next request.
    """
    user_id = request.state.authorizer["userId"]

    result = db.list_student_enrolments(
        user_id=user_id,
        cursor=cursor,
        page_size=page_size,
    )

    items = [_map_enrolment_to_response(item) for item in result["items"]]

    return EnrolmentListResponse(items=items, next_cursor=result["next_cursor"])


# ------------------------------------------------------------------
# PUT /students/me/courses/{course_id}/modules/{module_id}/progress
# Upsert — creates on first call, updates on subsequent calls.
# PK = STUDENT#{sub}   SK = PROGRESS#{courseId}#{moduleId}
# ------------------------------------------------------------------

@router.put(
    "/me/courses/{course_id}/modules/{module_id}/progress",
    response_model=ProgressUpsertResponse,
    status_code=200,
)
async def upsert_module_progress(
        course_id: str,
        module_id: str,
        body: ProgressUpsertRequest,
        request: Request,
):
    """
    Record or update progress for a specific module.

    First call creates the record (created_at is set via if_not_exists).
    Subsequent calls update progress_pct, status, updated_at only.
    Returns the full updated record via ReturnValues=ALL_NEW.
    """
    user_id = request.state.authorizer["userId"]

    item = db.upsert_module_progress(
        user_id=user_id,
        course_id=course_id,
        module_id=module_id,
        progress_pct=body.progress_pct,
        status=body.status,
    )

    return _map_progress_to_response(item, course_id, module_id)


@router.get("/me/courses/{course_id}/modules/{module_id}/quiz/results", response_model=StudentQuizResultsResponse, )
async def get_my_quiz_results(
        course_id: str,
        module_id: str,
        request: Request,
        cursor: Optional[str] = Query(None, description="Pagination cursor from previous response"),
        page_size: int = Query(20, ge=1, le=100),
):
    """
        Return all quiz attempts for the logged-in student for a specific module.
        Most recent attempt first.

        No role check needed — PK = STUDENT#{userId} means a student can only
        ever read their own results. The DynamoDB key enforces this.
        """
    user_id = request.state.authorizer["userId"]

    result = db.list_quiz_attempts(
        user_id=user_id,
        course_id=course_id,
        module_id=module_id,
        cursor=cursor,
        page_size=page_size,
    )

    attempts = [
        QuizAttemptSummary(
            attempt_id=item["SK"].split("#")[-1],  # RESULT#{courseId}#{moduleId}#{attemptId}
            score_pct=int(item["score_pct"]),  # Decimal → int
            passed=item["passed"],
            submitted_at=item["submitted_at"],
            time_taken_seconds=int(item.get("time_taken_seconds", 0)),
        )
        for item in result["items"]
    ]

    return StudentQuizResultsResponse(
        attempts=attempts,
        next_cursor=result["next_cursor"],
    )
