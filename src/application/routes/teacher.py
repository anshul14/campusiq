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

from fastapi import APIRouter, Request

from src.application.schemas import TeacherCoursesResponse

router = APIRouter(
    prefix="/teachers",
    tags=["teachers"],
)

logger = logging.getLogger(__name__)


@router.get("/me/courses", response_model=TeacherCoursesResponse)
async def get_courses(
        request: Request
) -> TeacherCoursesResponse:
    pass
