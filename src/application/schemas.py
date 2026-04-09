# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
CampusIQ API Schemas — Pydantic request and response models.

These models are used by FastAPI for:
  1. Validating incoming request bodies
  2. Serialising outgoing response payloads
  3. Auto-generating OpenAPI documentation

Organisation:
  Each route group has its own section.
  Request models are suffixed with Request.
  Response models are suffixed with Response.
  Shared/nested models have no suffix.

Usage:
    from src.application.schemas import (
        CreateCourseRequest,
        CourseResponse,
        SubmitQuizRequest,
        QuizResultResponse,
    )
"""

from __future__ import annotations
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Any
from enum import Enum


# ─────────────────────────────────────────────────────
# SHARED ENUMS
# ─────────────────────────────────────────────────────

class DomainEnum(str, Enum):
    UNIVERSITY = "university"
    K12        = "k12"
    CORPORATE  = "corporate"


class DifficultyEnum(str, Enum):
    BEGINNER     = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED     = "advanced"


class ContentTypeEnum(str, Enum):
    MARKDOWN = "markdown"
    PDF      = "pdf"
    VIDEO    = "video"


class CourseStatusEnum(str, Enum):
    DRAFT     = "draft"
    PUBLISHED = "published"
    ARCHIVED  = "archived"


class RoleEnum(str, Enum):
    STUDENT = "STUDENT"
    TEACHER = "TEACHER"
    ADMIN   = "ADMIN"
    PARENT  = "PARENT"
    OPS     = "OPS"


class QuestionTypeEnum(str, Enum):
    SINGLE   = "SINGLE"
    MULTIPLE = "MULTIPLE"


class IngestionStatusEnum(str, Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    COMPLETE   = "complete"
    FAILED     = "failed"


# ─────────────────────────────────────────────────────
# SHARED RESPONSE MODELS
# ─────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    """Standard error response body — returned on all 4xx and 5xx responses."""
    code:       str = Field(..., description="Machine-readable error code e.g. COURSE_NOT_FOUND")
    message:    str = Field(..., description="Human-readable error description")
    request_id: str = Field(..., description="Request ID for debugging and support")


class ErrorResponse(BaseModel):
    error: ErrorDetail


class PaginatedMeta(BaseModel):
    """Included in paginated list responses."""
    next_cursor:  Optional[str] = Field(None, description="Pass as ?cursor= to get the next page. Null if no more pages.")
    total_count:  Optional[int] = None


# ─────────────────────────────────────────────────────
# AUTH SCHEMAS
# ─────────────────────────────────────────────────────

class SessionUser(BaseModel):
    sub:        str
    name:       str
    email:      str
    role:       RoleEnum
    domain:     DomainEnum
    student_id: Optional[str] = None   # populated for STUDENT role only


class SessionResponse(BaseModel):
    """GET /api/v1/auth/session"""
    user:       SessionUser
    expires_at: str   # ISO 8601


# ─────────────────────────────────────────────────────
# COURSE SCHEMAS
# ─────────────────────────────────────────────────────

class CreateCourseRequest(BaseModel):
    """POST /api/v1/courses"""
    title:         str          = Field(..., min_length=3, max_length=200)
    description:   str          = Field(..., min_length=10, max_length=2000)
    domain:        DomainEnum
    difficulty:    DifficultyEnum
    cms_source:    str          = Field(default="s3", description="s3 | google_classroom | strapi | custom")
    cms_course_id: Optional[str] = Field(None, description="Original course ID in the source CMS")


class UpdateCourseRequest(BaseModel):
    """PATCH /api/v1/courses/{courseId}"""
    title:       Optional[str]              = Field(None, min_length=3, max_length=200)
    description: Optional[str]              = Field(None, min_length=10, max_length=2000)
    difficulty:  Optional[DifficultyEnum]   = None
    status:      Optional[CourseStatusEnum] = None


class CourseSummary(BaseModel):
    """Lightweight course object used in list responses."""
    course_id:    str
    title:        str
    description:  str
    domain:       DomainEnum
    difficulty:   DifficultyEnum
    status:       CourseStatusEnum
    module_count: int


class CourseResponse(BaseModel):
    """GET /api/v1/courses/{courseId}"""
    course_id:     str
    title:         str
    description:   str
    domain:        DomainEnum
    difficulty:    DifficultyEnum
    status:        CourseStatusEnum
    module_order:  list[str]
    cms_source:    str
    created_by:    str
    created_at:    str
    updated_at:    str


class CourseListResponse(BaseModel):
    """GET /api/v1/courses"""
    courses:     list[CourseSummary]
    next_cursor: Optional[str] = None


class CreateCourseResponse(BaseModel):
    """POST /api/v1/courses — 201"""
    course_id: str
    title:     str
    status:    CourseStatusEnum = CourseStatusEnum.DRAFT


class UpdateCourseResponse(BaseModel):
    """PATCH /api/v1/courses/{courseId}"""
    course_id:  str
    updated_at: str


# ─────────────────────────────────────────────────────
# MODULE SCHEMAS
# ─────────────────────────────────────────────────────

class CreateModuleRequest(BaseModel):
    """POST /api/v1/courses/{courseId}/modules"""
    title:              str           = Field(..., min_length=3, max_length=200)
    content_type:       ContentTypeEnum
    estimated_minutes:  Optional[int] = Field(None, ge=1, le=600)
    prerequisites:      list[str]     = Field(default_factory=list)


class UpdateModuleRequest(BaseModel):
    """PATCH /api/v1/courses/{courseId}/modules/{moduleId}"""
    title:             Optional[str]              = Field(None, min_length=3, max_length=200)
    estimated_minutes: Optional[int]              = Field(None, ge=1, le=600)
    prerequisites:     Optional[list[str]]        = None
    status:            Optional[CourseStatusEnum] = None


class ModuleSummary(BaseModel):
    """Lightweight module object used in list responses."""
    module_id:          str
    title:              str
    content_type:       ContentTypeEnum
    status:             CourseStatusEnum
    estimated_minutes:  Optional[int]   = None
    prerequisites:      list[str]       = Field(default_factory=list)
    quiz_id:            Optional[str]   = None


class ModuleResponse(BaseModel):
    """GET /api/v1/courses/{courseId}/modules/{moduleId}"""
    module_id:         str
    title:             str
    content_type:      ContentTypeEnum
    status:            CourseStatusEnum
    content_url:       Optional[str]          = None   # pre-signed S3 URL for PDF
    video_url:         Optional[str]          = None   # CloudFront HLS URL
    transcript_url:    Optional[str]          = None   # WebVTT S3 key
    quiz_id:           Optional[str]          = None
    estimated_minutes: Optional[int]          = None
    prerequisites:     list[str]              = Field(default_factory=list)
    ingestion_status:  IngestionStatusEnum    = IngestionStatusEnum.PENDING


class ModuleListResponse(BaseModel):
    """GET /api/v1/courses/{courseId}/modules"""
    modules: list[ModuleSummary]


class CreateModuleResponse(BaseModel):
    """POST /api/v1/courses/{courseId}/modules — 201"""
    module_id:        str
    title:            str
    status:           CourseStatusEnum    = CourseStatusEnum.DRAFT
    ingestion_status: IngestionStatusEnum = IngestionStatusEnum.PENDING


# ─────────────────────────────────────────────────────
# CONTENT UPLOAD SCHEMAS
# ─────────────────────────────────────────────────────

class ContentPresignRequest(BaseModel):
    """POST /api/v1/courses/{courseId}/modules/{moduleId}/content/presign"""
    file_name:    str           = Field(..., description="Original filename e.g. lecture_week3.pdf")
    file_type:    str           = Field(..., description="pdf | video")
    content_type: ContentTypeEnum


class ContentPresignResponse(BaseModel):
    """Response from presign endpoint — browser uses upload_url to PUT directly to S3."""
    upload_url:        str
    s3_key:            str
    expires_in_seconds: int = 900


class ContentCompleteRequest(BaseModel):
    """POST /api/v1/courses/{courseId}/modules/{moduleId}/content/complete"""
    s3_key:       str
    content_type: ContentTypeEnum


class ContentCompleteResponse(BaseModel):
    module_id:        str
    ingestion_status: IngestionStatusEnum = IngestionStatusEnum.PROCESSING


class SaveTextContentRequest(BaseModel):
    """PUT /api/v1/courses/{courseId}/modules/{moduleId}/content/text"""
    content: str = Field(..., description="Markdown string from BlockNote editor")


class SaveTextContentResponse(BaseModel):
    module_id:        str
    saved_at:         str
    ingestion_status: IngestionStatusEnum = IngestionStatusEnum.PROCESSING


# ─────────────────────────────────────────────────────
# STUDENT SCHEMAS
# ─────────────────────────────────────────────────────

class StudentProfileResponse(BaseModel):
    """GET /api/v1/students/me and GET /api/v1/students/{studentId}"""
    cognito_sub:       str
    student_id:        str
    name:              str
    email:             str
    domain:            DomainEnum
    grade:             str
    enrollment_status: str
    last_active_at:    Optional[str] = None


class EnrolledCourse(BaseModel):
    """Used in student enrolment list."""
    course_id:      str
    title:          str
    enrolled_at:    str
    status:         str
    completion_pct: int = 0


class StudentEnrolmentsResponse(BaseModel):
    """GET /api/v1/students/me/courses"""
    enrolments: list[EnrolledCourse]


class EnrolStudentsRequest(BaseModel):
    """POST /api/v1/courses/{courseId}/enrolments"""
    student_ids: list[str] = Field(..., min_length=1, description="List of institution student IDs")


class EnrolStudentsResponse(BaseModel):
    """POST /api/v1/courses/{courseId}/enrolments — 201"""
    enrolled: list[str]
    failed:   list[str] = Field(default_factory=list)


class CourseStudentSummary(BaseModel):
    """Used in course student roster."""
    cognito_sub: str
    student_id:  str
    name:        str
    email:       str
    enrolled_at: str
    status:      str


class CourseStudentListResponse(BaseModel):
    """GET /api/v1/courses/{courseId}/students"""
    students:    list[CourseStudentSummary]
    next_cursor: Optional[str] = None


# ─────────────────────────────────────────────────────
# PROGRESS SCHEMAS
# ─────────────────────────────────────────────────────

class UpdateProgressRequest(BaseModel):
    """PUT /api/v1/students/me/courses/{courseId}/modules/{moduleId}/progress"""
    completion_pct:    int = Field(..., ge=0, le=100)
    status:            str = Field(..., description="not_started | in_progress | completed")
    time_spent_seconds: int = Field(..., ge=0)


class UpdateProgressResponse(BaseModel):
    module_id:      str
    completion_pct: int
    status:         str
    updated_at:     str


class ModuleProgressSummary(BaseModel):
    module_id:      str
    title:          str
    status:         str
    completion_pct: int
    started_at:     Optional[str] = None
    completed_at:   Optional[str] = None


class StudentCourseProgressResponse(BaseModel):
    """GET /api/v1/students/me/courses/{courseId}/progress"""
    course_id: str
    modules:   list[ModuleProgressSummary]


class ModuleProgressDetailResponse(BaseModel):
    """GET /api/v1/students/me/courses/{courseId}/modules/{moduleId}/progress"""
    module_id:                str
    status:                   str
    completion_pct:           int
    started_at:               Optional[str] = None
    completed_at:             Optional[str] = None
    time_spent_seconds:       int           = 0
    tutor_interactions_count: int           = 0


class StudentProgressInCourse(BaseModel):
    """Used in teacher progress view."""
    student_id: str
    name:       str
    modules:    list[ModuleProgressSummary]


class CourseProgressResponse(BaseModel):
    """GET /api/v1/courses/{courseId}/progress"""
    students: list[StudentProgressInCourse]


# ─────────────────────────────────────────────────────
# QUIZ SCHEMAS
# ─────────────────────────────────────────────────────

class QuizOption(BaseModel):
    id:   str
    text: str


class QuizQuestionForTeacher(BaseModel):
    """Full question including correct answers — teacher only."""
    id:          str
    type:        QuestionTypeEnum
    text:        str
    options:     list[QuizOption]
    correct_ids: list[str]
    explanation: str
    concept:     str
    difficulty:  str


class QuizQuestionForStudent(BaseModel):
    """Question without correct answers — student facing."""
    id:      str
    type:    QuestionTypeEnum
    text:    str
    options: list[QuizOption]


class QuizDefinitionResponse(BaseModel):
    """GET /api/v1/courses/{courseId}/modules/{moduleId}/quiz"""
    quiz_id:            str
    title:              str
    question_count:     int
    time_limit_seconds: Optional[int] = None
    max_attempts:       int
    passing_score_pct:  int
    randomise_order:    bool


class SaveQuizRequest(BaseModel):
    """PUT /api/v1/courses/{courseId}/modules/{moduleId}/quiz"""
    title:              str               = Field(..., min_length=3, max_length=200)
    questions:          list[QuizQuestionForTeacher]
    time_limit_seconds: Optional[int]     = Field(None, ge=60, le=7200)
    max_attempts:       int               = Field(default=2, ge=1, le=5)
    passing_score_pct:  int               = Field(default=60, ge=0, le=100)
    randomise_order:    bool              = True
    status:             CourseStatusEnum  = CourseStatusEnum.DRAFT


class SaveQuizResponse(BaseModel):
    quiz_id:    str
    status:     CourseStatusEnum
    updated_at: str


class GenerateQuizRequest(BaseModel):
    """POST /api/v1/courses/{courseId}/modules/{moduleId}/quiz/generate"""
    num_questions: int = Field(default=8, ge=3, le=20)
    difficulty:    str = Field(default="medium", description="easy | medium | hard")


class GenerateQuizResponse(BaseModel):
    """Returns full draft including correct_ids — teacher only."""
    quiz_id:   str
    questions: list[QuizQuestionForTeacher]


class QuizAttemptResponse(BaseModel):
    """GET /api/v1/courses/{courseId}/modules/{moduleId}/quiz/attempt — student facing"""
    quiz_id:            str
    title:              str
    time_limit_seconds: Optional[int]           = None
    questions:          list[QuizQuestionForStudent]


class QuizAnswer(BaseModel):
    question_id:  str
    selected_ids: list[str]


class SubmitQuizRequest(BaseModel):
    """POST /api/v1/courses/{courseId}/modules/{moduleId}/quiz/submit"""
    quiz_id:            str
    answers:            list[QuizAnswer]
    time_taken_seconds: int = Field(..., ge=0)


class QuizAnswerResult(BaseModel):
    """Per-question result returned after submission."""
    id:          str
    correct:     bool
    explanation: str


class SubmitQuizResponse(BaseModel):
    """POST /api/v1/courses/{courseId}/modules/{moduleId}/quiz/submit"""
    attempt_id:     str
    score_pct:      int
    passed:         bool
    concept_scores: dict[str, float]   # concept → score 0.0–1.0
    questions:      list[QuizAnswerResult]


class QuizAttemptSummary(BaseModel):
    attempt_id:         str
    score_pct:          int
    passed:             bool
    submitted_at:       str
    time_taken_seconds: int


class StudentQuizResultsResponse(BaseModel):
    """GET /api/v1/students/me/.../quiz/results"""
    attempts: list[QuizAttemptSummary]


class StudentResultSummary(BaseModel):
    """Used in teacher's class quiz results view."""
    student_id:    str
    name:          str
    score_pct:     int
    passed:        bool
    submitted_at:  str
    attempt_count: int


