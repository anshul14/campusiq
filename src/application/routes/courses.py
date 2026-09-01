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
import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Request, HTTPException

from application.schemas import CourseResponse, CourseListResponse, UpdateCourseResponse, \
    CreateCourseResponse, CreateCourseRequest, UpdateCourseRequest, ModuleListResponse, ModuleResponse, \
    CreateModuleRequest, CreateModuleResponse, UpdateModuleRequest, UpdateModuleResponse, CourseStudentListResponse, \
    EnrolStudentsRequest, EnrolStudentsResponse, CourseProgressResponse, CourseGapsResponse, DashboardResponse, \
    AtRiskResponse, IngestionStatusResponse, ConceptGapDetail, AtRiskStudent, CourseStudentSummary, \
    ContentPresignResponse, ContentPresignRequest, ContentCompleteResponse, ContentCompleteRequest, \
    SaveTextContentResponse, SaveTextContentRequest, CourseStatusEnum, ModuleStatusEnum, ModuleSummary
from application.schemas import CourseSummary
from application.services import dynamodb as db
from application.services.events import emit_module_published, EventEmitFailedError

logger = logging.getLogger(__name__)

# Module-level client, ADR-012 pattern — created once on cold start.
s3_client = boto3.client("s3")
CONTENT_BUCKET = os.environ["CONTENT_BUCKET_NAME"]

# Same threshold the Gap Detection Lambda uses to gate the GapDetected
# EventBridge event — kept as Decimal since gap_severity comes back from
# DynamoDB as Decimal and comparing float to Decimal raises TypeError.
AT_RISK_THRESHOLD = Decimal("0.700")

router = APIRouter(
    prefix="/courses",
    tags=["courses"]
)


def _verify_course_access(
        role: str,
        user_id: str,
        course_id: str
) -> dict:
    """Verify user can access this course. Returns course dict or raises HTTPException."""
    if role == "ADMIN":
        course = db.get_course_by_id(course_id)
    elif role == "TEACHER":
        if not db.teacher_is_assigned_to_course(user_id, course_id):
            raise HTTPException(status_code=403, detail="Teacher not assigned to course")
        course = db.get_course_by_id(course_id)
    elif role == "STUDENT":
        if not db.student_is_enrolled_to_course(user_id, course_id):
            raise HTTPException(status_code=403, detail="Student not enrolled to course")
        course = db.get_course_by_id(course_id)
    else:
        raise HTTPException(status_code=403, detail="Unknown role")

    if course is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "COURSE_NOT_FOUND", "message": f"Course {course_id} not found"}
        )
    return course


@router.get("/", response_model=CourseListResponse)
async def get_courses(
        request: Request,
        domain: str = None,  # GET /courses?domain=university
        status: str = None,  # GET /courses?status=published
        cursor: str = None,  # GET /courses?cursor=abc123
        page_size: int = 20,  # GET /courses?page_size=50

) -> CourseListResponse:
    authorizer_context = request.state.authorizer
    role = authorizer_context["role"]

    if role == "ADMIN":
        result = db.list_all_courses(
            domain=domain, status=status, cursor=cursor, page_size=page_size)
    else:
        # TODO: Phase 2 - Implement student and teacher filtered views
        result = db.list_all_courses(
            domain=domain, status=status, cursor=cursor, page_size=page_size)

    return CourseListResponse(
        courses=[CourseSummary(**item) for item in result["items"]],
        next_cursor=result["next_cursor"]
    )


@router.get("/{course_id}", response_model=CourseResponse)
async def get_course(
        course_id: str,
        request: Request
) -> CourseResponse:
    authorizer_context = request.state.authorizer
    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]

    course = _verify_course_access(role=role, user_id=user_id, course_id=course_id)
    return CourseResponse(**course)


@router.patch("/{course_id}", response_model=UpdateCourseResponse)
async def update_course(
        course_id: str,
        request: Request,
        body: UpdateCourseRequest,

) -> UpdateCourseResponse:
    authorizer_context = request.state.authorizer
    now = datetime.now(timezone.utc).isoformat()

    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]

    course = _verify_course_access(role=role, user_id=user_id, course_id=course_id)
    try:
        db.update_course(
            course_id=course_id,
            title=body.title,
            description=body.description,
            difficulty=body.difficulty,
            status=body.status,
            now=now

        )
    except Exception as e:
        logger.error("Failed to update course", extra={
            "course_id": course_id,
            "error": str(e),
        })
        raise HTTPException(status_code=500,
                            detail={"code": "COURSE_UPDATE_FAILED",
                                    "message": "Failed to update course"})
    return UpdateCourseResponse(
        course_id=course_id,
        updated_at=now,
    )


