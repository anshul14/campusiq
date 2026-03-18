# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.application.models import dynamodb_keys as keys


class LinkStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass
class ParentChildLink:
    """
    Links a parent/guardian Cognito account to their child's
    student account. This is meant only for K-12 deployments only.

    Parents are Cognito-native (not federated) — they register
    with email and password. An admin or teacher creates this
    link after verifying the parent-child relationship.

    The Lambda Authorizer reads this record to verify that a
    parent can only access their own child's progress data.

    DynamoDB:
        PK = PARENT#{parent_cognito_sub}
        SK = CHILD#{child_cognito_sub}
    """
    parent_cognito_sub: str
    child_cognito_sub: str
    child_name: str
    child_grade: str  # Grade 5 | Year 7 | etc.
    institution_id: str
    linked_by: str  # TEACHER#{sub} or ADMIN#{sub}
    linked_at: str  # ISO 8601
    status: LinkStatus = LinkStatus.ACTIVE

    @property
    def pk(self) -> str:
        return keys.parent_pk(self.parent_cognito_sub)

    @property
    def sk(self) -> str:
        return keys.child_sk(self.child_cognito_sub)
