# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Courses routes for CampusIQ.

These routes handle CRUD course operations.

"""

import logging

from fastapi import APIRouter, Request

from src.application.schemas import CourseResponse, CourseListResponse, UpdateCourseResponse, \
    CreateCourseResponse, CreateCourseRequest, UpdateCourseRequest, ModuleListResponse, ModuleResponse, \
    CreateModuleRequest, CreateModuleResponse, UpdateModuleRequest, UpdateModuleResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/courses",
    tags=["courses"]
)


@router.get("/", response_model=CourseListResponse)
async def get_courses(
        request: Request,
        domain: str = None,  # GET /courses?domain=university
        status: str = None,  # GET /courses?status=published
        cursor: str = None,  # GET /courses?cursor=abc123
        page_size: int = 20,  # GET /courses?page_size=50

) -> CourseListResponse:
    pass


@router.get("/{course_id}", response_model=CourseResponse)
async def get_course(
        course_id: str,
        request: Request
) -> CourseResponse:
    pass


@router.patch("/{course_id}", response_model=UpdateCourseResponse)
async def update_course(
        course_id: str,
        request: Request,
        body: UpdateCourseRequest,

) -> UpdateCourseResponse:
    pass


@router.post("/", response_model=CreateCourseResponse)
async def create_course(
        request: Request,
        body: CreateCourseRequest,
) -> CreateCourseResponse:
    pass


@router.delete("/{course_id}", status_code=204)
async def delete_course(
        course_id: str,
        request: Request,
) -> None:
    pass

@router.get("/{course_id}/modules", response_model=ModuleListResponse)
async def get_modules(
        request: Request,
        course_id: str,
) -> ModuleListResponse:
    pass

@router.get("/{course_id}/modules/{module_id}", response_model=ModuleResponse)
async def get_module(
        request: Request,
        course_id: str,
        module_id: str,
) -> ModuleResponse:
    pass

@router.post("/{course_id}/modules", response_model=CreateModuleResponse)
async def create_module(
        request: Request,
        course_id: str,
        body: CreateModuleRequest,
) -> CreateModuleResponse:
    pass

@router.patch("/{course_id}/modules/{module_id}", response_model=UpdateModuleResponse)
async def  update_module(
        course_id: str,
        module_id: str,
        request: Request,
        body: UpdateModuleRequest,
) -> UpdateModuleResponse:
    pass

@router.delete("/{course_id}/modules/{module_id}", status_code=204)
async def delete_module(
        course_id: str,
        module_id: str,
        request: Request,
) -> None:
    pass