@router.post("/", response_model=CreateCourseResponse, status_code=201)
async def create_course(
        request: Request,
        body: CreateCourseRequest,
) -> CreateCourseResponse:
    authorizer_context = request.state.authorizer
    created_by = authorizer_context["userId"]
    course_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]
    if role == "STUDENT":
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN",
                    "message": "Students cannot create courses"}
        )
    try:
        db.create_course(
            course_id=course_id,
            title=body.title,
            description=body.description,
            domain=body.domain,
            difficulty=body.difficulty,
            cms_source=body.cms_source,
            created_by=created_by,
            now=now,
        )
    except Exception as e:
        logger.error("Failed to create course", extra={
            "course_id": course_id,
            "error": str(e),
        })
        raise HTTPException(status_code=500,
                            detail={"code": "COURSE_CREATE_FAILED",
                                    "message": "Failed to create course"})

    return CreateCourseResponse(course_id=course_id, title=body.title, status=CourseStatusEnum.DRAFT)


@router.delete("/{course_id}", status_code=204)
async def delete_course(
        course_id: str,
        request: Request,
) -> None:
    authorizer_context = request.state.authorizer
    now = datetime.now(timezone.utc).isoformat()

    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]

    course = _verify_course_access(role=role, user_id=user_id, course_id=course_id)

    try:
        db.archive_course(course_id=course_id, now=now)
    except Exception as e:
        logger.error("Failed to archive course", extra={
            "course_id": course_id,
            "error": str(e),
        })
        raise HTTPException(status_code=500,
                            detail={"code": "COURSE_ARCHIVE_FAILED",
                                    "message": "Failed to archive course"})


@router.get("/{course_id}/modules", response_model=ModuleListResponse)
async def get_modules(
        request: Request,
        course_id: str,
) -> ModuleListResponse:
    authorizer_context = request.state.authorizer
    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]
    result = None

    # Step 1 - First check if the user is allowed to view/assigned/enrolled to the course 
    course = _verify_course_access(role=role, user_id=user_id, course_id=course_id)
    # Step 2 - list modules of the course
    result = db.list_all_modules_of_course(course_id=course_id)

    return ModuleListResponse(
        modules=[ModuleSummary(**item) for item in result["items"]],
        next_cursor=result["next_cursor"]
    )


@router.get("/{course_id}/modules/{module_id}", response_model=ModuleResponse)
async def get_module_by_id(
        request: Request,
        course_id: str,
        module_id: str,
) -> ModuleResponse:
    authorizer_context = request.state.authorizer
    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]

    # Step 1 - first check if the user has access to the course
    _verify_course_access(role=role, user_id=user_id, course_id=course_id)
    # Step 2 - get the module
    module = db.get_module_by_id(course_id=course_id, module_id=module_id)
    if module is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "MODULE_NOT_FOUND", "message": f"Module {module_id} not found"}
        )
    return ModuleResponse(**module)


@router.post("/{course_id}/modules", response_model=CreateModuleResponse)
async def create_module(
        request: Request,
        course_id: str,
        body: CreateModuleRequest,
) -> CreateModuleResponse:
    authorizer_context = request.state.authorizer
    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]
    module_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    if role == "STUDENT":
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN",
                    "message": "Students cannot create modules"}
        )
    # Step 1 - create module for the course
    try:
        db.create_module(
            course_id=course_id,
            module_id=module_id,
            title=body.title,
            content_type=body.content_type,
            estimated_minutes=body.estimated_minutes,
            prerequisites=body.prerequisites,
            created_by=user_id,
            now=now,
        )
    except Exception as e:
        logger.error(f"Failed to create module for course {course_id}", extra={
            "course_id": course_id,
            "error": str(e),
        })
        raise HTTPException(status_code=500,
                            detail={"code": "MODULE_CREATION_FAILED",
                                    "message": "Failed to create module"})

    # Step 2 - append module_id to course's module order
    try:
        db.append_module_to_course_order(
            course_id=course_id,
            module_id=module_id,
        )
    except Exception as e:
        logger.error("Failed to update module order", extra={
            "course_id": course_id,
            "module_id": module_id,
            "error": str(e),
        })
        raise HTTPException(status_code=500,
                            detail={"code": "MODULE_ORDER_UPDATE_FAILED",
                                    "message": "Module created but failed to update course order"})

    return CreateModuleResponse(
        module_id=module_id,
        title=body.title,
        status="draft",
        ingestion_status="pending",
    )