class CourseQuizResultsResponse(BaseModel):
    """GET /api/v1/courses/{courseId}/modules/{moduleId}/quiz/results"""
    results:     list[StudentResultSummary]
    next_cursor: Optional[str] = None


# ─────────────────────────────────────────────────────
# TUTOR SCHEMAS
# ─────────────────────────────────────────────────────

class TutorContext(BaseModel):
    """Context sent with each tutor message — used for RAG grounding."""
    course_id:    str
    module_id:    str
    current_page: Optional[int] = None   # current PDF page or doc section


class TutorChatRequest(BaseModel):
    """POST /api/v1/tutor/chat"""
    message: str     = Field(..., min_length=1, max_length=2000)
    context: TutorContext


class TutorMessage(BaseModel):
    role:      str   # user | assistant
    content:   str
    timestamp: str


class TutorHistoryResponse(BaseModel):
    """GET /api/v1/tutor/history"""
    messages: list[TutorMessage]


# ─────────────────────────────────────────────────────
# GAP & LEARNING PATH SCHEMAS
# ─────────────────────────────────────────────────────

class GapSummary(BaseModel):
    """
    Student-facing gap — raw severity score not exposed.
    Instead shows a human-readable label.
    """
    concept_id:     str
    concept_name:   str
    status:         str   # needs-attention | developing | strong
    last_updated_at: str


