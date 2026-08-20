# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Content Adaptation Lambda — src/application/lambdas/content_adaptation/handler.py

Consumes: EventBridge `GapDetected` event (published by Stream Processor Lambda,
          same event Recommendation Lambda independently subscribes to —
          parallel branches, not sequential)

Produces:
  - Clarification tier (0.7 <= severity <= 0.85, ANY content format):
    STUDENT#{sub}/CLARIFICATION#{conceptId} — grounded in the specific
    wrong quiz question(s), teacher's own explanation field, structured
    JSON. Overwritten in place on each regeneration, same pattern as
    GAP# — no TTL, always reflects the latest recalculation.

  - Full rewrite tier (severity > 0.85, ANY content format): adapted
    Markdown saved to S3 alongside the original (same directory,
    "-adapted" suffix), MODULE# record updated with
    adapted_content_s3_key. SHARED across all students on that module,
    not per-student — the first student to cross 0.85 triggers the
    rewrite; every subsequent struggling student reuses it. Regeneration
    is skipped if adapted_content_s3_key already exists (idempotent,
    avoids redundant Bedrock calls).

Model: Claude Haiku 4.5 (cross-region inference profile), per
ARCHITECTURE.md 5.3's original Claude 3 Haiku selection — updated after
Claude 3 Haiku and 3.5 Haiku were both marked Legacy on Bedrock,
confirmed via a live ResourceNotFoundException during testing.

