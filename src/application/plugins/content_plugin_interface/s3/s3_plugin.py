# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
S3 Content Plugin — src/application/plugins/content_plugin_interface/s3_plugin.py

Default CPI plugin (ARCHITECTURE.md 4.2). No external CMS — content lives
in the institution's own S3 bucket, following the convention-based path:

    {domain}/{courseId}/modules/{moduleId}/content.{ext}

SCOPE OF THIS BUILD — markdown and PDF only. Video's path structure
(raw-uploads/ -> MediaConvert -> HLS + Transcribe -> WebVTT) is a
separate, still-unconfirmed pipeline (transcript_s3_key field name
unresolved — no real video content exists yet to test against).
fetch_content/get_metadata raise ContentNotFoundError for video paths;
this is a known, deliberate gap, not silent mishandling.

DOMAIN RESOLUTION — the real design problem this file had to solve.
fetch_content(course_id, module_id) has no domain parameter (it's the
shared abstract signature every plugin implements identically), but the
S3 key needs domain as its first path segment. Domain is NOT discovered
from S3 structure — it's a closed, Pydantic-enforced set
(application.schemas.DomainEnum: university/k12/corporate), validated at
course creation and immutable afterward (CreateCourseRequest requires
it, UpdateCourseRequest excludes it). So resolution here is a bounded
probe: 3 known domains x 2 known extensions = at most 6 head_object
calls, each metadata-only (no body transfer). Same "small, bounded scale
-> brute force beats a discovery service" reasoning already used to
reject Personalize for module reordering. DomainEnum is imported
directly, not mirrored as a duplicate constant — domain is a CampusIQ
platform concept this plugin borrows, decided explicitly, not defaulted.

METADATA — domain/difficulty come from S3 custom metadata tags
(x-amz-meta-domain, x-amz-meta-difficulty), NOT faked with defaults if
missing. A missing tag returns None, surfacing the real upstream gap
(the Content Upload Handler Lambda, not yet built, doesn't set these
tags in its current doc spec — flagged separately) rather than masking
it with a guess. domain in particular drives Bedrock Guardrails profile
selection, so a wrong default would be a safety-relevant bug.
ingest_content() is the one exception: since it already writes to
DynamoDB, it falls back to the course's own COURSE# record when S3
metadata is absent.

title resolution — a lower-stakes gap than domain/difficulty (cosmetic,
not safety/routing-relevant), so handled with a plain fallback rather
than a None + upstream-fix flag: reads x-amz-meta-title if the Content
Upload Handler ever sets it, otherwise derives a human-readable title
from module_id (e.g. "week3-newtons-laws" -> "Week3 Newtons Laws").
Worth reviewing once real content and a real title tag exist.