class StudentGapsResponse(BaseModel):
    """GET /api/v1/students/me/gaps"""
    gaps: list[GapSummary]


class ConceptGapDetail(BaseModel):
    """Used in teacher gap heatmap."""
    concept_id:    str
    concept_name:  str
    avg_severity:  float
    at_risk_count: int


class CourseGapsResponse(BaseModel):
    """GET /api/v1/courses/{courseId}/gaps — teacher heatmap"""
    concepts: list[ConceptGapDetail]


class RecommendedModule(BaseModel):
    module_id: str
    title:     str
    rationale: str


class LearningPathResponse(BaseModel):
    """GET /api/v1/students/me/courses/{courseId}/learning-path"""
    course_id:            str
    recommended_modules:  list[RecommendedModule]
    current_module_id:    str
    generated_at:         str
    expires_at:           str


# ─────────────────────────────────────────────────────
# TEACHER SCHEMAS
# ─────────────────────────────────────────────────────

class TeacherCourseSummary(BaseModel):
    course_id:    str
    title:        str
    domain:       DomainEnum
    student_count: int
    at_risk_count: int
    avg_mastery:   float


class TeacherCoursesResponse(BaseModel):
    """GET /api/v1/teachers/me/courses"""
    courses: list[TeacherCourseSummary]


