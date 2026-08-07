"""
Gap Detection Lambda — src/application/lambdas/gap_detection/handler.py

Consumes: EventBridge `QuizCompleted` event (published by Stream Processor Lambda)
Produces: GAP#{conceptId} records in DynamoDB (Knowledge Gap entity, Entity 09)

Does NOT publish GapDetected itself. The Stream Processor Lambda watches the
DynamoDB Stream for GAP# writes and fires GapDetected when gap_severity > 0.7
— per its own docstring, translating table writes into EventBridge events is
its job exclusively ("contains no business logic — its only job is
pattern-matching on SK prefix and forwarding a normalised event"). This
Lambda's put_item on the GAP# record is what triggers that, same as a
QuizResult write triggers QuizCompleted. Publishing GapDetected from here too
would double-fire the event for every gap that crosses threshold.

Design: Option A — pure statistical calculation. No Bedrock InvokeModel call.
gap_severity is a recency-weighted average of historical concept scores,
inverted (1.0 = unknown/never scored well, 0.0 = mastered).

ASSUMPTION TO VERIFY BEFORE COMMIT:
concept_name derivation (title-cased concept_id) is a placeholder — the
Knowledge Gap entity has a concept_name field but concept_scores only
carries concept_id. Revisit if a concept catalog / display-name lookup
exists elsewhere.
"""

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ADR-012 — module-level client, created once on cold start, reused across
# warm invocations. Holds no user-specific state.
dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
table = dynamodb.Table(os.environ["TABLE_NAME"])

RECENCY_DECAY = Decimal("0.6")  # each older attempt weighted 0.6x the one after it


def handler(event, context):
    """
    Entry point. event['detail'] is the QuizCompleted payload published by
    the Stream Processor Lambda:

        {
            "student_id": "c4b84488-...",   # Cognito sub
            "course_id": "phys101",
            "module_id": "week3-friction",
            "attempt_id": "20260315T142200-a1b2c3d4",
            "concept_scores": {"friction": 0.4, "inertia": 0.75}
        }

    One QuizCompleted event can touch several concepts. A failure on one
    concept is logged and skipped rather than failing the whole invocation,
    so a single bad concept_id doesn't block gap updates for the others in
    the same quiz submission.
    """
    detail = event.get("detail", {})
    student_id = detail["student_id"]
    course_id = detail["course_id"]
    concept_scores = detail.get("concept_scores", {})

    if not concept_scores:
        logger.info(
            "QuizCompleted event has no concept_scores — nothing to do. student_id=%s",
            student_id,
        )
        return {"concepts_processed": 0}

    processed = 0
    for concept_id in concept_scores:
        try:
            severity = calculate_gap_severity(student_id, course_id, concept_id)
            write_knowledge_gap(student_id, course_id, concept_id, severity)
            processed += 1
            # GapDetected is not published here — the Stream Processor fires
            # it when this put_item's GAP# write lands on the DynamoDB Stream.

        except Exception:
            logger.exception(
                "Gap calculation failed. student_id=%s course_id=%s concept_id=%s",
                student_id,
                course_id,
                concept_id,
            )

    return {"concepts_processed": processed}


def calculate_gap_severity(student_id: str, course_id: str, concept_id: str) -> Decimal:
    """
    Recency-weighted average of historical scores for one concept, inverted.

    Example: scores oldest -> newest = [0.40, 0.55, 0.50, 0.65]
             weights (decay=0.6, most recent = 1.0) = [0.216, 0.36, 0.6, 1.0]
             weighted_avg = sum(s*w) / sum(w) = 0.601
             severity = 1 - weighted_avg = 0.399  (below the 0.7 at-risk threshold)
    """
    scores = fetch_historical_concept_scores(student_id, course_id, concept_id)

    if not scores:
        # Should not happen — the caller only iterates concepts that are
        # present in the current attempt's concept_scores, and that attempt's
        # RESULT# record is written before this Lambda runs. Defensive default.
        return Decimal("1.0")

    n = len(scores)
    weights = [RECENCY_DECAY ** (n - 1 - i) for i in range(n)]
    weighted_sum = sum(s * w for s, w in zip(scores, weights))
    weight_total = sum(weights)
    weighted_avg = weighted_sum / weight_total

    severity = Decimal("1.0") - weighted_avg
    return severity.quantize(Decimal("0.001"))


def fetch_historical_concept_scores(student_id: str, course_id: str, concept_id: str) -> list:
    """
    Pulls every RESULT# record for this student in this course, oldest first
    (attempt_id is timestamp-prefixed, so natural SK order == chronological
    order), and returns the score for concept_id from each attempt that
    tested it. Paginates for students with a long attempt history.
    """
    scores = []
    query_kwargs = {
        "KeyConditionExpression": (
            Key("PK").eq(f"STUDENT#{student_id}") & Key("SK").begins_with(f"RESULT#{course_id}#")
        ),
        "ScanIndexForward": True,  # oldest first
    }

    while True:
        response = table.query(**query_kwargs)
        for item in response.get("Items", []):
            concept_score = item.get("concept_scores", {}).get(concept_id)
            if concept_score is not None:
                scores.append(concept_score)

        if "LastEvaluatedKey" not in response:
            break
        query_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    return scores


def write_knowledge_gap(student_id: str, course_id: str, concept_id: str, severity: Decimal) -> None:
    """
    Writes/overwrites the GAP#{conceptId} record (Entity 09). One put_item
    triggers 3 internal writes — main table + GSI2 + GSI3.
    """
    severity_str = f"{severity:.3f}"  # zero-padded, e.g. '0.750' — matches GSI2_SK/GSI3_SK format
    now = datetime.now(timezone.utc).isoformat()

    # TODO: placeholder display name — derive from a concept catalog / Quiz
    # Definition lookup if one exists, rather than title-casing the id.
    concept_name = concept_id.replace("_", " ").title()

    table.put_item(
        Item={
            "PK": f"STUDENT#{student_id}",
            "SK": f"GAP#{concept_id}",
            "entity_type": "GAP",
            "concept_id": concept_id,
            "concept_name": concept_name,
            "course_id": course_id,
            "gap_severity": severity,
            "last_updated": now,
            "GSI2_PK": f"STUDENT#{student_id}",
            "GSI2_SK": severity_str,
            "GSI3_PK": f"COURSE#{course_id}",
            "GSI3_SK": severity_str,
        }
    )