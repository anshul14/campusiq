# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


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
class CPIMetadata:
    """
    Typed metadata carried by all CPI content objects.
    Replaces the loosely typed dict — every plugin must
    populate these fields. Maps directly to DynamoDB
    module and ingestion manifest attributes.
    """
    domain:          str                    # university | k12 | corporate
    difficulty:      str                    # beginner | intermediate | advanced
    content_type:    ContentType
    last_updated:    str                    # ISO 8601 timestamp
    cms_source:      str                    # s3 | google_classroom | strapi | custom
    cms_course_id:   Optional[str] = None   # original ID in the source CMS
    cms_module_id:   Optional[str] = None
    estimated_minutes: Optional[int] = None
    prerequisites:   list[str] = field(default_factory=list)


@dataclass
class CPIContent:
    """
    Standard content object returned by all CMS plugins.
    Maps directly to the Module record in DynamoDB and
    the S3 content storage structure.
    """
    content_id:      str           # CampusIQ module ID
    title:           str
    content_type:    ContentType
    metadata:        CPIMetadata
    source:          str           # which plugin produced this
    request_id:      str

    # Content payload — only one of these is populated
    # depending on content_type
    body:            Optional[str] = None   # markdown text (MARKDOWN type)
    content_url:     Optional[str] = None   # S3 key (PDF type)
    video_url:       Optional[str] = None   # CloudFront HLS URL (VIDEO type)
    transcript_url:  Optional[str] = None   # WebVTT S3 key (VIDEO type)

    # Supporting media — images embedded in markdown, etc.
    media_urls:      list[str] = field(default_factory=list)


@dataclass
class CPIRequest:
    """
    Standard request object passed to all CMS plugin actions.
    """
    action:          str           # fetchContent | searchContent | listCourses
                                   # getMetadata | ingestContent
    course_id:       Optional[str] = None
    module_id:       Optional[str] = None
    query:           Optional[str] = None
    filters:         Optional[dict] = None
    request_id:      Optional[str] = None


@dataclass
class CPIIngestionResult:
    """
    Return type for ingest_content action.
    Maps directly to the ingestion manifest record in DynamoDB.
    """
    module_id:        str
    s3_key:           str
    ingestion_status: IngestionStatus
    kb_document_id:   Optional[str] = None   # Bedrock KB doc ID once indexed
    ingested_at:      Optional[str] = None   # ISO 8601
    error_message:    Optional[str] = None


class ContentPluginInterface(ABC):
    """
    Abstract base class for all CampusIQ CMS plugins.

    Every CMS plugin must implement this interface.
    The plugin is responsible for:
    1. Fetching content from the source CMS
    2. Transforming it into the standard CPIContent format
    3. Triggering ingestion into the CampusIQ S3 + KB pipeline

    The plugin never writes to DynamoDB directly.
    DynamoDB writes are handled by the ingestion Lambda
    that calls the plugin.
    """

    @abstractmethod
    def fetch_content(self, request: CPIRequest) -> CPIContent:
        raise NotImplementedError

    @abstractmethod
    def search_content(self, request: CPIRequest) -> list[CPIContent]:
        raise NotImplementedError

    @abstractmethod
    def list_courses(self, request: CPIRequest) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def get_metadata(self, request: CPIRequest) -> CPIMetadata:
        raise NotImplementedError

    @abstractmethod
    def ingest_content(self, request: CPIRequest) -> CPIIngestionResult:
        raise NotImplementedError