INGESTION — two distinct paths, only one of which ingest_content() here
actually serves:
    Path A (native creation via CampusIQ's own Content Upload Handler)
        bypasses this plugin entirely — writes straight to S3, KB
        auto-sync fires on the ObjectCreated event, gated on
        status=published. Not this plugin's concern.
    Path B (admin-triggered backfill of pre-existing content) is what
        ingest_content() is for: list_courses -> list_modules ->
        ingest_content per module. Needed because pre-existing objects
        never fire a *new* ObjectCreated event — same delta-only gap
        already caught with Google Classroom's Pub/Sub webhook.
Bedrock KB isn't provisioned yet, so the actual KB-ingestion-job trigger
is a clearly marked stub. The DynamoDB write (via
dynamodb.upsert_module_from_ingestion — the service layer, not inline
boto3) is real and functional today.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import boto3
from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError

from application.schemas import DomainEnum
from application.services import dynamodb  # service layer — adjust import to match actual repo layout
from ..base import (
    ContentPlugin,
    ContentNotFoundError,
    CPIContent,
    CPIMetadata,
    CPIIngestionResult,
    ContentType,
    IngestionStatus,
)

logger = Logger(service="s3-cpi-plugin")

# Module-level client — ADR-012 pattern: created once on cold start,
# reused across warm invocations. Never create clients inside methods.
s3_client = boto3.client("s3")

# The only domains that can ever legitimately exist. Imported from the
# single source of truth (application.schemas.DomainEnum), not
# duplicated — see module docstring.
_KNOWN_DOMAINS = [d.value for d in DomainEnum]

# Extensions this build supports — video deliberately excluded, see
# module docstring.
_EXT_TO_CONTENT_TYPE = {"md": ContentType.MARKDOWN, "pdf": ContentType.PDF}


def _content_key(domain: str, course_id: str, module_id: str, ext: str) -> str:
    """Builds the convention-based S3 key (ARCHITECTURE.md 4.2)."""
    return f"{domain}/{course_id}/modules/{module_id}/content.{ext}"


def _humanize_module_id(module_id: str) -> str:
    """Fallback title when no x-amz-meta-title tag exists. Cosmetic only."""
    return module_id.replace("-", " ").replace("_", " ").title()


def _probe_object(bucket: str, course_id: str, module_id: str) -> tuple[str, str, dict] | None:
    """
    Resolves (domain, extension, head_object response) for a
    course_id/module_id pair by probing the known domain x extension
    space. Returns None if nothing is found in any combination.
    """
    for domain in _KNOWN_DOMAINS:
        for ext in _EXT_TO_CONTENT_TYPE:
            key = _content_key(domain, course_id, module_id, ext)
            try:
                response = s3_client.head_object(Bucket=bucket, Key=key)
                return domain, ext, response
            except ClientError as e:
                error_code = e.response["Error"]["Code"]
                if error_code in ("404", "NoSuchKey", "NotFound"):
                    continue
                logger.error("head_object failed during probe", extra={
                    "error_code": error_code, "course_id": course_id, "module_id": module_id,
                })
                raise
    return None


def _build_metadata(head_response: dict, ext: str, course_id: str) -> CPIMetadata:
    """
    Builds CPIMetadata from a head_object response. domain/difficulty
    are None if their tags are absent — deliberate, see module
    docstring. boto3 lower-cases custom metadata keys automatically.
    """
    s3_meta = head_response.get("Metadata", {})
    return CPIMetadata(
        domain=s3_meta.get("domain"),          # None if not set — by design
        difficulty=s3_meta.get("difficulty"),  # None if not set — by design
        content_type=_EXT_TO_CONTENT_TYPE[ext],
        last_updated=head_response.get("LastModified", datetime.now(timezone.utc)),
        cms_source="s3",
        cms_course_id=course_id,
    )


class S3Plugin(ContentPlugin):
    """
    Default CPI plugin. Institutions with no external CMS use this —
    content is created directly in CampusIQ (BlockNote editor / PDF /
    video upload) and stored in the institution's own S3 bucket.
    """

    def __init__(self, config: dict):
        """
        Standardised constructor (Aug 2026) — every CPI plugin takes a
        single config dict from campusiq.config.json (plugins.s3), so
        a future plugin registry can construct any plugin uniformly:
        PluginClass(config=plugin_config_block), no special-casing per
        CMS. Fails loudly on a missing required key rather than
        surfacing a confusing error later, mid-request.

        Args:
            config: e.g. {"bucket_name": "campusiq-vnit-dev-content"}
        """
        try:
            self.bucket_name = config["bucket_name"]
        except KeyError:
            raise ValueError("S3Plugin config missing required key 'bucket_name'")

    # ------------------------------------------------------------------
    def fetch_content(self, course_id: str, module_id: str) -> CPIContent:
        probe = _probe_object(self.bucket_name, course_id, module_id)
        if probe is None:
            raise ContentNotFoundError(
                f"No markdown or PDF content found for course_id={course_id!r} "
                f"module_id={module_id!r} in any of {_KNOWN_DOMAINS}. "
                f"(Video content is not yet supported by this plugin.)"
            )
        domain, ext, head_response = probe
        key = _content_key(domain, course_id, module_id, ext)
        metadata = _build_metadata(head_response, ext, course_id)
        s3_meta = head_response.get("Metadata", {})
        title = s3_meta.get("title") or _humanize_module_id(module_id)

        content = CPIContent(
            content_id=f"{course_id}#{module_id}",
            title=title,
            content_type=_EXT_TO_CONTENT_TYPE[ext],
            metadata=metadata,
        )

        if ext == "md":
            # Markdown body is small enough to read fully — CPIContent.body
            # carries the actual text (ARCHITECTURE.md 4.1).
            obj = s3_client.get_object(Bucket=self.bucket_name, Key=key)
            content.body = obj["Body"].read().decode("utf-8")
        elif ext == "pdf":
            # PDF: content_url carries the S3 key itself, not the bytes
            # (ARCHITECTURE.md 4.1) — the platform fetches/presigns
            # separately when actually needed.
            content.content_url = key

        return content

    # ------------------------------------------------------------------
    def get_metadata(self, content_id: str) -> CPIMetadata:
        course_id, module_id = self._parse_content_id(content_id)
        probe = _probe_object(self.bucket_name, course_id, module_id)
        if probe is None:
            raise ContentNotFoundError(f"No content found for content_id={content_id!r}")
        domain, ext, head_response = probe
        return _build_metadata(head_response, ext, course_id)

    # ------------------------------------------------------------------
    def list_courses(self) -> list[dict]:
        """
        Enumerates {domain}/{courseId}/ prefixes across all known
        domains. title isn't resolvable from S3 alone (no course-level
        manifest exists in the convention) — callers needing a real
        title should cross-reference DynamoDB's COURSE# record; this
        method is a discovery/backfill primitive, not a full course read.
        """
        courses = []
        for domain in _KNOWN_DOMAINS:
            for course_id in self._list_common_prefixes(f"{domain}/"):
                courses.append({
                    "course_id": course_id,
                    "domain": domain,
                    "title": course_id,  # best-effort placeholder — see docstring
                })
        return courses

    # ------------------------------------------------------------------
    def list_modules(self, course_id: str) -> list[dict]:
        """
        Enumerates modules within a course by probing each known domain
        for a {domain}/{courseId}/modules/ prefix (course_id alone
        doesn't tell us the domain — same resolution problem as
        fetch_content, solved the same bounded way).
        """
        for domain in _KNOWN_DOMAINS:
            prefix = f"{domain}/{course_id}/modules/"
            module_ids = self._list_common_prefixes(prefix)
            if module_ids:
                modules = []
                for module_id in module_ids:
                    ext = self._find_content_extension(domain, course_id, module_id)
                    if ext is None:
                        continue  # e.g. a video-only module — not yet supported, skip rather than fail the whole listing
                    modules.append({
                        "module_id": module_id,
                        "title": _humanize_module_id(module_id),
                        "content_type": _EXT_TO_CONTENT_TYPE[ext].value,
                    })
                return modules
        return []  # course_id not found under any known domain

    # ------------------------------------------------------------------
    def search_content(self, query: str, filters: dict | None = None) -> list[CPIContent]:
        """
        Lightweight title/module_id substring match — S3 has no native
        search capability. Deliberately does NOT fetch and scan full
        module bodies (expensive, and real semantic search is Bedrock
        KB's job once provisioned, not CPI's). filters={"course_id": ...}
        scopes the search to one course; omitted, it searches across
        every discoverable course (bounded — small-scale deployment).
        """
        filters = filters or {}
        query_lower = query.lower()
        course_ids = (
            [filters["course_id"]] if "course_id" in filters
            else [c["course_id"] for c in self.list_courses()]
        )

        matches = []
        for course_id in course_ids:
            for module in self.list_modules(course_id):
                title = module["title"]
                if query_lower in title.lower() or query_lower in module["module_id"].lower():
                    try:
                        matches.append(self.fetch_content(course_id, module["module_id"]))
                    except ContentNotFoundError:
                        continue  # listed but not fetchable (e.g. race with a delete) — skip, don't fail the whole search
        return matches

    # ------------------------------------------------------------------
    def ingest_content(self, course_id: str, module_id: str) -> CPIIngestionResult:
        """
        Path B only (admin-triggered backfill) — see module docstring.
        Writes/refreshes the MODULE# DynamoDB record via the service
        layer. KB-ingestion-job trigger is a stub until Bedrock KB is
        provisioned — explicit trigger is required here (not just the
        automatic S3-event trigger) precisely because backfilled objects
        are pre-existing, so no new ObjectCreated event will ever fire
        for them.
        """
        now = datetime.now(timezone.utc).isoformat()
        probe = _probe_object(self.bucket_name, course_id, module_id)
        if probe is None:
            return CPIIngestionResult(
                module_id=module_id,
                s3_key="",
                ingestion_status=IngestionStatus.FAILED,
                error_message=f"No markdown or PDF content found for course_id={course_id!r} module_id={module_id!r}",
            )

        domain, ext, head_response = probe
        key = _content_key(domain, course_id, module_id, ext)
        s3_meta = head_response.get("Metadata", {})

        resolved_domain = s3_meta.get("domain")
        resolved_difficulty = s3_meta.get("difficulty")
        if resolved_domain is None or resolved_difficulty is None:
            # The one place this plugin is allowed to fall back to
            # DynamoDB — see module docstring. ingest_content() already
            # owns the DynamoDB write, so this isn't a new boundary
            # crossing, just completing the one it already makes.
            course = dynamodb.get_course_by_id(course_id)
            if course is not None:
                resolved_domain = resolved_domain or course.get("domain")
                resolved_difficulty = resolved_difficulty or course.get("difficulty")

        title = s3_meta.get("title") or _humanize_module_id(module_id)

        try:
            dynamodb.upsert_module_from_ingestion(
                course_id=course_id,
                module_id=module_id,
                content_s3_key=key,
                content_type=_EXT_TO_CONTENT_TYPE[ext].value,
                domain=resolved_domain,
                difficulty=resolved_difficulty,
                ingestion_status=IngestionStatus.COMPLETE.value,
                title=title,
                now=now,
            )
        except ClientError as e:
            return CPIIngestionResult(
                module_id=module_id,
                s3_key=key,
                ingestion_status=IngestionStatus.FAILED,
                error_message=str(e),
            )

        # TODO: once Bedrock KB is provisioned, explicitly trigger a KB
        # ingestion job here (e.g. bedrock_agent_client.start_ingestion_job)
        # rather than relying on the automatic S3-event trigger, which
        # never fires for objects that already existed before KB started
        # watching this prefix. Tracked, not blocking this build.

        return CPIIngestionResult(
            module_id=module_id,
            s3_key=key,
            ingestion_status=IngestionStatus.COMPLETE,
            ingested_at=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_content_id(content_id: str) -> tuple[str, str]:
        if "#" not in content_id:
            raise ValueError(f"Malformed content_id (expected 'course_id#module_id'): {content_id!r}")
        course_id, module_id = content_id.split("#", 1)
        return course_id, module_id

    def _list_common_prefixes(self, prefix: str) -> list[str]:
        """
        Lists the immediate 'folder' names under prefix using S3's
        Delimiter param — S3 has no real directories, but ListObjectsV2
        with Delimiter='/' returns CommonPrefixes that simulate them.
        Paginated via ContinuationToken, same shape as dynamodb.py's
        cursor pattern.
        """
        names = []
        continuation_token = None
        while True:
            kwargs = {"Bucket": self.bucket_name, "Prefix": prefix, "Delimiter": "/"}
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token
            response = s3_client.list_objects_v2(**kwargs)
            for common_prefix in response.get("CommonPrefixes", []):
                # e.g. "university/phys101/" -> "phys101"
                name = common_prefix["Prefix"][len(prefix):].rstrip("/")
                if name:
                    names.append(name)
            if response.get("IsTruncated"):
                continuation_token = response.get("NextContinuationToken")
            else:
                break
        return names

    def _find_content_extension(self, domain: str, course_id: str, module_id: str) -> str | None:
        """Returns which supported extension actually exists for a module, or None."""
        for ext in _EXT_TO_CONTENT_TYPE:
            key = _content_key(domain, course_id, module_id, ext)
            try:
                s3_client.head_object(Bucket=self.bucket_name, Key=key)
                return ext
            except ClientError as e:
                if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                    continue
                raise
        return None