Both tiers are independently gated, not one severity-tiered flow:
clarification never touches module content at all (grounded entirely in
the QUIZ# record), so it works identically regardless of whether the
underlying module is markdown, PDF, or video. Full rewrite needs actual
module text, so it extracts it per format (markdown: read as-is; PDF:
pypdf text extraction; video: strip the existing WebVTT transcript
Transcribe already generated at ingestion) and feeds all three into one
shared rewrite call — the output is always Markdown regardless of source
format.

DynamoDB access goes through application.dynamodb (db.*), not inline
boto3 — matches the convention established for HTTP routes (see
routes/teacher.py). S3 and Bedrock clients stay inline here since
dynamodb.py's scope is DynamoDB access specifically.

Known limitation, not solved here: scanned/image-based PDFs have no
extractable text layer — would need Textract OCR, out of scope for now.
Extraction failures are logged clearly and skip the rewrite tier
gracefully rather than crashing the whole invocation — the clarification
tier still completes independently.
"""

import io
import json
import logging
import os
import re
from decimal import Decimal

import boto3

from application.services import dynamodb as db

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))

CONTENT_BUCKET = os.environ["CONTENT_BUCKET_NAME"]
MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

CLARIFICATION_MIN_SEVERITY = Decimal("0.7")
FULL_REWRITE_SEVERITY = Decimal("0.85")
MIN_EXPLANATION_WORDS = 10  # below this, teacher's explanation is too thin to ground on safely


def handler(event, context):
    """
    Entry point. event['detail'] is the GapDetected payload:

        {
            "student_id": "...", "concept_id": "friction", "gap_severity": 1.0,
            "course_id": "phys101", "last_module_id": "week3-newtons-laws",
            "last_attempt_id": "20260817T230517-d702164d"
        }

    Both tiers wrapped independently — a failure in one (e.g. PDF
    extraction failing on a scanned document) must not prevent the other
    from completing.
    """
    detail = event.get("detail", {})
    student_id = detail["student_id"]
    course_id = detail["course_id"]
    concept_id = detail["concept_id"]
    gap_severity = Decimal(
        str(detail["gap_severity"]))  # EventBridge detail is JSON float; Decimal for exact threshold comparison
    module_id = detail.get("last_module_id")
    attempt_id = detail.get("last_attempt_id")

    result = {"clarification": "skipped", "full_rewrite": "skipped"}

    if gap_severity >= CLARIFICATION_MIN_SEVERITY:
        try:
            result["clarification"] = run_clarification_tier(
                student_id, course_id, concept_id, module_id, attempt_id
            )
        except Exception:
            logger.exception(
                "Clarification tier failed. student_id=%s concept_id=%s",
                student_id, concept_id,
            )
            result["clarification"] = "error"

    if gap_severity > FULL_REWRITE_SEVERITY:
        try:
            result["full_rewrite"] = run_full_rewrite_tier(course_id, module_id)
        except Exception:
            logger.exception(
                "Full rewrite tier failed. course_id=%s module_id=%s",
                course_id, module_id,
            )
            result["full_rewrite"] = "error"

    logger.info(
        "Content Adaptation complete. student_id=%s concept_id=%s severity=%s result=%s",
        student_id, concept_id, gap_severity, result,
    )
    return result


# ── Clarification tier — format-agnostic, grounded in the quiz question ────

def run_clarification_tier(student_id: str, course_id: str, concept_id: str, module_id: str | None,
                           attempt_id: str | None) -> str:
    if not module_id or not attempt_id:
        logger.info("No module_id/attempt_id on this gap (older GAP# record) — skipping clarification.")
        return "skipped_no_attempt_data"

    wrong_question = find_wrong_question(student_id, course_id, module_id, attempt_id, concept_id)
    if wrong_question is None:
        logger.info("No wrong question found for this concept/attempt — skipping clarification.")
        return "skipped_no_wrong_question"

    explanation = wrong_question["explanation"]
    if len(explanation.split()) < MIN_EXPLANATION_WORDS:
        logger.info(
            "Teacher explanation too thin (%d words) — skipping clarification rather than "
            "risk an ungrounded response. question_id=%s", len(explanation.split()), wrong_question["question_id"],
        )
        return "skipped_thin_explanation"

    clarification = generate_clarification(wrong_question)
    db.write_clarification(student_id, concept_id, clarification)
    return "generated"


def find_wrong_question(student_id: str, course_id: str, module_id: str, attempt_id: str,
                        concept_id: str) -> dict | None:
    """
    Cross-references the triggering attempt's RESULT# record against the
    QUIZ# definition to find which specific question, tagged with this
    concept, the student got wrong. Returns the first match — quizzes
    with multiple questions per concept ground on the first wrong one
    found, not all of them.
    """
    result_item = db.get_quiz_result(student_id, course_id, module_id, attempt_id)
    if result_item is None:
        return None

    quiz_item = db.get_quiz_definition(course_id, module_id)
    if quiz_item is None:
        return None

    student_answers = {a["question_id"]: set(a["selected_ids"]) for a in result_item.get("answers", [])}

    for question in quiz_item.get("questions", []):
        if question.get("concept") != concept_id:
            continue
        selected = student_answers.get(question["id"])
        correct = set(question.get("correct_ids", []))
        if selected is not None and selected != correct:
            options_by_id = {opt["id"]: opt["text"] for opt in question.get("options", [])}
            return {
                "question_id": question["id"],
                "question_text": question["text"],
                "options": question.get("options", []),
                "correct_answer_text": ", ".join(options_by_id.get(c, c) for c in correct),
                "student_answer_text": ", ".join(options_by_id.get(s, s) for s in selected),
                "explanation": question["explanation"],
                "concept": concept_id,
            }
    return None


def strip_json_code_fence(text: str) -> str:
    """
    Claude Haiku 4.5 sometimes wraps JSON output in a Markdown code fence
    despite being told not to ("no preamble"). Strip it defensively rather
    than rely on prompt wording alone to prevent it.
    """
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def generate_clarification(wrong_question: dict) -> dict:
    system_prompt = (
        "You are writing a short clarification (2-4 sentences) for a student who "
        "answered a quiz question incorrectly. Your ONLY source of truth for the "
        "underlying concept is the teacher's own explanation provided below — do not "
        "introduce facts, examples, or framing beyond what it supports.\n\n"
        "If the teacher's explanation is thin or vague, do not compensate by inventing "
        "additional domain content. Instead, restate and rephrase what IS there more "
        "clearly, and explicitly frame this as a prompt to revisit the module's own "
        "material — do not present yourself as an independent authority on the subject.\n\n"
        "Address why the student's specific wrong answer reflects a plausible "
        "misconception, not just \"the correct answer is X.\"\n\n"
        "Respond with ONLY valid JSON in this exact structure, no preamble:\n"
        '{"misconception": "...", "clarification": "...", "prompt_to_revisit": "..."}'
    )
    user_prompt = (
        f"Question: {wrong_question['question_text']}\n"
        f"Student selected: {wrong_question['student_answer_text']}\n"
        f"Correct answer: {wrong_question['correct_answer_text']}\n"
        f"Teacher's explanation: {wrong_question['explanation']}"
    )

    response_text = invoke_bedrock(system_prompt, user_prompt, max_tokens=1024)
    response_text = strip_json_code_fence(response_text)
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        logger.error("Clarification response was not valid JSON. Raw text: %r", response_text)
        raise


# ── Full rewrite tier — format-agnostic via per-format extraction ──────────

def run_full_rewrite_tier(course_id: str, module_id: str | None) -> str:
    if not module_id:
        return "skipped_no_module_id"

    module = db.get_module(course_id, module_id)
    if module is None:
        logger.error("Module not found. course_id=%s module_id=%s", course_id, module_id)
        return "skipped_module_not_found"

    if module.get("adapted_content_s3_key"):
        logger.info("Adapted content already exists for this module — reusing, no new Bedrock call.")
        return "already_exists"

    content_type = module.get("content_type")
    extractors = {"markdown": extract_markdown, "pdf": extract_pdf, "video": extract_video_transcript}
    extractor = extractors.get(content_type)
    if extractor is None:
        logger.warning("Unknown content_type '%s' — skipping full rewrite.", content_type)
        return "skipped_unknown_content_type"

    try:
        source_text = extractor(module)
    except Exception:
        logger.exception(
            "Text extraction failed for content_type=%s module_id=%s -- skipping full rewrite, "
            "clarification tier is unaffected.", content_type, module_id,
        )
        return "skipped_extraction_failed"

    if not source_text or not source_text.strip():
        logger.warning("Extracted text is empty. content_type=%s module_id=%s", content_type, module_id)
        return "skipped_empty_extraction"

    adapted_markdown = rewrite_content(source_text)
    adapted_key = save_adapted_content(module, adapted_markdown)
    db.update_module_adapted_content_key(course_id, module_id, adapted_key)
    return "generated"


def extract_markdown(module: dict) -> str:
    obj = s3.get_object(Bucket=CONTENT_BUCKET, Key=module["content_s3_key"])
    return obj["Body"].read().decode("utf-8")


def extract_pdf(module: dict) -> str:
    """
    pypdf text extraction -- works for born-digital PDFs (typed slides,
    typed notes), which covers most course material. Scanned/image-based
    PDFs have no extractable text layer and would need Textract OCR --
    not handled here; extraction returns empty text in that case, and the
    caller treats empty extraction as a skip, not a crash.
    """
    import pypdf

    obj = s3.get_object(Bucket=CONTENT_BUCKET, Key=module["content_s3_key"])
    reader = pypdf.PdfReader(io.BytesIO(obj["Body"].read()))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def extract_video_transcript(module: dict) -> str:
    """
    Reuses the WebVTT transcript Transcribe already generated at ingestion
    -- no new transcription work, just strips VTT cue timestamps/indices
    to get plain spoken text.
    """
    transcript_key = module.get("transcript_s3_key")
    if not transcript_key:
        logger.warning("Video module has no transcript_s3_key -- was ingestion still processing?")
        return ""

    obj = s3.get_object(Bucket=CONTENT_BUCKET, Key=transcript_key)
    vtt_text = obj["Body"].read().decode("utf-8")
    return strip_vtt_markup(vtt_text)


def strip_vtt_markup(vtt_text: str) -> str:
    timestamp_pattern = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}")
    lines = []
    for line in vtt_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "WEBVTT" or stripped.isdigit() or timestamp_pattern.match(stripped):
            continue
        lines.append(stripped)
    return " ".join(lines)


def rewrite_content(source_text: str) -> str:
    """
    One shared rewrite call regardless of source format. The output is
    always Markdown -- if the source had no real structure (a PDF's
    unstructured extracted text, or a video transcript's run-on spoken
    text), the model is explicitly instructed to impose reasonable
    Markdown structure, not just simplify prose in place.
    """
    system_prompt = (
        "You are rewriting a course module's content at a lower difficulty level for a "
        "struggling student. Preserve all key concepts and factual accuracy -- do not "
        "invent or add information not present in the source. Simplify sentence "
        "structure and vocabulary. If the source lacks clear structure (e.g. it came "
        "from a PDF or a spoken video transcript), organize it into logical sections "
        "with Markdown headings rather than reproducing it as a single unstructured "
        "block. Return ONLY the rewritten Markdown content -- no preamble, no meta-commentary."
    )
    return invoke_bedrock(system_prompt, source_text, max_tokens=2000)


def save_adapted_content(module: dict, adapted_markdown: str) -> str:
    """
    Derives the adapted key from the module's own real content_s3_key by
    inserting "-adapted" before the file extension -- guarantees the
    adapted variant sits in the same directory as the original, rather
    than reconstructing a path from course_id/module_id that could drift
    from whatever folder convention the original actually uses.
    e.g. university/phys101/week5/content.md -> .../content-adapted.md
    """
    original_key = module["content_s3_key"]
    base, ext = original_key.rsplit(".", 1)
    adapted_key = f"{base}-adapted.{ext}"
    s3.put_object(Bucket=CONTENT_BUCKET, Key=adapted_key, Body=adapted_markdown.encode("utf-8"),
                  ContentType="text/markdown")
    return adapted_key


# ── Shared Bedrock helper ───────────────────────────────────────────────────

def invoke_bedrock(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    """
    Claude Haiku 4.5 supports hybrid/extended reasoning -- the response's
    content array can include non-text blocks (e.g. type="thinking")
    before the actual text block. Filter for the real text block(s)
    instead of assuming position 0, which was the shape of the older,
    simpler Claude 3 Haiku response and broke silently on this model.
    """
    response = bedrock.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }),
    )
    body = json.loads(response["body"].read())
    text_blocks = [block["text"] for block in body.get("content", []) if block.get("type") == "text"]

    if not text_blocks:
        logger.error("No text block found in Bedrock response. Raw body: %s", json.dumps(body))
        raise ValueError("Bedrock response contained no text content block")

    return "".join(text_blocks)
