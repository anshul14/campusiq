# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from src.application.models import dynamodb_keys as keys


class IngestionStatus(str, Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    COMPLETE   = "complete"
    FAILED     = "failed"


@dataclass
class CMSPluginConfig:
    """
    Deployment-level CMS plugin configuration.
    One record per deployment — stores which plugin is active
    and its configuration.

    DynamoDB:
        PK = CONFIG#cms_plugin
        SK = ACTIVE
    """
    plugin_type:   str           # s3 | google_classroom | strapi | custom
    field_mapping: dict          # CMS field name → CampusIQ field name
    plugin_config: dict          # plugin-specific config (credentials ARNs, endpoints)
    updated_at:    str           # ISO 8601
    updated_by:    str           # ADMIN#{cognitoSub}

    @property
    def pk(self) -> str:
        return keys.config_cms_pk()

    @property
    def sk(self) -> str:
        return keys.active_sk()


@dataclass
class DomainConfig:
    """
    Deployment-level domain experience configuration.
    Controls AI behaviour — tutor persona, model selection,
    guardrails, and content restrictions.

    DynamoDB:
        PK = CONFIG#domain
        SK = ACTIVE
    """
    domain_type:          str           # university | k12 | corporate
    tutor_persona:        str           # system prompt prefix for Tutor Agent
    model_id:             str           # Bedrock model ID
    temperature:          float
    max_tokens:           int
    age_group:            str           # adult | teen | child
    content_restrictions: list[str]     = field(default_factory=list)
    guardrails_id:        Optional[str] = None   # Bedrock Guardrails ID
    updated_at:           str           = ""
    updated_by:           str           = ""     # ADMIN#{cognitoSub}

    @property
    def pk(self) -> str:
        return keys.config_domain_pk()

    @property
    def sk(self) -> str:
        return keys.active_sk()


@dataclass
class IngestionManifest:
    """
    Tracks the ingestion status of a module's content into
    the Bedrock Knowledge Base.

    Written when content is first ingested, updated as the
    KB ingestion job progresses. The ingestion Lambda checks
    this before re-ingesting to avoid duplicate KB entries.

    DynamoDB:
        PK = COURSE#{course_id}
        SK = INGEST#{module_id}
    """
    course_id:        str
    module_id:        str
    s3_key:           str
    content_type:     str
    ingestion_status: IngestionStatus
    ingested_at:      Optional[str]  = None   # ISO 8601 — set on completion
    kb_document_id:   Optional[str]  = None   # Bedrock KB document ID
    error_message:    Optional[str]  = None   # populated on failure

    @property
    def pk(self) -> str:
        return keys.course_pk(self.course_id)

    @property
    def sk(self) -> str:
        return keys.ingest_sk(self.module_id)