@router.patch("/{course_id}/modules/{module_id}", response_model=UpdateModuleResponse)
async def update_module(
        course_id: str,
        module_id: str,
        request: Request,
        body: UpdateModuleRequest,
) -> UpdateModuleResponse:
    authorizer_context = request.state.authorizer
    now = datetime.now(timezone.utc).isoformat()
    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]

    # Step 1 - first verify access to the course
    _verify_course_access(role=role, user_id=user_id, course_id=course_id)

    is_publishing = body.status == ModuleStatusEnum.PUBLISHED

    # Step 2 - the publish transition is handled separately from the
    # generic field-update path below (fast synchronous write, then an
    # async ModulePublished event) — see events.py / dynamodb.py's
    # publish_module(). The generic path doesn't know about
    # ingestion_status or ingestion at all, and shouldn't have to.
    if is_publishing:
        try:
            db.publish_module(course_id=course_id, module_id=module_id, now=now)
        except ValueError:
            raise HTTPException(status_code=404, detail={
                "code": "MODULE_NOT_FOUND",
                "message": f"Module {module_id} not found"
            })
        except Exception as e:
            logger.error("Failed to publish module", extra={
                "course_id": course_id, "module_id": module_id, "error": str(e),
            })
            raise HTTPException(status_code=500, detail={
                "code": "MODULE_PUBLISH_FAILED",
                "message": "Failed to publish module"
            })

        try:
            emit_module_published(course_id=course_id, module_id=module_id)
        except (EventEmitFailedError, Exception) as e:
            # The DynamoDB write already succeeded and the teacher already
            # sees "Published" — a failed event emit means ingestion won't
            # fire automatically, not that the publish itself failed. Log
            # loudly rather than 500 on a request that actually succeeded.
            logger.error(
                "Failed to emit ModulePublished — module is published but "
                "ingestion will not trigger automatically",
                extra={"course_id": course_id, "module_id": module_id, "error": str(e)},
            )

    # Step 3 - any other fields (title/estimated_minutes/prerequisites, or
    # a non-publish status change like archiving) still go through the
    # generic path. status is deliberately omitted here when is_publishing
    # — already handled above, not touched twice in one request.
    other_fields_present = any([
        body.title is not None,
        body.estimated_minutes is not None,
        body.prerequisites is not None,
        body.status is not None and not is_publishing,
    ])
    if other_fields_present:
        try:
            db.update_module(
                course_id=course_id,
                module_id=module_id,
                title=body.title,
                estimated_minutes=body.estimated_minutes,
                prerequisites=body.prerequisites,
                status=None if is_publishing else body.status,
                now=now
            )
        except Exception as e:
            logger.error("Failed to update module", extra={
                "course_id": course_id,
                "module_id": module_id,
                "error": str(e),
            })
            raise HTTPException(status_code=500,
                                detail={"code": "MODULE_UPDATE_FAILED",
                                        "message": "Failed to update module"})

    return UpdateModuleResponse(
        module_id=module_id,
        updated_at=now,
    )


@router.delete("/{course_id}/modules/{module_id}", status_code=204)
async def delete_module(
        course_id: str,
        module_id: str,
        request: Request,
) -> None:
    authorizer_context = request.state.authorizer
    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]
    now = datetime.now(timezone.utc).isoformat()

    _verify_course_access(role=role, user_id=user_id, course_id=course_id)
    try:
        db.archive_module(course_id=course_id, module_id=module_id, now=now)

    except Exception as e:
        logger.error("Failed to archive module", extra={
            "module_id": module_id,
            "error": str(e),
        })
        raise HTTPException(status_code=500,
                            detail={"code": "MODULE_ARCHIVE_FAILED",
                                    "message": "Failed to archive module"})
    # Step 2 — remove from course module_order
    try:
        db.remove_module_from_course_order(
            course_id=course_id,
            module_id=module_id,
        )
    except Exception as e:
        logger.error("Failed to update module order after archive", extra={
            "course_id": course_id,
            "module_id": module_id,
            "error": str(e),
        })
        # Non-fatal — module is archived, order update failed
        # TODO: add compensation logic or DynamoDB transaction in Phase 3


