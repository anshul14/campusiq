# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Content Provider Interface (CPI) — src/application/plugins/content_plugin_interface/base.py

Defines the standard contract every CMS plugin must implement. This is
the boundary the platform is built against — CampusIQ's AI layer only
ever talks to CPIContent objects and never needs to know which CMS (or
none at all, for the S3 default) produced them. This is what makes
CampusIQ a framework rather than a platform: the AI layer works without
any CMS-specific modification.

Six required actions per plugin (ARCHITECTURE.md 4.1, plus list_modules
added Aug 2026 — see note below):
    fetch_content    — a single content item by course + module ID
    search_content   — content items matching a query string
    list_courses     — all available courses from the CMS
    list_modules     — all modules/content items within a given course
    get_metadata     — metadata for a specific content item, without
                        fetching the full body
    ingest_content   — triggers ingestion into the KB pipeline

DESIGN NOTE — why list_modules was added: the original 5-method contract
had no way to enumerate what content exists inside a course you haven't
seen before — fetch_content requires an already-known module_id, which a
freshly-connected plugin doesn't have. This blocks initial sync/backfill
entirely: a fresh deployment connecting to a CMS with pre-existing
content (e.g. Google Classroom, where the webhook is delta-only and
never fires for content that existed before registration) would have no
way to discover and ingest that backlog.

DESIGN NOTE — CPIRequest's role: the spec describes CPIRequest as "the
standard request" carrying action/course_id/module_id/query/filters/
request_id together, but doesn't specify whether each method takes a
single CPIRequest or typed individual arguments. This implementation
uses typed individual arguments per method (clearer, self-documenting
for a small fixed set of actions) and treats CPIRequest as a tracing/
logging envelope a caller (e.g. the ingestion Lambda) can construct
alongside a call, not the sole parameter every plugin method receives.

S3 PATH CONVENTION (resolved Aug 2026 — ARCHITECTURE.md 4.2's documented
convention wins over what a couple of pre-existing test fixtures happen
to use): {domain}/{courseId}/modules/{moduleId}/content.{ext}
Two existing test modules (week3-newtons-laws, week5-energy-conservation)
predate this decision and use a flatter path without the modules/
segment — harmless, since nothing in the codebase reconstructs a content
path from course_id/module_id; every read goes through the module's own
stored content_s3_key. New content created via any plugin from here on
follows the nested convention.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ContentType(str, Enum):
    """
    Determines which optional field on CPIContent is populated. Only the
    matching field is ever set — deliberate, so the platform never has
    to guess what kind of content it's holding (ARCHITECTURE.md 4.1).
    """
    MARKDOWN = "markdown"
    PDF = "pdf"
    VIDEO = "video"


class IngestionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class CPIMetadata:
    """
    Typed metadata every CPIContent carries — replaces a loosely typed
    dict per the Master Reference's "Updated Base Class" note.

    domain/difficulty are Optional (Aug 2026 amendment, S3 plugin scoping
    session): a plugin should return None when its source doesn't actually
    carry this information, rather than fake a default. Faking a default
    (e.g. "university" when unknown) would silently mask a real upstream
    gap — domain in particular drives Bedrock Guardrails profile selection,
    so a wrong guess is a safety-relevant bug, not a cosmetic one. Callers
    that need a guaranteed value (e.g. ingest_content(), which already
    writes to DynamoDB) are expected to fall back to the course's own
    COURSE# record when these come back None.
    """
    domain: str | None            # e.g. "university", "k12", "corporate" — None if unknown
    difficulty: str | None        # e.g. "beginner", "intermediate", "advanced" — None if unknown
    content_type: ContentType
    last_updated: datetime
    cms_source: str        # e.g. "s3", "google_classroom", "strapi"
    cms_course_id: str     # the course ID as known to the SOURCE CMS —
                            # not necessarily the same as CampusIQ's own course_id


@dataclass
class CPIContent:
    """
    Standard content object every plugin action that returns content
    must produce. Only the field matching content_type is populated:
    body for markdown, content_url (S3 key) for PDF, video_url (HLS) +
    transcript_url (WebVTT) for video.
    """
    content_id: str
    title: str
    content_type: ContentType
    metadata: CPIMetadata
    body: str | None = None
    content_url: str | None = None
    video_url: str | None = None
    transcript_url: str | None = None


@dataclass
class CPIRequest:
    """
    Standard request envelope — action identifies which of the five
    operations is being invoked, request_id supports tracing/logging
    across a plugin call. Optional fields are populated depending on
    which action is being represented (course_id/module_id for
    fetch_content, query/filters for search_content, etc.).
    """
    action: str
    request_id: str
    course_id: str | None = None
    module_id: str | None = None
    query: str | None = None
    filters: dict = field(default_factory=dict)


@dataclass
class CPIIngestionResult:
    """Return type for ingest_content() — maps directly to the DynamoDB ingestion manifest."""
    module_id: str
    s3_key: str
    ingestion_status: IngestionStatus
    kb_document_id: str | None = None
    ingested_at: datetime | None = None
    error_message: str | None = None


class ContentNotFoundError(Exception):
    """
    Raised by fetch_content/get_metadata when the requested content
    genuinely doesn't exist at the source — distinct from other failures
    (permissions, throttling, malformed input) which should propagate as
    themselves. Shared across all plugins so callers can catch one
    consistent exception regardless of which CMS is behind the plugin.
    """
    pass


class ContentPlugin(ABC):
    """
    Abstract base class every CMS plugin implements. The platform only
    ever calls these six methods — no plugin-specific logic exists
    anywhere else in the codebase. A new CMS integration means
    implementing this contract, nothing more (see the template plugin
    at content_plugin_interface/template/ for a starting point).
    """

    @abstractmethod
    def fetch_content(self, course_id: str, module_id: str) -> CPIContent:
        """Fetch a single content item from the CMS by course and module ID."""
        raise NotImplementedError

    @abstractmethod
    def search_content(self, query: str, filters: dict | None = None) -> list[CPIContent]:
        """Search for content items matching a query string."""
        raise NotImplementedError

    @abstractmethod
    def list_courses(self) -> list[dict]:
        """
        List all available courses from the CMS. Returns plain dicts
        (course_id, title, at minimum) rather than a typed dataclass —
        no CPICourse type is specified anywhere in the docs; this is an
        assumption, worth revisiting if course-level metadata needs grow.
        """
        raise NotImplementedError

    @abstractmethod
    def list_modules(self, course_id: str) -> list[dict]:
        """
        List all modules/content items within a given course. Added
        specifically to make initial sync/backfill possible — without
        this, a plugin has no way to discover what exists inside a
        course it hasn't seen before, since fetch_content requires an
        already-known module_id. Returns plain dicts (module_id, title,
        content_type at minimum) — same reasoning as list_courses for
        not introducing a new typed dataclass without a specified need.
        """
        raise NotImplementedError

    @abstractmethod
    def get_metadata(self, content_id: str) -> CPIMetadata:
        """Return metadata for a specific content item without fetching its full body."""
        raise NotImplementedError

    @abstractmethod
    def ingest_content(self, course_id: str, module_id: str) -> CPIIngestionResult:
        """Trigger ingestion of a content item into the CampusIQ knowledge base pipeline."""
        raise NotImplementedError