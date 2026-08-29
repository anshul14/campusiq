# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Ingestion Lambda — src/application/lambdas/ingestion/handler.py

Invokes CPI plugin methods. This is the only caller of S3Plugin (and any
future CMS plugin) in the deployed system.

Two EventBridge triggers, one code path:

  ModulePublished (course_id, module_id)
    Emitted by the module Publish handler after its own synchronous
    write (MODULE#.status -> published, ingestion_status -> pending).
    One module, known exactly.

  CMSCourseSyncRequested (course_id)
    Emitted by the admin sync-trigger endpoint once per selected course,
    after it has already created that course's COURSE# record
    synchronously (required — ingest_content()'s domain/difficulty
    fallback needs it to exist). One course, modules unknown —
    discovered via list_modules().

Both paths converge on the same call: plugin.ingest_content(course_id,
module_id). Not split into two code paths: ingest_content()'s upsert is
idempotent (if_not_exists on status/entity_type/created_at), so a call
following ModulePublished's own synchronous write is a safe, cheap
re-derivation, not a duplication risk. One code path, at the cost of one
redundant head_object call for the ModulePublished case, is simpler than
maintaining two.

No job-tracking entity — failures are logged (CloudWatch) and surfaced
per-module via MODULE#.ingestion_status. CMSCourseSyncRequested
processes modules independently: one module failing does not abort the
rest of the course's sync.
"""

from __future__ import annotations

import os

from aws_lambda_powertools import Logger

from application.plugins.content_plugin_interface.base import ContentPlugin, IngestionStatus
from application.plugins.content_plugin_interface.s3.s3_plugin import S3Plugin
from application.services import dynamodb as db

logger = Logger(service="ingestion-lambda")


# Plugin registry: cms_source (stored on every COURSE# record) -> plugin
# class. Only "s3" is implemented; google_classroom/strapi are
# unimplemented until real credentials exist to test against.
#
# Config comes from Lambda environment variables, not a config file —
# CDK already knows the bucket name at synth time, so passing it as an
# env var carries no risk of drifting out of sync with a separately
# maintained file.
_PLUGIN_REGISTRY = {
    "s3": lambda: S3Plugin(config={"bucket_name": os.environ["CONTENT_BUCKET_NAME"]}),
}


class UnknownCMSSourceError(Exception):
    """Raised when a course's cms_source has no registered plugin -- e.g.
    google_classroom/strapi before they're built. Distinct from a plugin
    method genuinely failing, so callers can log/handle it differently."""
    pass


def _get_plugin_for_course(course_id: str) -> ContentPlugin:
    course = db.get_course_by_id(course_id)
    if course is None:
        # Should not happen in practice -- CMSCourseSyncRequested is only
        # ever emitted after the admin endpoint creates COURSE# synchronously,
        # and ModulePublished implies the module (and therefore its course)
        # already exists. Raised loudly rather than silently no-op'd, since
        # it would indicate a real ordering bug upstream if it ever fires.
        raise ValueError(f"No COURSE# record found for course_id={course_id!r}")

    cms_source = course.get("cms_source", "s3")
    plugin_factory = _PLUGIN_REGISTRY.get(cms_source)
    if plugin_factory is None:
        raise UnknownCMSSourceError(
            f"No registered plugin for cms_source={cms_source!r} "
            f"(course_id={course_id!r}). Known: {list(_PLUGIN_REGISTRY)}"
        )
    return plugin_factory()


def _ingest_one_module(course_id: str, module_id: str) -> None:
    plugin = _get_plugin_for_course(course_id)
    result = plugin.ingest_content(course_id, module_id)
    if result.ingestion_status == IngestionStatus.FAILED:
        logger.error("Module ingestion failed", extra={
            "course_id": course_id,
            "module_id": module_id,
            "error_message": result.error_message,
        })
    else:
        logger.info("Module ingested", extra={
            "course_id": course_id,
            "module_id": module_id,
            "ingestion_status": result.ingestion_status.value,
        })


def _sync_course(course_id: str) -> None:
    plugin = _get_plugin_for_course(course_id)
    modules = plugin.list_modules(course_id)
    logger.info("Course sync starting", extra={"course_id": course_id, "module_count": len(modules)})

    failures = 0
    for module in modules:
        module_id = module["module_id"]
        try:
            result = plugin.ingest_content(course_id, module_id)
            if result.ingestion_status == IngestionStatus.FAILED:
                failures += 1
                logger.error("Module ingestion failed during course sync", extra={
                    "course_id": course_id, "module_id": module_id, "error_message": result.error_message,
                })
        except Exception as e:
            # A single module's unexpected failure must not abort the
            # rest of the course's sync — log and continue.
            failures += 1
            logger.error("Unexpected error ingesting module during course sync", extra={
                "course_id": course_id, "module_id": module_id, "error": str(e),
            })

    logger.info("Course sync complete", extra={
        "course_id": course_id, "module_count": len(modules), "failures": failures,
    })


def handler(event: dict, context) -> None:
    """
    EventBridge rule target -- invoked once per matching event (not
    batched). event["detail-type"] selects which of the two triggers
    fired; event["detail"] carries the payload.
    """
    detail_type = event.get("detail-type")
    detail = event.get("detail", {})

    logger.info("Ingestion Lambda invoked", extra={"detail_type": detail_type, "detail": detail})

    try:
        if detail_type == "ModulePublished":
            _ingest_one_module(course_id=detail["course_id"], module_id=detail["module_id"])
        elif detail_type == "CMSCourseSyncRequested":
            _sync_course(course_id=detail["course_id"])
        else:
            logger.warning("Unrecognised detail-type, ignoring", extra={"detail_type": detail_type})
    except (ValueError, UnknownCMSSourceError) as e:
        # Course-level setup problems (missing COURSE#, unknown cms_source)
        # -- log clearly and let the Lambda fail so EventBridge's built-in
        # retry/DLQ behaviour applies, rather than swallow a real ordering
        # or config bug silently.
        logger.error("Ingestion Lambda failed", extra={"detail_type": detail_type, "detail": detail, "error": str(e)})
        raise