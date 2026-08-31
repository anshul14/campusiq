# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
DynamoDB utility methods
"""
import base64
import json
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

import boto3
from aws_lambda_powertools import Logger
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

logger = Logger(service="dynamodb-service")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.getenv("DYNAMODB_TABLE_NAME", ""))

ENTITY_TYPE_INDEX = "EntityTypeIndex"
AT_RISK_INDEX = "AtRiskIndex"


# Encode LastEvaluatedKey -> opaque cursor string
def encode_cursor(last_evaluated_key: dict) -> str:
    json_string = json.dumps(last_evaluated_key)
    return base64.b64encode(json_string.encode()).decode()


# Decode cursor string -> LastEvaluatedKey
def decode_cursor(cursor: str) -> dict:
    json_string = base64.b64decode(cursor.encode()).decode()
    return json.loads(json_string)


def _map_to_course_summary(item: dict) -> dict:
    return {
        "course_id": item["PK"].replace("COURSE#", ""),
        "title": item.get("title", ""),
        "description": item.get("description", ""),
        "domain": item.get("domain", ""),
        "difficulty": item.get("difficulty", ""),
        "status": item.get("status", ""),
        "module_count": item.get("module_count", 0),
    }


def _map_to_course_response(item: dict) -> dict:
    return {
        "course_id": item["PK"].replace("COURSE#", ""),
        "title": item.get("title", ""),
        "description": item.get("description", ""),
        "domain": item.get("domain", ""),
        "difficulty": item.get("difficulty", ""),
        "status": item.get("status", ""),
        "module_order": item.get("module_order", []),
        "cms_source": item.get("cms_source", ""),
        "created_by": item.get("created_by", ""),
        "created_at": item.get("created_at", ""),
        "updated_at": item.get("updated_at", ""),
    }


def _map_to_module_summary(item: dict) -> dict:
    return {
        "module_id": item["SK"].replace("MODULE#", ""),
        "title": item.get("title", ""),
        "content_type": item.get("content_type", ""),
        "status": item.get("status", ""),
        "estimated_minutes": item.get("estimated_minutes", ""),
        "prerequisites": item.get("prerequisites", []),
        "quiz_id": item.get("quiz_id", "")
    }


def _map_to_module_response(item: dict) -> dict:
    return {
        "module_id": item["SK"].replace("MODULE#", ""),
        "title": item.get("title", ""),
        "content_type": item.get("content_type", ""),
        "status": item.get("status", ""),
        "content_url": item.get("content_url", ""),
        "video_url": item.get("video_url", ""),
        "transcript_url": item.get("transcript_url", ""),
        "quiz_id": item.get("quiz_id", ""),
        "prerequisites": item.get("prerequisites", []),
        "estimated_minutes": item.get("estimated_minutes", ""),
        "ingestion_status": item.get("ingestion_status", ""),

    }


def list_all_courses(
        domain: str = None,
        status: str = None,
        cursor: str = None,
        page_size: int = 20,
) -> dict:
    kwargs = {
        "IndexName": ENTITY_TYPE_INDEX,
        "KeyConditionExpression": Key("entity_type").eq("COURSE"),
        "Limit": page_size
    }
    if cursor:
        kwargs["ExclusiveStartKey"] = decode_cursor(cursor)

    filters = []
    if domain:
        filters.append(Attr("domain").eq(domain))
    if status:
        filters.append(Attr("status").eq(status))
    if filters:
        filter_exp = filters[0]
        for f in filters[1:]:
            filter_exp = filter_exp & f
        kwargs["FilterExpression"] = filter_exp
    response = table.query(
        **kwargs
    )
    return {
        "items": [_map_to_course_summary(item) for item in response["Items"]],
        "next_cursor": encode_cursor(response["LastEvaluatedKey"]) if "LastEvaluatedKey" in response else None,
    }


def get_course_by_id(course_id: str) -> dict | None:
    response = table.get_item(
        Key={"PK": f"COURSE#{course_id}", "SK": "METADATA"})
    item = response.get("Item")  # None if not found
    if item is None:
        return None
    return _map_to_course_response(item)


def teacher_is_assigned_to_course(teacher_id: str, course_id: str) -> bool:
    response = table.get_item(
        Key={
            "PK": f"TEACHER#{teacher_id}",
            "SK": f"TEACHES#{course_id}"
        }
    )
    return response.get("Item") is not None


def student_is_enrolled_to_course(student_id: str, course_id: str) -> bool:
    response = table.get_item(
        Key={
            "PK": f"STUDENT#{student_id}",
            "SK": f"ENROL#{course_id}"
        }
    )
    return response.get("Item") is not None


def create_course(
        course_id: str,
        title: str,
        description: str,
        domain: str,
        difficulty: str,
        cms_source: str,
        created_by: str,
        now: str,
) -> None:
    try:
        table.put_item(
            Item={
                "PK": f"COURSE#{course_id}",
                "SK": "METADATA",
                "entity_type": "COURSE",
                "title": title,
                "description": description,
                "domain": domain,
                "difficulty": difficulty,
                "cms_source": cms_source,
                "status": "draft",
                "module_order": [],
                "created_by": created_by,
                "created_at": now,
                "updated_at": now,
            }
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        logger.error("DynamoDB put_item failed", extra={
            "error_code": error_code,
            "course_id": course_id,
        })
        raise e


def update_course(
        course_id: str,
        title: str = None,
        description: str = None,
        difficulty: str = None,
        status: str = None,
        now: str = None,
) -> None:
    # Build update expression dynamically
    update_parts = []
    values = {}

    if title is not None:
        update_parts.append("title = :t")
        values[":t"] = title

    if description is not None:
        update_parts.append("description = :d")
        values[":d"] = description

    if difficulty is not None:
        update_parts.append("difficulty = :diff")
        values[":diff"] = difficulty

    if status is not None:
        update_parts.append("#s = :s")
        values[":s"] = status

    # Always update the time
    update_parts.append("updated_at = :u")
    values[":u"] = now

    kwargs = {
        "Key": {"PK": f"COURSE#{course_id}", "SK": "METADATA"},
        "UpdateExpression": "SET " + ", ".join(update_parts),
        "ExpressionAttributeValues": values,
    }

    if status is not None:
        kwargs["ExpressionAttributeNames"] = {"#s": "status"}
    try:
        table.update_item(
            **kwargs
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        logger.error("DynamoDB update_course failed", extra={
            "error_code": error_code,
            "course_id": course_id,
        })
        raise e


def archive_course(course_id: str, now: str) -> None:
    try:
        table.update_item(
            Key={"PK": f"COURSE#{course_id}", "SK": "METADATA"},
            UpdateExpression="SET #s = :s, deleted_at = :d",
            ExpressionAttributeValues={":s": "archived", ":d": now},
            ExpressionAttributeNames={"#s": "status"},
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        logger.error("DynamoDB archive_course failed", extra={
            "error_code": error_code,
            "course_id": course_id,
        })
        raise e


def list_all_modules_of_course(
        course_id: str,
        cursor: str = None,
        page_size: int = 20,
) -> dict:
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(f"COURSE#{course_id}")
                                  & Key("SK").begins_with("MODULE#"),
        "Limit": page_size,
    }
    if cursor:
        kwargs["ExclusiveStartKey"] = decode_cursor(cursor)

    response = table.query(
        **kwargs
    )
    return {
        "items": [_map_to_module_summary(item) for item in response["Items"]],
        "next_cursor": encode_cursor(response["LastEvaluatedKey"]) if "LastEvaluatedKey" in response else None,
    }


def get_module_by_id(
        course_id: str,
        module_id: str,

) -> dict | None:
    response = table.get_item(
        Key={
            "PK": f"COURSE#{course_id}",
            "SK": f"MODULE#{module_id}",
        }
    )
    item = response.get("Item")  # None if not found
    if item is None:
        return None
    return _map_to_module_response(item)


def update_module(
        course_id: str,
        module_id: str,
        title: str = None,
        estimated_minutes: int = None,
        prerequisites: str = None,
        status: str = None,
        now: str = None,
) -> None:
    update_parts = []
    values = {}
    if title is not None:
        update_parts.append("title = :t")
        values[":t"] = title

    if estimated_minutes is not None:
        update_parts.append("estimated_minutes = :e")
        values[":e"] = estimated_minutes

    if prerequisites is not None:
        update_parts.append("prerequisites = :p")
        values[":p"] = prerequisites

    if status is not None:
        update_parts.append("#s = :s")
        values[":s"] = status

    # Always update the time
    update_parts.append("updated_at = :u")
    values[":u"] = now

    kwargs = {
        "Key": {"PK": f"COURSE#{course_id}", "SK": f"MODULE#{module_id}"},
        "UpdateExpression": "SET " + ", ".join(update_parts),
        "ExpressionAttributeValues": values,
    }

    if status is not None:
        kwargs["ExpressionAttributeNames"] = {"#s": "status"}
    try:
        table.update_item(
            **kwargs
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        logger.error("DynamoDB update_module failed", extra={
            "error_code": error_code,
            "course_id": course_id,
            "module_id": module_id,
        })
        raise e


def create_module(course_id: str,
                  module_id: str,
                  title: str,
                  content_type: str,
                  estimated_minutes: int = None,
                  prerequisites: list[str] = None,
                  created_by: str = None,
                  now: str = None,
                  ) -> None:
    try:
        table.put_item(
            Item={
                "PK": f"COURSE#{course_id}",
                "SK": f"MODULE#{module_id}",
                "entity_type": "MODULE",
                "title": title,
                "content_type": content_type,
                "estimated_minutes": estimated_minutes,
                "prerequisites": prerequisites,
                "status": "draft",
                "ingestion_status": "pending",
                "created_at": now,
                "updated_at": now,
                "created_by": created_by,
            }
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        logger.error("DynamoDB create_module failed", extra={
            "error_code": error_code,
            "course_id": course_id,
        })
        raise e


def append_module_to_course_order(course_id: str, module_id: str) -> None:
    try:
        table.update_item(
            Key={"PK": f"COURSE#{course_id}", "SK": "METADATA"},
            UpdateExpression="SET module_order = list_append(module_order, :m)",
            ExpressionAttributeValues={":m": [module_id]},  # must be a list
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        logger.error("DynamoDB append_module_to_course_order failed", extra={
            "error_code": error_code,
            "course_id": course_id,
            "module_id": module_id,
        })
        raise e


def archive_module(course_id: str, module_id: str, now: str) -> None:
    try:
        table.update_item(
            Key={"PK": f"COURSE#{course_id}", "SK": f"MODULE#{module_id}"},
            UpdateExpression="SET #s = :s, deleted_at = :d",
            ExpressionAttributeValues={":s": "archived", ":d": now},
            ExpressionAttributeNames={"#s": "status"},
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        logger.error("DynamoDB archive_module failed", extra={
            "error_code": error_code,
            "module_id": module_id,
        })
        raise e


def remove_module_from_course_order(course_id: str, module_id: str) -> None:
    # Step 1 — read current module_order
    response = table.get_item(
        Key={"PK": f"COURSE#{course_id}", "SK": "METADATA"},
    )
    item = response.get("Item")
    if item is None:
        return

    # Step 2 — remove module_id from list in Python
    module_order = item.get("module_order", [])
    updated_order = [m for m in module_order if m != module_id]

    # Step 3 — write updated list back
    try:
        table.update_item(
            Key={"PK": f"COURSE#{course_id}", "SK": "METADATA"},
            UpdateExpression="SET module_order = :o",
            ExpressionAttributeValues={":o": updated_order},
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        logger.error("DynamoDB remove_module_from_course_order failed", extra={
            "error_code": error_code,
            "course_id": course_id,
            "module_id": module_id,
        })
        raise e


def enrol_students(
        course_id: str,
        student_ids: list[str],
        now: str,
) -> None:
    # Build enrolment items
    items = []
    for student_id in student_ids:
        items.append({
            "PutRequest": {
                "Item": {
                    "PK": f"STUDENT#{student_id}",
                    "SK": f"ENROL#{course_id}",
                    "course_id": course_id,
                    "student_id": student_id,
                    "enrolled_at": now,
                    "status": "active",
                    "GSI1_PK": f"COURSE#{course_id}",
                    "GSI1_SK": f"STUDENT#{student_id}",
                }
            }
        })

    # Split into chunks of 25 — DynamoDB batch_write_item limit
    table_name = os.getenv("DYNAMODB_TABLE_NAME", "")
    chunks = [items[i:i + 25] for i in range(0, len(items), 25)]

    try:
        for chunk in chunks:
            dynamodb.batch_write_item(
                RequestItems={
                    table_name: chunk
                }
            )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        logger.error("DynamoDB batch_write_item failed", extra={
            "error_code": error_code,
            "course_id": course_id,
        })
        raise e


def _map_to_student_profile(item: dict) -> dict:
    return {
        "cognito_sub": item["PK"].replace("STUDENT#", ""),
        "student_id": item.get("student_id", ""),
        "name": item.get("name", ""),
        "email": item.get("email", ""),
        "domain": item.get("domain", ""),
        "grade": item.get("grade", ""),
        "enrollment_status": item.get("enrollment_status", "active"),
        "last_active_at": item.get("last_active_at", ""),
    }


def get_student_profile(student_id: str) -> dict | None:
    response = table.get_item(
        Key={"PK": f"STUDENT#{student_id}", "SK": "PROFILE"},
    )
    profile = response.get("Item")  # None if not found
    if profile is None:
        return None
    return _map_to_student_profile(profile)


# ------------------------------------------------------------------
# GET /students/me/courses  →  list_student_enrolments
# ------------------------------------------------------------------

def list_student_enrolments(
        user_id: str,
        cursor: Optional[str] = None,
        page_size: int = 20,
) -> dict:
    """
    Query all ENROL# records for a student.

    KeyConditionExpression:
        PK = STUDENT#{user_id}   AND   SK begins_with ENROL#

    No FilterExpression needed — every record under ENROL# prefix
    is an enrolment by definition of the single-table key design.

    Returns:
        { items: [...], next_cursor: str | None }
    """
    kwargs = {
        "KeyConditionExpression": (
                Key("PK").eq(f"STUDENT#{user_id}")
                & Key("SK").begins_with("ENROL#")
        ),
        "Limit": page_size,
        # Most recently enrolled first
        "ScanIndexForward": False,
    }

    if cursor:
        kwargs["ExclusiveStartKey"] = decode_cursor(cursor)

    response = table.query(**kwargs)

    return {
        "items": response["Items"],
        "next_cursor": (
            encode_cursor(response["LastEvaluatedKey"])
            if "LastEvaluatedKey" in response
            else None
        ),
    }


# ------------------------------------------------------------------
# PUT /students/me/courses/{course_id}/modules/{module_id}/progress
# →  upsert_module_progress
# ------------------------------------------------------------------

def upsert_module_progress(
        user_id: str,
        course_id: str,
        module_id: str,
        progress_pct: float,
        status: str,
) -> dict:
    """
    Upsert a progress record for a student + course + module combination.

    Key:
        PK = STUDENT#{user_id}
        SK = PROGRESS#{course_id}#{module_id}

    Upsert behaviour:
        - progress_pct, status, updated_at  — always overwritten (SET)
        - created_at, entity_type           — set ONLY on first write (if_not_exists)
          This is the atomic upsert pattern — no separate get_item + conditional
          put_item needed.

    Why Decimal for progress_pct?
        boto3 DynamoDB does not accept Python float types.
        Decimal(str(value)) is the correct conversion — str() avoids floating
        point precision issues (e.g. Decimal(0.1) → Decimal('0.1000000...1')).

    ReturnValues=ALL_NEW:
        Returns the full updated record in one round trip.
        Avoids a second get_item call after the update.
    """
    now = datetime.now(timezone.utc).isoformat()

    response = table.update_item(
        Key={
            "PK": f"STUDENT#{user_id}",
            "SK": f"PROGRESS#{course_id}#{module_id}",
        },
        UpdateExpression=(
            "SET progress_pct = :pct, "
            "#s = :s, "
            "updated_at = :u, "
            "GSI1_PK = :g1pk",
            "GSI1_SK = :g1sk",
            "created_at = if_not_exists(created_at, :u), "
            "entity_type = if_not_exists(entity_type, :et)"
        ),
        ExpressionAttributeNames={
            # 'status' is a DynamoDB reserved word — must alias
            "#s": "status",
        },
        ExpressionAttributeValues={
            ":pct": Decimal(str(progress_pct)),  # float → Decimal
            ":s": status,
            ":u": now,
            ":et": "PROGRESS",
            ":g1pk": f"COURSE#{course_id}",
            ":g1sk": f"PROGRESS#{module_id}#{user_id}",
        },
        ReturnValues="ALL_NEW",
    )

    # response["Attributes"] contains the full updated item
    return response["Attributes"]


def get_quiz_for_module(
        course_id: str,
        module_id: str,
) -> dict:
    """
    Retrieve the quiz for a given module.
    Key:
        PK = COURSE#{course_id}
        SK = QUIZ#{module_id}
    :param course_id:
    :param module_id:
    :return:
    """
    response = table.get_item(
        Key={
            "PK": f"COURSE#{course_id}",
            "SK": f"QUIZ#{module_id}",
        }
    )
    item = response.get("Item")  # None if not found
    if item is None:
        return None

    return item


# ------------------------------------------------------------------
# Get quiz attempt counts for the student
# ------------------------------------------------------------------
def count_quiz_attempts(user_id, course_id, module_id) -> int:
    """
    Count the number of quiz attempts for a student + course + module combination.
    Key:
        PK = STUDENT#{user_id}
        SK begins_with RESULT#{courseId}#{moduleId}#

    :param user_id:
    :param course_id:
    :param module_id:
    :return:
    """
    kwargs = {
        "KeyConditionExpression": (
                Key("PK").eq(f"STUDENT#{user_id}")
                & Key("SK").begins_with(f"RESULT#{course_id}#{module_id}#")
        ),
        "Select": "COUNT",
    }
    response = table.query(**kwargs)
    return response["Count"]


def write_quiz_result(user_id, course_id, module_id, attempt_id,
                      score_pct, passed, concept_scores, quiz_id,
                      time_taken_seconds, answers, submitted_at, student_name: str = "", attempt_count: int = 1):
    try:
        ttl = int((datetime.now(timezone.utc) + timedelta(days=730)).timestamp())
        table.put_item(
            Item={
                "PK": f"STUDENT#{user_id}",
                "SK": f"RESULT#{course_id}#{module_id}#{attempt_id}",
                "course_id": course_id,
                "module_id": module_id,
                "quiz_id": quiz_id,
                "student_name": student_name,
                "score_pct": Decimal(str(score_pct)),
                "attempt_count": attempt_count,
                "passed": passed,
                "concept_scores": {
                    concept: Decimal(str(score))
                    for concept, score in concept_scores.items()
                },
                "time_taken_seconds": time_taken_seconds,
                "answers": answers,
                "entity_type": "QUIZ_RESULT",
                "submitted_at": submitted_at,
                "created_at": submitted_at,
                "updated_at": submitted_at,
                "ttl": ttl,
                "GSI1_PK": f"COURSE#{course_id}",
                "GSI1_SK": f"RESULT#{module_id}#{user_id}#{attempt_id}",
            }
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        logger.error("DynamoDB put_item failed", extra={
            "error_code": error_code,
            "course_id": course_id,
        })
        raise e


def get_latest_quiz_attempt(user_id: str, course_id: str, module_id: str) -> dict | None:
    """
    Fetch the most recent quiz attempt for a student + course + module.

    Key:
        PK = STUDENT#{user_id}
        SK begins_with RESULT#{course_id}#{module_id}#

    ScanIndexForward=False + Limit=1 returns the latest attempt in one read unit.
    Timestamp-prefixed attempt_id ensures chronological SK sort.

    Returns:
        The DynamoDB item dict, or None if no attempts exist.
    """
    response = table.query(
        KeyConditionExpression=(
                Key("PK").eq(f"STUDENT#{user_id}")
                & Key("SK").begins_with(f"RESULT#{course_id}#{module_id}#")
        ),
        ScanIndexForward=False,
        Limit=1,
    )
    items = response.get("Items", [])
    return items[0] if items else None


def create_student_profile_if_not_exists(user_id, email, name, grade, idp_provider, institution_id, entity_type,
                                         created_at, student_id: str, enrollment_status: str):
    response = table.update_item(
        Key={
            "PK": f"STUDENT#{user_id}",
            "SK": "PROFILE"
        },
        UpdateExpression=(
            "SET email = :e, #n = :n, grade = :g, "
            "idp_provider = :idp, institution_id = :inst, "
            "student_id = if_not_exists(student_id, :sid), "
            "enrollment_status = if_not_exists(enrollment_status, :es), "
            "entity_type = if_not_exists(entity_type, :et), "
            "created_at = if_not_exists(created_at, :ca)"
        ),
        ExpressionAttributeNames={"#n": "name"},  # name is a reserved word
        ExpressionAttributeValues={
            ":e": email,
            ":n": name,
            ":g": grade,
            ":idp": idp_provider,
            ":inst": institution_id,
            ":et": "STUDENT",
            ":ca": created_at,
            ":sid": user_id,
            ":es": enrollment_status
        },
        ReturnValues="NONE",
    )


def list_quiz_attempts(
        user_id: str,
        course_id: str,
        module_id: str,
        cursor: Optional[str] = None,
        page_size: int = 20,
) -> dict:
    """
    List all quiz attempts for a student + course + module combination.

    Key:
        PK = STUDENT#{user_id}
        SK begins_with RESULT#{course_id}#{module_id}#

    ScanIndexForward=False — most recent attempt first.
    Timestamp-prefixed attempt_id ensures chronological SK sort.

    Returns:
        { items: [...], next_cursor: str | None }
    """
    kwargs = {
        "KeyConditionExpression": (
                Key("PK").eq(f"STUDENT#{user_id}")
                & Key("SK").begins_with(f"RESULT#{course_id}#{module_id}#")
        ),
        "ScanIndexForward": False,
        "Limit": page_size,
    }

    if cursor:
        kwargs["ExclusiveStartKey"] = decode_cursor(cursor)

    response = table.query(**kwargs)

    return {
        "items": response["Items"],
        "next_cursor": (
            encode_cursor(response["LastEvaluatedKey"])
            if "LastEvaluatedKey" in response
            else None
        ),
    }


def list_course_quiz_results(
        course_id: str,
        module_id: str,
        cursor: Optional[str] = None,
        page_size: int = 50,
) -> dict:
    """
    List all quiz results for a course + module — teacher view.

    Key:
        GSI1_PK = COURSE#{course_id}
        GSI1_SK begins_with RESULT#{module_id}#

    GSI1_SK format: RESULT#{moduleId}#{userId}#{attemptId}
    Putting moduleId first enables filtering by module at the key level —
    no FilterExpression needed, no Limit gotcha.

    ScanIndexForward=False — most recent submission first.

    Returns:
        { items: [...], next_cursor: str | None }
    """
    kwargs = {
        "IndexName": "CourseIndex",
        "KeyConditionExpression": (
                Key("GSI1_PK").eq(f"COURSE#{course_id}")
                & Key("GSI1_SK").begins_with(f"RESULT#{module_id}#")
        ),
        "ScanIndexForward": False,
        "Limit": page_size,
    }

    if cursor:
        kwargs["ExclusiveStartKey"] = decode_cursor(cursor)

    response = table.query(**kwargs)

    return {
        "items": response.get("Items", []),
        "next_cursor": (
            encode_cursor(response["LastEvaluatedKey"])
            if "LastEvaluatedKey" in response
            else None
        ),
    }


def save_quiz(
        course_id: str,
        module_id: str,
        title: str,
        questions: list,
        time_limit_seconds: int | None,
        max_attempts: int,
        passing_score_pct: int,
        randomise_order: bool,
        status: str,
        created_by: str,
        now: str,
) -> str:
    """
    Save (create or overwrite) a quiz definition for a course + module.

    Key:
        PK = COURSE#{course_id}
        SK = QUIZ#{module_id}

    One quiz per module — put_item naturally overwrites if quiz already exists.
    quiz_id is deterministic: {courseId}-{moduleId}-quiz — stable across saves.

    Returns:
        quiz_id
    """
    quiz_id = f"{course_id}-{module_id}-quiz"

    try:
        table.put_item(
            Item={
                "PK": f"COURSE#{course_id}",
                "SK": f"QUIZ#{module_id}",
                "entity_type": "QUIZ",
                "quiz_id": quiz_id,
                "course_id": course_id,
                "module_id": module_id,
                "title": title,
                "questions": questions,
                "time_limit_seconds": time_limit_seconds,
                "max_attempts": max_attempts,
                "passing_score_pct": passing_score_pct,
                "randomise_order": randomise_order,
                "status": status,
                "created_by": created_by,
                "created_at": now,
                "updated_at": now,
            }
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        logger.error("DynamoDB save_quiz failed", extra={
            "error_code": error_code,
            "course_id": course_id,
            "module_id": module_id,
        })
        raise e

    return quiz_id


def list_teacher_courses(teacher_id: str) -> list[dict]:
    """
    Query all TEACHES# records for a teacher.

    KeyConditionExpression:
        PK = TEACHER#{teacher_id}   AND   SK begins_with TEACHES#

    No pagination here (unlike list_student_enrolments) — a teacher's
    assigned-course count is small and bounded, and the caller
    (GET /teacher/me/courses) needs the complete list, not a page of it.

    Returns: raw Items list — each item has course_id already stored as an
    attribute (see Entity 04), no key-parsing needed by the caller.
    """
    response = table.query(
        KeyConditionExpression=(
                Key("PK").eq(f"TEACHER#{teacher_id}")
                & Key("SK").begins_with("TEACHES#")
        ),
    )
    return response["Items"]


def count_active_enrollments(course_id: str) -> int:
    """
    Count active (non-archived, per ADR-005) enrolments for a course via
    the CourseIndex (GSI1) flip.

    KeyConditionExpression:
        GSI1_PK = COURSE#{course_id}   AND   GSI1_SK begins_with STUDENT#

    The begins_with STUDENT# is required, not optional — Teacher Assignment
    records share the same GSI1_PK=COURSE#{course_id} but use
    GSI1_SK=TEACHER#{sub}, so without this filter the count would include
    teacher assignments alongside student enrolments.

    Paginated internally (unlike count_quiz_attempts) since a single query()
    only guarantees ~1MB per page and a popular course could exceed that.
    """
    count = 0
    kwargs = {
        "IndexName": "CourseIndex",
        "KeyConditionExpression": (
                Key("GSI1_PK").eq(f"COURSE#{course_id}")
                & Key("GSI1_SK").begins_with("STUDENT#")
        ),
        "FilterExpression": Attr("status").eq("active"),
        "Select": "COUNT",
    }
    while True:
        response = table.query(**kwargs)
        count += response["Count"]
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return count


def list_course_gap_records(course_id: str) -> list[dict]:
    """
    Every GAP# record for a course via AtRiskIndex (GSI3) — no severity
    filter. Callers computing avg_mastery need every assessed student, not
    just the ones over the at-risk threshold.

    KeyConditionExpression:
        GSI3_PK = COURSE#{course_id}

    Paginated internally for the same reason as count_active_enrollments —
    this feeds an aggregate calculation (per-student-then-course averaging
    in the route layer) that needs the complete dataset, not one page of it.

    Returns: raw Items list. gap_severity comes back as Decimal — callers
    doing arithmetic on it should stay in Decimal, not cast to float
    mid-calculation.
    """
    items = []
    kwargs = {
        "IndexName": AT_RISK_INDEX,
        "KeyConditionExpression": Key("GSI3_PK").eq(f"COURSE#{course_id}"),
    }
    while True:
        response = table.query(**kwargs)
        items.extend(response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return items


# Add to src/application/dynamodb.py

def get_quiz_result(student_id: str, course_id: str, module_id: str, attempt_id: str) -> dict | None:
    """
    A single QuizResult record for one specific attempt.
    PK=STUDENT#{sub}, SK=RESULT#{courseId}#{moduleId}#{attemptId}
    """
    response = table.get_item(
        Key={"PK": f"STUDENT#{student_id}", "SK": f"RESULT#{course_id}#{module_id}#{attempt_id}"}
    )
    return response.get("Item")


def get_quiz_definition(course_id: str, module_id: str) -> dict | None:
    """
    The QuizDefinition record for a module.
    PK=COURSE#{courseId}, SK=QUIZ#{moduleId}
    """
    response = table.get_item(Key={"PK": f"COURSE#{course_id}", "SK": f"QUIZ#{module_id}"})
    return response.get("Item")


def write_clarification(student_id: str, concept_id: str, clarification: dict) -> None:
    """
    Writes/overwrites the CLARIFICATION#{conceptId} record. Same
    overwrite-in-place pattern as GAP# -- no TTL, always reflects the
    latest regeneration for this student/concept.
    """
    table.put_item(Item={
        "PK": f"STUDENT#{student_id}",
        "SK": f"CLARIFICATION#{concept_id}",
        "entity_type": "CLARIFICATION",
        "misconception": clarification["misconception"],
        "clarification": clarification["clarification"],
        "prompt_to_revisit": clarification["prompt_to_revisit"],
    })


def get_module(course_id: str, module_id: str) -> dict | None:
    """
    The Module record. PK=COURSE#{courseId}, SK=MODULE#{moduleId}
    """
    response = table.get_item(Key={"PK": f"COURSE#{course_id}", "SK": f"MODULE#{module_id}"})
    return response.get("Item")


def update_module_adapted_content_key(course_id: str, module_id: str, adapted_key: str) -> None:
    """
    Sets adapted_content_s3_key on a Module record once Content Adaptation
    has generated a shared lower-difficulty variant. Presence of this
    field is the idempotency check that prevents regenerating it for
    every subsequent struggling student on the same module.
    """
    table.update_item(
        Key={"PK": f"COURSE#{course_id}", "SK": f"MODULE#{module_id}"},
        UpdateExpression="SET adapted_content_s3_key = :key",
        ExpressionAttributeValues={":key": adapted_key},
    )


# upsert_module_from_ingestion() is a dedicated write path for CPI
# ingestion, separate from create_module()/update_module(). Neither of
# those accepts content_s3_key, ingestion_status, domain, or difficulty,
# and neither should: they're the teacher-authored-module write path,
# with different semantics (create_module() unconditionally sets
# status="draft" and ingestion_status="pending", which is wrong for
# re-ingesting an already-published module).
#
# Handles both cases in one call: a brand-new module discovered during
# backfill gets created; re-ingesting an existing module refreshes its
# content_s3_key/ingestion_status without clobbering fields ingestion
# doesn't own (title, prerequisites, status stay under the
# teacher-authored path).

def upsert_module_from_ingestion(
        course_id: str,
        module_id: str,
        content_s3_key: str,
        content_type: str,
        domain: str,
        difficulty: str,
        ingestion_status: str,
        title: str = None,
        now: str = None,
) -> None:
    """
    Upsert a MODULE# record from the CPI ingestion path.

    Key:
        PK = COURSE#{course_id}
        SK = MODULE#{module_id}

    Upsert behaviour, atomic single update_item call:
        - content_s3_key, content_type, ingestion_status, domain,
          difficulty, updated_at  — always overwritten (SET)
        - title                  — only set if provided (CPI discovery
          methods don't always have a real title — see s3_plugin.py's
          title-resolution note); if_not_exists() so a later ingestion
          run never blanks out a title the teacher already set
        - status, entity_type, created_at, created_by — set ONLY on
          first write (if_not_exists / attribute_not_exists), so a
          re-ingestion run never resets an already-published module
          back to a draft state or loses its original creation record.

    Why not create_module() + update_module()?
        create_module() unconditionally sets status="draft" and
        ingestion_status="pending" — wrong for re-ingestion of an
        already-published module. update_module() has no parameters for
        content_s3_key/ingestion_status/domain/difficulty at all. A
        conditional upsert in one call is the correct primitive here,
        not two existing functions bolted together.
    """
    # Every attribute name is aliased via ExpressionAttributeNames, not
    # just the ones known to collide today -- "domain" and "status" are
    # DynamoDB reserved words, and the reserved-word list (~570 words)
    # is large enough that "happens not to collide today" isn't a safe
    # bet for whatever field gets added to this function next.
    names = {
        "#s3key": "content_s3_key", "#ctype": "content_type", "#ing": "ingestion_status",
        "#dom": "domain", "#diff": "difficulty", "#u": "updated_at",
        "#et": "entity_type", "#ca": "created_at", "#s": "status", "#t": "title",
    }
    update_parts = [
        "#s3key = :s3key",
        "#ctype = :ctype",
        "#ing = :ing",
        "#dom = :dom",
        "#diff = :diff",
        "#u = :u",
        "#et = if_not_exists(#et, :et)",
        "#ca = if_not_exists(#ca, :now)",
        "#s = if_not_exists(#s, :draft)",
    ]
    values = {
        ":s3key": content_s3_key,
        ":ctype": content_type,
        ":ing": ingestion_status,
        ":dom": domain,
        ":diff": difficulty,
        ":u": now,
        ":et": "MODULE",
        ":now": now,
        ":draft": "draft",
    }

    if title is not None:
        update_parts.append("#t = if_not_exists(#t, :t)")
        values[":t"] = title

    kwargs = {
        "Key": {"PK": f"COURSE#{course_id}", "SK": f"MODULE#{module_id}"},
        "UpdateExpression": "SET " + ", ".join(update_parts),
        "ExpressionAttributeValues": values,
        "ExpressionAttributeNames": names,
    }

    try:
        table.update_item(**kwargs)
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        logger.error("DynamoDB upsert_module_from_ingestion failed", extra={
            "error_code": error_code,
            "course_id": course_id,
            "module_id": module_id,
        })
        raise e

# publish_module() is the synchronous half of the module Publish action,
# paired with events.emit_module_published() for the async half.

def publish_module(course_id: str, module_id: str, now: str) -> None:
    """
    Flips a module to published and marks ingestion as pending. This is
    all the Publish handler does synchronously — it deliberately does
    NOT touch content_s3_key, content_type, domain, or difficulty. Those
    are the ingestion Lambda's job, via ingest_content()'s idempotent
    upsert (if_not_exists on status/entity_type/created_at means a
    later write can't clobber what this one just set). Keeping this
    function narrow is what lets the Publish handler return immediately
    rather than wait on S3/KB work.

    Raises ValueError if the module doesn't exist — publishing a module
    that was never created is a real error, not a silent no-op.
    """
    # Attribute names aliased throughout — see upsert_module_from_ingestion.
    try:
        table.update_item(
            Key={"PK": f"COURSE#{course_id}", "SK": f"MODULE#{module_id}"},
            UpdateExpression="SET #s = :published, #ing = :pending, #u = :now",
            ConditionExpression="attribute_exists(PK)",
            ExpressionAttributeNames={"#s": "status", "#ing": "ingestion_status", "#u": "updated_at"},
            ExpressionAttributeValues={":published": "published", ":pending": "pending", ":now": now},
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ConditionalCheckFailedException":
            raise ValueError(f"Module not found: course_id={course_id!r} module_id={module_id!r}")
        logger.error("DynamoDB publish_module failed", extra={
            "error_code": error_code, "course_id": course_id, "module_id": module_id,
        })
        raise e

# update_module_content() records that content now exists for a module,
# separate from publish_module(): authoring content and publishing it
# are different actions, and saving a draft must never trigger
# ingestion. ingestion_status is left untouched here -- it only changes
# via an explicit Publish action.

def update_module_content(course_id: str, module_id: str, content_s3_key: str, content_type: str, now: str) -> None:
    """
    Records a module's content location after a successful S3 write —
    called by save_text_content()/complete_content_upload(). Does NOT
    touch status or ingestion_status.
    """
    try:
        table.update_item(
            Key={"PK": f"COURSE#{course_id}", "SK": f"MODULE#{module_id}"},
            UpdateExpression="SET #cs3 = :key, #ct = :ctype, #u = :now",
            ConditionExpression="attribute_exists(PK)",
            ExpressionAttributeNames={"#cs3": "content_s3_key", "#ct": "content_type", "#u": "updated_at"},
            ExpressionAttributeValues={":key": content_s3_key, ":ctype": content_type, ":now": now},
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ConditionalCheckFailedException":
            raise ValueError(f"Module not found: course_id={course_id!r} module_id={module_id!r}")
        logger.error("DynamoDB update_module_content failed", extra={
            "error_code": error_code, "course_id": course_id, "module_id": module_id,
        })
        raise e