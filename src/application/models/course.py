# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from src.application.models import dynamodb_keys as keys


class CourseStatus(str, Enum):
    DRAFT     = "draft"
    PUBLISHED = "published"
    ARCHIVED  = "archived"


class CMSSource(str, Enum):
    S3                = "s3"
    GOOGLE_CLASSROOM  = "google_classroom"
    STRAPI            = "strapi"
    CUSTOM            = "custom"


class ContentType(str, Enum):
    MARKDOWN = "markdown"
    PDF      = "pdf"
    VIDEO    = "video"


class IngestionStatus(str, Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    COMPLETE   = "complete"
    FAILED     = "failed"


@dataclass
class Course:
    """
    Represents a course in CampusIQ.

    DynamoDB:
        PK = COURSE#{course_id}
        SK = METADATA
    """
    course_id:     str
    title:         str
    description:   str
    domain:        str                    # university | k12 | corporate
    difficulty:    str                    # beginner | intermediate | advanced
    status:        CourseStatus
    created_by:    str                    # TEACHER#{cognitoSub}
    created_at:    str                    # ISO 8601
    updated_at:    str                    # ISO 8601
    module_order:  list[str]             = field(default_factory=list)
    cms_source:    CMSSource             = CMSSource.S3
    cms_course_id: Optional[str]         = None   # original ID in source CMS

    # DynamoDB key helpers
    @property
    def pk(self) -> str:
        return keys.course_pk(self.course_id)

    @property
    def sk(self) -> str:
        return keys.metadata_sk()


@dataclass
class Module:
    """
    Represents a module (lesson unit) within a course.

    DynamoDB:
        PK = COURSE#{course_id}
        SK = MODULE#{module_id}
    """
    course_id:          str
    module_id:          str
    title:              str
    content_type:       ContentType
    status:             CourseStatus
    created_by:         str              # TEACHER#{cognitoSub}
    created_at:         str              # ISO 8601
    updated_at:         str              # ISO 8601

    # Content URLs — only the relevant field is populated per content_type
    content_url:        Optional[str]    = None   # S3 key for markdown or PDF
    video_url:          Optional[str]    = None   # CloudFront HLS URL
    transcript_url:     Optional[str]    = None   # WebVTT S3 key

    # Quiz linkage
    quiz_id:            Optional[str]    = None

    # Metadata
    prerequisites:      list[str]        = field(default_factory=list)
    estimated_minutes:  Optional[int]    = None
    ingestion_status:   IngestionStatus  = IngestionStatus.PENDING

    @property
    def pk(self) -> str:
        return keys.course_pk(self.course_id)

    @property
    def sk(self) -> str:
        return keys.module_sk(self.module_id)
