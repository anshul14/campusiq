# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Courses routes for CampusIQ.

These routes handle get operation for a teacher's courses.

"""

import logging
from typing import Optional

from fastapi import APIRouter, Request, Query, HTTPException

from application.schemas import TeacherCoursesResponse, CourseQuizResultsResponse, StudentResultSummary
from application.services import dynamodb as db

router = APIRouter(
    prefix="/teacher",
    tags=["teachers"],
)

logger = logging.getLogger(__name__)


@router.get("/me/courses", response_model=TeacherCoursesResponse)
async def get_courses(
        request: Request
) -> TeacherCoursesResponse:
    pass


# ------------------------------------------------------------------
# GET /teachers/courses/{course_id}/modules/{module_id}/quiz/results
# Teacher views all student quiz results for a module.
# GSI1: PK=COURSE#{courseId}, SK begins_with RESULT#{moduleId}#
# ------------------------------------------------------------------

@router.get(
    "/courses/{course_id}/modules/{module_id}/quiz/results",
    response_model=CourseQuizResultsResponse,
)
async def get_course_quiz_results(
        course_id: str,
        module_id: str,
        request: Request,
        cursor: Optional[str] = Query(None, description="Pagination cursor"),
        page_size: int = Query(50, ge=1, le=200),
) -> CourseQuizResultsResponse:
    """
    Return all student quiz results for a specific module.
    Teacher and Admin only. Teacher must be assigned to the course.

    student_name and attempt_count are denormalized on QuizResult
    at write time — no N+1 lookups needed here.
    """
    authorizer_context = request.state.authorizer
    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]

    if role not in ("TEACHER", "ADMIN"):
        raise HTTPException(status_code=403, detail={
            "code": "FORBIDDEN",
            "message": "Only teachers and admins can view course quiz results"
        })

    try:
        # Teachers must be assigned — admins can see any course
        if role == "TEACHER":
            if not db.teacher_is_assigned_to_course(user_id, course_id):
                raise HTTPException(status_code=403, detail={
                    "code": "NOT_ASSIGNED",
                    "message": "You are not assigned to this course"
                })

        result = db.list_course_quiz_results(
            course_id=course_id,
            module_id=module_id,
            cursor=cursor,
            page_size=page_size,
        )

        results = [
            StudentResultSummary(
                student_id=item["PK"].removeprefix("STUDENT#"),
                name=item.get("student_name", ""),
                score_pct=int(item["score_pct"]),
                passed=item["passed"],
                submitted_at=item["submitted_at"],
                attempt_count=int(item.get("attempt_count", 1)),
            )
            for item in result["items"]
        ]

        return CourseQuizResultsResponse(
            results=results,
            next_cursor=result["next_cursor"],
        )

    except HTTPException:
        raise


    except Exception as e:
        import traceback
        logger.error(f"Failed to fetch course quiz results: {str(e)}\n{traceback.format_exc()}", extra={
            "course_id": course_id,
            "module_id": module_id,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail={
            "code": "QUIZ_RESULTS_FETCH_FAILED",
            "message": "Failed to fetch quiz results"
        })
