# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Student routes for CampusIQ.

These routes handle CRUD student operations.

"""

import logging

from fastapi import APIRouter, Request

from src.application.schemas import StudentProfileResponse, StudentEnrolmentsResponse, \
    StudentCourseProgressResponse, ModuleProgressDetailResponse, UpdateProgressResponse, UpdateProgressRequest

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/students",
    tags=["students"]
)


@router.get("/me/courses", response_model=StudentEnrolmentsResponse)
async def get_my_courses(request: Request) -> StudentEnrolmentsResponse:
    pass


@router.get("/me", response_model=StudentProfileResponse)
async def get_my_profile(request: Request) -> StudentProfileResponse:
    pass


@router.get("/me/courses/{course_id}/progress", response_model=StudentCourseProgressResponse)
async def get_my_course_progress(
        course_id: str,
        request: Request
) -> StudentCourseProgressResponse:
    pass


@router.get("/me/courses/{course_id}/modules/{module_id}/progress", response_model=ModuleProgressDetailResponse)
async def get_my_module_progress(
        course_id: str,
        module_id: str,
        request: Request
) -> ModuleProgressDetailResponse:
    pass

@router.put("/me/courses/{course_id}/modules/{module_id}/progress", response_model=UpdateProgressResponse)
async def update_my_module_progress(
        course_id: str,
        module_id: str,
        body: UpdateProgressRequest,
        request: Request,
) -> UpdateProgressResponse:
    pass


@router.get("/{student_id}", response_model=StudentProfileResponse)
async def get_student(student_id: str, request: Request) -> StudentProfileResponse:
    pass