class AtRiskStudent(BaseModel):
    student_id: str
    name:       str
    gaps:       list[dict[str, Any]]


class AtRiskResponse(BaseModel):
    """GET /api/v1/courses/{courseId}/at-risk"""
    at_risk_students: list[AtRiskStudent]


class DashboardResponse(BaseModel):
    """
    GET /api/v1/courses/{courseId}/dashboard
    Composite response — all faculty dashboard data in one call.
    """
    course:              CourseResponse
    student_count:       int
    completion_summary:  dict[str, Any]   # module_id → avg_completion_pct
    at_risk_students:    list[AtRiskStudent]
    top_gaps:            list[ConceptGapDetail]
    module_effectiveness: list[dict[str, Any]]  # module_id → avg_score_delta


# ─────────────────────────────────────────────────────
# ADMIN SCHEMAS
# ─────────────────────────────────────────────────────

class UserSummary(BaseModel):
    cognito_sub:    str
    name:           str
    email:          str
    role:           RoleEnum
    status:         str
    last_active_at: Optional[str] = None


class UserListResponse(BaseModel):
    """GET /api/v1/admin/users"""
    users:       list[UserSummary]
    next_cursor: Optional[str] = None


class ChangeRoleRequest(BaseModel):
    """POST /api/v1/admin/users/{userId}/role"""
    role: RoleEnum