@router.get("/{course_id}/students", response_model=CourseStudentListResponse)
async def list_course_students(
        course_id: str,
        request: Request,
        cursor: str = None,
        page_size: int = 50,
) -> CourseStudentListResponse:
    authorizer_context = request.state.authorizer
    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]

    # Roster includes email addresses — same PII posture as at-risk,
    # students shouldn't see classmates' contact info.
    if role not in ("TEACHER", "ADMIN"):
        raise HTTPException(status_code=403, detail={
            "code": "FORBIDDEN", "message": "Only teachers and admins can view the course roster"
        })

    _verify_course_access(role=role, user_id=user_id, course_id=course_id)

    result = db.list_course_students(course_id=course_id, cursor=cursor, page_size=page_size)

    # ENROL# records carry student_id/enrolled_at/status but not
    # name/email — those live on the separate PROFILE record, joined
    # here per page (bounded by page_size, unlike the at-risk N+1 which
    # spans the whole course).
    students = []
    for item in result["items"]:
        student_id = item["student_id"]
        profile = db.get_student_profile(student_id)
        students.append(CourseStudentSummary(
            cognito_sub=student_id,
            student_id=student_id,
            name=profile["name"] if profile else "Unknown",
            email=profile["email"] if profile else "",
            enrolled_at=item["enrolled_at"],
            status=item["status"],
        ))

    return CourseStudentListResponse(
        students=students,
        next_cursor=result["next_cursor"],
    )


@router.post("/{course_id}/enrolments", response_model=EnrolStudentsResponse, status_code=201)
async def enrol_students(
        course_id: str,
        body: EnrolStudentsRequest,
        request: Request,
) -> EnrolStudentsResponse:
    authorizer_context = request.state.authorizer
    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]
    now = datetime.now(timezone.utc).isoformat()

    # Verify course exists
    course = db.get_course_by_id(course_id)
    if course is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "COURSE_NOT_FOUND", "message": f"Course {course_id} not found"}
        )

    if role == "ADMIN":
        # Admin can enrol any student in any course
        student_ids = body.student_ids

    elif role == "TEACHER":
        # Teacher can only enrol in their assigned courses
        if not db.teacher_is_assigned_to_course(user_id, course_id):
            raise HTTPException(
                status_code=403,
                detail={"code": "FORBIDDEN", "message": "Teacher not assigned to this course"}
            )
        student_ids = body.student_ids

    elif role == "STUDENT":
        # Student can only enrol themselves in published courses
        if course["status"] != "published":
            raise HTTPException(
                status_code=403,
                detail={"code": "COURSE_NOT_PUBLISHED", "message": "Course is not available for enrolment"}
            )
        # Students can only enrol themselves — ignore any other IDs in the request
        student_ids = [user_id]

    else:
        raise HTTPException(status_code=403, detail="Unknown role")

    try:
        db.enrol_students(
            course_id=course_id,
            student_ids=student_ids,
            now=now,
        )
    except Exception as e:
        logger.error("Failed to enrol students", extra={
            "course_id": course_id,
            "error": str(e),
        })
        raise HTTPException(
            status_code=500,
            detail={"code": "ENROLMENT_FAILED", "message": "Failed to enrol students"}
        )

    return EnrolStudentsResponse(
        enrolled=student_ids,  # list of successfully enrolled student IDs
        failed=[]  # empty for now - Phase 2 add per-item error handling
    )


@router.get("/{course_id}/progress", response_model=CourseProgressResponse)
async def get_course_progress(
        course_id: str,
        request: Request,
        module_id: str = None,

) -> CourseProgressResponse:
    pass


