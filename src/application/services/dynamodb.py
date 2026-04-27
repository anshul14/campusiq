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

import boto3
from aws_lambda_powertools import Logger
from boto3.dynamodb.conditions import Key, Attr

logger = Logger(service="dynamodb-service")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.getenv("DYNAMODB_TABLE_NAME", ""))

ENTITY_TYPE_INDEX = "EntityTypeIndex"

# Encode LastEvaluatedKey -> opaque cursor string
def encode_cursor(last_evaluated_key: dict) -> str:
    json_string = json.dumps(last_evaluated_key)
    return base64.b64encode(json_string.encode()).decode()


# Decode cursor string -> LastEvaluatedKey
def decode_cursor(cursor: str) -> dict:
    json_string = base64.b64decode(cursor.encode()).decode()
    return json.loads(json_string)

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
        "items": response["Items"],
        "next_cursor": encode_cursor(response["LastEvaluatedKey"]) if "LastEvaluatedKey" in response else None,
    }