class ChangeRoleResponse(BaseModel):
    user_id:    str
    role:       RoleEnum
    updated_at: str


class AssignTeacherRequest(BaseModel):
    """POST /api/v1/admin/courses/{courseId}/teachers"""
    cognito_sub: str
    role:        str = Field(default="lead", description="lead | assistant")


class AssignTeacherResponse(BaseModel):
    course_id:   str
    teacher_sub: str
    role:        str
    assigned_at: str


class UpdateCMSPluginRequest(BaseModel):
    """PUT /api/v1/admin/config/cms-plugin"""
    plugin_type:   str  = Field(..., description="s3 | google_classroom | strapi | custom")
    field_mapping: dict = Field(default_factory=dict)


class CMSPluginConfigResponse(BaseModel):
    """GET /api/v1/admin/config/cms-plugin"""
    plugin_type:   str
    field_mapping: dict
    updated_at:    str
    updated_by:    str


class UpdateDomainConfigRequest(BaseModel):
    """PUT /api/v1/admin/config/domain"""
    domain_type:          str
    tutor_persona:        Optional[str]       = None
    model_id:             Optional[str]       = None
    temperature:          Optional[float]     = Field(None, ge=0.0, le=1.0)
    max_tokens:           Optional[int]       = Field(None, ge=100, le=4096)
    content_restrictions: Optional[list[str]] = None