# Gaps
@router.get("/{course_id}/gaps", response_model=CourseGapsResponse)
async def get_gaps(
        course_id: str,
        request: Request,
) -> CourseGapsResponse:
    authorizer_context = request.state.authorizer
    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]

    # Aggregate-only (no student names) but still a teacher-facing
    # heatmap per the schema docstring — same guard as at-risk below,
    # for consistency rather than because this specific payload leaks PII.
    if role not in ("TEACHER", "ADMIN"):
        raise HTTPException(status_code=403, detail={
            "code": "FORBIDDEN", "message": "Only teachers and admins can view the gap heatmap"
        })

    _verify_course_access(role=role, user_id=user_id, course_id=course_id)

    gap_records = db.list_course_gap_records(course_id=course_id)

    # Per-concept aggregation across every gap record regardless of
    # severity (list_course_gap_records() is unfiltered by design — see
    # its docstring) so avg_severity reflects "how bad when it happens,"
    # not diluted by students who haven't triggered a gap on this concept.
    by_concept: dict[str, dict] = {}
    for record in gap_records:
        concept_id = record["concept_id"]
        severity = record["gap_severity"]  # Decimal

        bucket = by_concept.setdefault(concept_id, {
            "concept_name": record.get("concept_name", concept_id),
            "severities": [],
            "at_risk_count": 0,
        })
        bucket["severities"].append(severity)
        if severity >= AT_RISK_THRESHOLD:
            bucket["at_risk_count"] += 1

    concepts = [
        ConceptGapDetail(
            concept_id=concept_id,
            concept_name=data["concept_name"],
            avg_severity=float(sum(data["severities"]) / len(data["severities"])),
            at_risk_count=data["at_risk_count"],
        )
        for concept_id, data in by_concept.items()
    ]

    # Widest class-wide problem first — at_risk_count is the undiluted
    # "how many students" signal, avg_severity breaks ties.
    concepts.sort(key=lambda c: (c.at_risk_count, c.avg_severity), reverse=True)

    return CourseGapsResponse(concepts=concepts)


@router.get("/{course_id}/dashboard", response_model=DashboardResponse)
async def get_faculty_dashboard(
        course_id: str,
        request: Request,
) -> DashboardResponse:
    pass


@router.get("/{course_id}/at-risk", response_model=AtRiskResponse)
async def get_at_risk_students(
        course_id: str,
        request: Request,
) -> AtRiskResponse:
    authorizer_context = request.state.authorizer
    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]

    # Returns real student names tied to their weakest concepts — must
    # never be reachable by a student in the course, not just an admin/
    # teacher of it. _verify_course_access() alone would let an enrolled
    # student in (it grants access to STUDENT role), so this explicit
    # gate has to come first.
    if role not in ("TEACHER", "ADMIN"):
        raise HTTPException(status_code=403, detail={
            "code": "FORBIDDEN", "message": "Only teachers and admins can view at-risk students"
        })

    _verify_course_access(role=role, user_id=user_id, course_id=course_id)

    gap_records = db.list_course_gap_records(course_id=course_id)

    # Group by student, keeping only gaps at or above the at-risk
    # threshold — list_course_gap_records() is unfiltered, so the
    # filtering happens here same as the GSI3 query pattern in the docs
    # (KeyConditionExpression Key('GSI3_SK').gte('0.700')), just applied
    # in-memory since we already fetched the full course dataset for
    # get_gaps' sibling aggregation.
    by_student: dict[str, list[dict]] = {}
    for record in gap_records:
        severity = record["gap_severity"]  # Decimal
        if severity < AT_RISK_THRESHOLD:
            continue
        student_id = record["PK"].replace("STUDENT#", "")
        by_student.setdefault(student_id, []).append({
            "concept_id": record["concept_id"],
            "concept_name": record.get("concept_name", record["concept_id"]),
            "gap_severity": float(severity),
        })

    at_risk_students = []
    for student_id, gaps in by_student.items():
        profile = db.get_student_profile(student_id)
        at_risk_students.append(AtRiskStudent(
            student_id=student_id,
            name=profile["name"] if profile else "Unknown",
            gaps=gaps,
        ))

    # Most-affected students first — by number of at-risk concepts, then
    # by their single worst severity as a tiebreaker.
    at_risk_students.sort(
        key=lambda s: (len(s.gaps), max(g["gap_severity"] for g in s.gaps)),
        reverse=True,
    )

    return AtRiskResponse(at_risk_students=at_risk_students)


