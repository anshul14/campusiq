# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Courses routes for CampusIQ.

These routes handle CRUD admin operations.

"""

import logging

from fastapi import APIRouter, Request

from src.application.schemas import UserListResponse, ChangeRoleRequest, ChangeRoleResponse, AssignTeacherResponse, \
    AssignTeacherRequest, CMSPluginConfigResponse, UpdateCMSPluginRequest, DomainConfigResponse, \
    UpdateDomainConfigRequest, TriggerSyncResponse, SyncJobStatusResponse, TriggerSyncRequest, CreateParentLinkRequest, \
    CreateParentLinkResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)


@router.get("/users", response_model=UserListResponse)
async def get_users(
        request: Request,
) -> UserListResponse:
    pass


@router.post("/users/{userId}/role", response_model=ChangeRoleResponse)
async def change_user_role(
        userId: str,
        request: Request,
        body: ChangeRoleRequest
) -> ChangeRoleResponse:
    pass


@router.post("/courses/{courseId}/teachers", response_model=AssignTeacherResponse)
async def assign_teacher_to_course(
        courseId: str,
        request: Request,
        body: AssignTeacherRequest
) -> AssignTeacherResponse:
    pass


@router.delete("/courses/{courseId}/teachers/{teacherSub}", status_code=204)
async def delete_teacher_from_course(
        courseId: str,
        teacherSub: str,
        request: Request,
) -> None:
    pass


@router.get("/config/cms-plugin", response_model=CMSPluginConfigResponse)
async def get_cms_plugin(
        request: Request,
) -> CMSPluginConfigResponse:
    pass


@router.put("/config/cms-plugin", response_model=CMSPluginConfigResponse)
async def put_cms_plugin(
        request: Request,
        body: UpdateCMSPluginRequest
) -> CMSPluginConfigResponse:
    pass


@router.get("/config/domain", response_model=DomainConfigResponse)
async def get_current_domain(
        request: Request,
) -> DomainConfigResponse:
    pass


@router.put("/config/domain", response_model=DomainConfigResponse)
async def update_domain(
        request: Request,
        body: UpdateDomainConfigRequest
) -> DomainConfigResponse:
    pass


@router.post("/cms/sync", response_model=TriggerSyncResponse)
async def sync_cms(
        request: Request,
        body: TriggerSyncRequest
) -> TriggerSyncResponse:
    pass


@router.get("/cms/sync/{job_id}", response_model=SyncJobStatusResponse)
async def get_status_cms_sync(
        job_id: str,
        request: Request,
) -> SyncJobStatusResponse:
    pass


@router.post("/parent-links", response_model=CreateParentLinkResponse)
async def parent_links(
        request: Request,
        body: CreateParentLinkRequest
) -> CreateParentLinkResponse:
    pass