class DomainConfigResponse(BaseModel):
    """GET /api/v1/admin/config/domain"""
    domain_type:          str
    tutor_persona:        str
    model_id:             str
    temperature:          float
    max_tokens:           int
    age_group:            str
    content_restrictions: list[str]


# ─────────────────────────────────────────────────────
# CMS SYNC SCHEMAS
# ─────────────────────────────────────────────────────

class TriggerSyncRequest(BaseModel):
    """POST /api/v1/admin/cms/sync"""
    course_ids: Optional[list[str]] = Field(
        None,
        description="Specific course IDs to sync. If omitted all courses are synced."
    )


class TriggerSyncResponse(BaseModel):
    job_id:                    str
    status:                    str = "started"
    estimated_duration_seconds: int


class SyncJobStatusResponse(BaseModel):
    """GET /api/v1/admin/cms/sync/{jobId}"""
    job_id:          str
    status:          str   # running | complete | failed
    courses_synced:  int   = 0
    modules_synced:  int   = 0
    errors:          list[str] = Field(default_factory=list)
    completed_at:    Optional[str] = None


class IngestionStatusResponse(BaseModel):
    """GET /api/v1/courses/{courseId}/modules/{moduleId}/ingestion-status"""
    module_id:        str
    ingestion_status: IngestionStatusEnum
    kb_document_id:   Optional[str] = None
    ingested_at:      Optional[str] = None
    error_message:    Optional[str] = None


# ─────────────────────────────────────────────────────
# PARENT SCHEMAS (K-12)
# ─────────────────────────────────────────────────────

class ChildCourseSummary(BaseModel):
    course_id: str
    title:     str


class ChildSummary(BaseModel):
    student_id: str
    name:       str
    grade:      str
    courses:    list[ChildCourseSummary]


class ParentChildrenResponse(BaseModel):
    """GET /api/v1/parent/children"""
    children: list[ChildSummary]


class ChildCourseProgress(BaseModel):
    course_id:      str
    title:          str
    completion_pct: int
    last_active_at: Optional[str] = None


class ChildProgressResponse(BaseModel):
    """GET /api/v1/parent/children/{studentId}/progress"""
    student_id: str
    courses:    list[ChildCourseProgress]


class CreateParentLinkRequest(BaseModel):
    """POST /api/v1/admin/parent-links"""
    parent_email:     EmailStr
    child_student_id: str


class CreateParentLinkResponse(BaseModel):
    parent_sub:  str
    child_sub:   str
    linked_at:   str