@router.get("/{course_id}/modules/{module_id}/ingestion-status", response_model=IngestionStatusResponse)
async def get_bedrock_kb_ingestion_status_for_module(
        course_id: str,
        module_id: str,
        request: Request,
) -> IngestionStatusResponse:
    authorizer_context = request.state.authorizer
    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]

    # Reuses the same cascading access model as every other course-scoped
    # route: a student who can't see the course can't see its modules'
    # ingestion status either.
    _verify_course_access(role, user_id, course_id)

    status = db.get_module_ingestion_status(course_id, module_id)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "MODULE_NOT_FOUND", "message": f"Module {module_id} not found"}
        )

    return IngestionStatusResponse(**status)


# Content Upload

@router.post("/{course_id}/modules/{module_id}/content/presign", response_model=ContentPresignResponse)
async def presign_content_upload(
        course_id: str,
        module_id: str,
        body: ContentPresignRequest,
        request: Request,
) -> ContentPresignResponse:
    authorizer_context = request.state.authorizer
    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]

    if role not in ("TEACHER", "ADMIN"):
        raise HTTPException(status_code=403, detail={
            "code": "FORBIDDEN", "message": "Only teachers and admins can upload module content"
        })

    course = _verify_course_access(role=role, user_id=user_id, course_id=course_id)

    if body.file_type == "video":
        # Genuinely undesigned, not a stub — the video pipeline
        # (raw-uploads/ -> MediaConvert -> Transcribe -> HLS/WebVTT) has
        # no confirmed S3 key convention yet. Rejecting explicitly
        # rather than guessing at an unverified path structure.
        raise HTTPException(status_code=501, detail={
            "code": "VIDEO_NOT_YET_SUPPORTED",
            "message": "Video upload is not yet implemented — the ingestion pipeline for video is still undesigned"
        })

    if body.file_type != "pdf":
        raise HTTPException(status_code=400, detail={
            "code": "UNSUPPORTED_FILE_TYPE",
            "message": f"Unsupported file_type {body.file_type!r} — only 'pdf' is currently supported"
        })

    domain = course["domain"]
    s3_key = f"{domain}/{course_id}/modules/{module_id}/content.pdf"

    try:
        upload_url = s3_client.generate_presigned_url(
            "put_object",
            Params={"Bucket": CONTENT_BUCKET, "Key": s3_key, "ContentType": "application/pdf"},
            ExpiresIn=900,
        )
    except ClientError as e:
        logger.error("Failed to generate presigned upload URL", extra={
            "course_id": course_id, "module_id": module_id, "error": str(e),
        })
        raise HTTPException(status_code=500, detail={
            "code": "PRESIGN_FAILED", "message": "Failed to generate upload URL"
        })

    return ContentPresignResponse(upload_url=upload_url, s3_key=s3_key, expires_in_seconds=900)


