# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0


"""
Recommendation Lambda — src/application/lambdas/recommendation/handler.py

Consumes: EventBridge `GapDetected` event (published by Stream Processor Lambda)
Produces: PATH#{courseId} record in DynamoDB (LearningPath entity), TTL 24h

Design: Option 1 — deterministic rule-based reordering. No Amazon Personalize,
no ML. Pull the source module of every concept currently above the 0.7
threshold to the front of recommended_modules, worst severity first, then
append the rest of the course's module_order untouched.

Personalize was evaluated and deliberately rejected at this scale: the
actual decision here is reordering ~10 known modules per course, closer to
a lookup than the large-catalog ranking problem Personalize is built for.
A bootstrap validation test (30 users, 5 items) showed no meaningful
differentiation — the model collapsed toward popularity ranking rather
than learning real per-student signal. ML-driven personalization remains a
named Phase 2 item once genuine usage volume exists; the bootstrap tooling
in tools/personalize-bootstrap/ already proves the mechanism is buildable
when warranted.

Does NOT write to PROGRESS# — the student's own client-reported progress
signal (content consumption) is fully decoupled from quiz performance by
design elsewhere in the system, and overwriting it here would both destroy
that signal and race against the student's own client PUT calls. This
Lambda writes only to its own PATH#{courseId} record, which the (not yet
built) learning-path GET endpoint checks FIRST, falling back to the plain
module_order+PROGRESS# walk if no active, unexpired PATH# override exists.

Rebuilds the FULL recommended_modules list from the student's current
complete gap profile (via GSI2) on every invocation — not just the single
concept that triggered this specific event — since a student may have
several concurrent gaps and the path should reflect all of them together,
worst severity first.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ADR-012 — module-level client, created once on cold start, reused across
# warm invocations.
dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
table = dynamodb.Table(os.environ["DYNAMODB_TABLE_NAME"])

AT_RISK_THRESHOLD = Decimal("0.7")
PATH_TTL_HOURS = 24


def handler(event, context):
    """
    Entry point. event['detail'] is the GapDetected payload:

        {
            "student_id": "c4b84488-...",
            "concept_id": "friction",
            "gap_severity": 1.0,
            "course_id": "phys101",
            "last_module_id": "week3-newtons-laws",
            "last_attempt_id": "20260817T230517-d702164d"
        }

    Only course_id and student_id are actually needed from this event —
    everything else about the CURRENT recommendation is re-derived fresh
    from the student's full gap profile, not from this one event's detail,
    so a student with multiple concurrent gaps gets a path reflecting all
    of them, not just whichever one most recently crossed threshold.
    """
    detail = event.get("detail", {})
    student_id = detail["student_id"]
    course_id = detail["course_id"]

    try:
        course = get_course(course_id)
        if course is None:
            logger.error("Course not found, cannot build learning path. course_id=%s", course_id)
            return {"status": "course_not_found"}

        module_order = course.get("module_order", [])
        at_risk_gaps = fetch_at_risk_gaps(student_id)

        recommended_modules, rationale = build_recommended_order(module_order, at_risk_gaps)
        write_learning_path(student_id, course_id, recommended_modules, rationale)

        logger.info(
            "Learning path updated. student_id=%s course_id=%s at_risk_count=%s",
            student_id, course_id, len(rationale),
        )
        return {"status": "path_updated", "recommended_modules": recommended_modules}

    except Exception:
        logger.exception(
            "Failed to build learning path. student_id=%s course_id=%s",
            student_id, course_id,
        )
        # No batch/partial-failure protocol here (unlike Stream Processor) —
        # EventBridge invokes this Lambda asynchronously, one event at a
        # time, with its own built-in retry. Let it propagate.
        raise


def get_course(course_id: str) -> dict | None:
    response = table.get_item(Key={"PK": f"COURSE#{course_id}", "SK": "METADATA"})
    return response.get("Item")


def fetch_at_risk_gaps(student_id: str) -> list[dict]:
    """
    Every GAP# record for this student currently at/above the 0.7
    threshold, via GapSeverityIndex (GSI2), worst severity first
    (GSI2_SK is the zero-padded severity string, so ScanIndexForward=False
    gives descending order).
    """
    response = table.query(
        IndexName="GapSeverityIndex",
        KeyConditionExpression=Key("GSI2_PK").eq(f"STUDENT#{student_id}"),
        ScanIndexForward=False,
    )
    items = response.get("Items", [])
    return [item for item in items if item.get("gap_severity", Decimal("0")) >= AT_RISK_THRESHOLD]


def build_recommended_order(module_order: list[str], at_risk_gaps: list[dict]) -> tuple[list[str], list[dict]]:
    """
    Deterministic reordering, no ML. Pull each at-risk concept's source
    module (last_module_id, written by Gap Detection Lambda) to the front,
    worst severity first, then append the rest of module_order untouched.

    Gaps missing last_module_id are skipped for reordering purposes only —
    older GAP# records written before that field existed have nothing to
    reorder around, but this doesn't block the rest of the path from being
    built correctly.

    If multiple concepts map to the same module, rationale records only
    the first (most severe, since gaps are processed worst-first) reason —
    deliberately simple, consistent with choosing deterministic reordering
    over ML in the first place. Not a limitation worth solving with more
    complexity for a rationale field that's informational, not the primary
    student-facing surface.
    """
    priority_modules = []
    rationale = []
    seen = set()

    for gap in at_risk_gaps:
        module_id = gap.get("last_module_id")
        if not module_id or module_id in seen:
            continue
        priority_modules.append(module_id)
        seen.add(module_id)
        rationale.append({
            "module_id": module_id,
            "concept_id": gap.get("concept_id"),
            "gap_severity": gap.get("gap_severity", Decimal("0")),  # keep as Decimal — this gets written straight to DynamoDB, not JSON-serialised
        })

    remainder = [module_id for module_id in module_order if module_id not in seen]
    return priority_modules + remainder, rationale


def write_learning_path(student_id: str, course_id: str, recommended_modules: list[str], rationale: list[dict]) -> None:
    now = datetime.now(timezone.utc)
    ttl = int((now + timedelta(hours=PATH_TTL_HOURS)).timestamp())

    table.put_item(
        Item={
            "PK": f"STUDENT#{student_id}",
            "SK": f"PATH#{course_id}",
            "entity_type": "LEARNING_PATH",
            "course_id": course_id,
            "recommended_modules": recommended_modules,
            "rationale": rationale,
            "generated_at": now.isoformat(),
            "ttl": ttl,
        }
    )