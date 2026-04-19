# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Courses routes for CampusIQ.

These routes handle get operations for parents.

"""

import logging

from fastapi import APIRouter, Request

from src.application.schemas import ParentChildrenResponse, ChildProgressResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/parent",
    tags=["parents"]
)


@router.get("/children", response_model=ParentChildrenResponse)
async def get_children_linked_to_parent(
        request: Request,
) -> ParentChildrenResponse:
    pass


@router.get("/children/{student_id}/progress", response_model=ChildProgressResponse)
async def get_children_progress_summary(
        student_id: str,
        request: Request,
) -> ChildProgressResponse:
    pass