@router.post("/{course_id}/modules/{module_id}/content/complete", response_model=ContentCompleteResponse)
async def complete_content_upload(
        course_id: str,
        module_id: str,
        body: ContentCompleteRequest,
        request: Request,
) -> ContentCompleteResponse:
    authorizer_context = request.state.authorizer
    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]
    now = datetime.now(timezone.utc).isoformat()

    if role not in ("TEACHER", "ADMIN"):
        raise HTTPException(status_code=403, detail={
            "code": "FORBIDDEN", "message": "Only teachers and admins can upload module content"
        })

    course = _verify_course_access(role=role, user_id=user_id, course_id=course_id)

    # Step 1 - verify the object actually exists. A client calling
    # "complete" doesn't prove the browser's PUT actually succeeded —
    # confirm server-side rather than trust the request.
    try:
        s3_client.head_object(Bucket=CONTENT_BUCKET, Key=body.s3_key)
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ("404", "NoSuchKey", "NotFound"):
            raise HTTPException(status_code=400, detail={
                "code": "UPLOAD_NOT_FOUND",
                "message": f"No object found at s3_key={body.s3_key!r} — did the upload actually complete?"
            })
        logger.error("head_object failed during content completion", extra={
            "course_id": course_id, "module_id": module_id, "error": str(e),
        })
        raise HTTPException(status_code=500, detail={
            "code": "CONTENT_COMPLETE_FAILED", "message": "Failed to verify upload"
        })

    # Step 2 - stamp domain/difficulty metadata server-side. S3 object
    # metadata is immutable except via a copy — this is a self-copy with
    # MetadataDirective=REPLACE, same principle as save_text_content:
    # the backend controls domain/difficulty, never the client.
    domain = course["domain"]
    difficulty = course.get("difficulty", "")
    try:
        s3_client.copy_object(
            Bucket=CONTENT_BUCKET, Key=body.s3_key,
            CopySource={"Bucket": CONTENT_BUCKET, "Key": body.s3_key},
            Metadata={"domain": domain, "difficulty": difficulty},
            MetadataDirective="REPLACE",
        )
    except ClientError as e:
        logger.error("Failed to stamp metadata on uploaded content", extra={
            "course_id": course_id, "module_id": module_id, "error": str(e),
        })
        raise HTTPException(status_code=500, detail={
            "code": "CONTENT_COMPLETE_FAILED", "message": "Failed to finalise upload"
        })

    # Step 3 - record the S3 key. Same as save_text_content: does NOT
    # touch status/ingestion_status — uploading is not publishing.
    try:
        db.update_module_content(
            course_id=course_id, module_id=module_id,
            content_s3_key=body.s3_key, content_type=body.content_type.value, now=now,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail={
            "code": "MODULE_NOT_FOUND", "message": f"Module {module_id} not found"
        })
    except Exception as e:
        logger.error("Failed to update module content record", extra={
            "course_id": course_id, "module_id": module_id, "error": str(e),
        })
        raise HTTPException(status_code=500, detail={
            "code": "CONTENT_COMPLETE_FAILED", "message": "Failed to finalise upload"
        })

    # ingestion_status returned as "pending", not the schema's PROCESSING
    # default — nothing is ingesting yet, that only starts at Publish.
    return ContentCompleteResponse(module_id=module_id, ingestion_status="pending")


@router.put("/{course_id}/modules/{module_id}/content/text", response_model=SaveTextContentResponse)
async def save_text_content(
        course_id: str,
        module_id: str,
        body: SaveTextContentRequest,
        request: Request,
) -> SaveTextContentResponse:
    authorizer_context = request.state.authorizer
    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]
    now = datetime.now(timezone.utc).isoformat()

    if role not in ("TEACHER", "ADMIN"):
        raise HTTPException(status_code=403, detail={
            "code": "FORBIDDEN", "message": "Only teachers and admins can save module content"
        })

    # Step 1 - verify access (also fetches the course record, which we
    # need for domain/difficulty below)
    course = _verify_course_access(role=role, user_id=user_id, course_id=course_id)

    # Step 2 - write to S3. domain/difficulty come from the COURSE#
    # record looked up server-side here, never from the client — the
    # module editor never needs a domain field; it's inherited silently
    # from the course context.
    domain = course["domain"]
    difficulty = course.get("difficulty", "")
    s3_key = f"{domain}/{course_id}/modules/{module_id}/content.md"

    try:
        s3_client.put_object(
            Bucket=CONTENT_BUCKET,
            Key=s3_key,
            Body=body.content.encode("utf-8"),
            ContentType="text/markdown",
            Metadata={"domain": domain, "difficulty": difficulty},
        )
    except ClientError as e:
        logger.error("Failed to write module content to S3", extra={
            "course_id": course_id, "module_id": module_id, "error": str(e),
        })
        raise HTTPException(status_code=500, detail={
            "code": "CONTENT_SAVE_FAILED", "message": "Failed to save content"
        })

    # Step 3 - record the S3 key on the module. Deliberately does NOT
    # touch status/ingestion_status — saving content is not publishing
    # it. ingestion_status returned here is always "pending", not the
    # schema's PROCESSING default — nothing is ingesting until an
    # explicit Publish action fires (the module-level gate).
    try:
        db.update_module_content(
            course_id=course_id, module_id=module_id,
            content_s3_key=s3_key, content_type="markdown", now=now,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail={
            "code": "MODULE_NOT_FOUND", "message": f"Module {module_id} not found"
        })
    except Exception as e:
        logger.error("Failed to update module content record", extra={
            "course_id": course_id, "module_id": module_id, "error": str(e),
        })
        raise HTTPException(status_code=500, detail={
            "code": "CONTENT_SAVE_FAILED", "message": "Failed to save content"
        })

    return SaveTextContentResponse(
        module_id=module_id,
        saved_at=now,
        ingestion_status="pending",
    )