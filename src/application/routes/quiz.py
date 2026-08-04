# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0


import logging
import random
from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Request, HTTPException

from application.schemas import SubmitQuizRequest, SubmitQuizResponse, QuizDefinitionResponse, GenerateQuizRequest, \
    GenerateQuizResponse, SaveQuizResponse, SaveQuizRequest, QuizAttemptResponse, CourseQuizResultsResponse, \
    QuizAnswerResult, QuizQuestionForStudent
from application.services import dynamodb as db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.post("/courses/{course_id}/modules/{module_id}/quiz/submit", response_model=SubmitQuizResponse, status_code=201)
async def submit_quiz_attempt(
        request: Request,
        course_id: str,
        module_id: str,
        body: SubmitQuizRequest
) -> SubmitQuizResponse:
    authorizer_context = request.state.authorizer
    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]

    if role != "STUDENT":
        raise HTTPException(status_code=403, detail={
            "code": "FORBIDDEN",
            "message": "Only students can submit quiz"
        })

    try:
        quiz = db.get_quiz_for_module(course_id=course_id, module_id=module_id)
        if quiz is None:
            raise HTTPException(status_code=404, detail={
                "code": "QUIZ_NOT_FOUND",
                "message": "No quiz found for this module"
            })

        attempt_count = db.count_quiz_attempts(user_id, course_id, module_id)
        max_attempts = quiz.get("max_attempts", 3)
        if attempt_count >= max_attempts:
            raise HTTPException(status_code=403, detail={
                "code": "MAX_ATTEMPTS_EXCEEDED",
                "message": "Max attempts exceeded"
            })

        question_map = {q["id"]: q for q in quiz["questions"]}
        answer_map = {a.question_id: set(a.selected_ids) for a in body.answers}

        concept_scores_raw = defaultdict(list)
        total_correct = 0

        for q_id, question in question_map.items():
            student_answer = answer_map.get(q_id, set())
            is_correct = student_answer == set(question["correct_ids"])
            concept = question.get("concept", "general")
            concept_scores_raw[concept].append(1.0 if is_correct else 0.0)
            if is_correct:
                total_correct += 1

        concept_scores = {
            concept: round(sum(scores) / len(scores), 4)
            for concept, scores in concept_scores_raw.items()
        }
        # build the question results
        question_results = [
            QuizAnswerResult(
                id=q_id,
                correct=(answer_map.get(q_id, set()) == set(question["correct_ids"])),
                explanation=question.get("explanation", " "),
            )
            for q_id, question in question_map.items()
        ]

        total_questions = len(question_map)
        score_pct = round((total_correct / total_questions) * 100) if total_questions > 0 else 0
        passed = score_pct >= quiz.get("passing_score_pct", 70)

        now = datetime.now(timezone.utc)
        attempt_id = now.strftime('%Y%m%dT%H%M%S') + '-' + str(uuid4())[:8]
        submitted_at = now.isoformat()

        db.write_quiz_result(
            user_id=user_id,
            course_id=course_id,
            module_id=module_id,
            attempt_id=attempt_id,
            score_pct=score_pct,
            passed=passed,
            concept_scores=concept_scores,
            quiz_id=body.quiz_id,
            time_taken_seconds=body.time_taken_seconds,
            answers=body.answers,
            submitted_at=submitted_at,
            student_name=authorizer_context.get("name", ""),
            attempt_count=attempt_count + 1,  # ← +1 because count_quiz_attempts
                                                                        # returns attempts BEFORE this one
        )

        return SubmitQuizResponse(
            attempt_id=attempt_id,
            score_pct=score_pct,
            passed=passed,
            concept_scores=concept_scores,
            questions=question_results,
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Quiz submission failed", extra={
            "course_id": course_id,
            "module_id": module_id,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail={
            "code": "QUIZ_SUBMIT_FAILED",
            "message": "Failed to submit quiz"
        })


@router.get("/courses/{course_id}/modules/{module_id}/quiz", response_model=QuizDefinitionResponse)
async def get_quiz_definition(
        course_id: str,
        module_id: str,
        request: Request
) -> QuizDefinitionResponse:
    pass


@router.post("/courses/{course_id}/modules/{module_id}/quiz/generate", response_model=GenerateQuizResponse)
async def generate_quiz(
        course_id: str,
        module_id: str,
        request: Request,
        body: GenerateQuizRequest,
) -> GenerateQuizResponse:
    pass


@router.put("/courses/{course_id}/modules/{module_id}/quiz", response_model=SaveQuizResponse)
async def save_quiz_result(
        course_id: str,
        module_id: str,
        body: SaveQuizRequest,
        request: Request,
) -> SaveQuizResponse:
    pass


@router.get("/courses/{course_id}/modules/{module_id}/quiz/attempt", response_model=QuizAttemptResponse)
async def get_quiz_attempt(
        course_id: str,
        module_id: str,
        request: Request,
) -> QuizAttemptResponse:
    authorizer_context = request.state.authorizer
    role = authorizer_context["role"]
    user_id = authorizer_context["userId"]

    if role != "STUDENT":
        raise HTTPException(status_code=403, detail={
            "code": "FORBIDDEN",
            "message": "Only students can fetch a quiz attempt"
        })

    try:
        # Step 1 - verify enrolment
        if not db.student_is_enrolled_to_course(user_id, course_id):
            raise HTTPException(status_code=403, detail={
                "code": "STUDENT_NOT_ENROLLED",
                "message": "Student is not enrolled in this course"
            })

        # Step 2 - fetch quiz definition
        quiz = db.get_quiz_for_module(course_id=course_id, module_id=module_id)
        if quiz is None:
            raise HTTPException(status_code=404, detail={
                "code": "QUIZ_NOT_FOUND",
                "message": "No quiz exists for this module"
            })

        # Step 3 - enforce max attempts
        attempt_count = db.count_quiz_attempts(user_id=user_id, course_id=course_id, module_id=module_id)
        max_attempts = int(quiz.get("max_attempts", 2))
        if attempt_count >= max_attempts:
            raise HTTPException(status_code=403, detail={
                "code": "MAX_ATTEMPTS_EXCEEDED",
                "message": f"Maximum of {max_attempts} attempts reached for this quiz"
            })

        # Step 4 - check if this is a retry after failure
        latest_attempt = db.get_latest_quiz_attempt(user_id=user_id, course_id=course_id, module_id=module_id)
        is_retry_after_failure = (
                latest_attempt is not None
                and latest_attempt.get("passed") is False
        )

        if is_retry_after_failure:
            # TODO: call Assessment Lambda to generate adaptive quiz
            # targeting weak concepts from latest_attempt["concept_scores"]
            # For now: serve base quiz (same as first attempt)
            pass

        # Step 5 - strip correct_ids, build student-facing questions
        questions = [
            QuizQuestionForStudent(
                id=q["id"],
                type=q["type"],
                text=q["text"],
                options=q["options"],
            )
            for q in quiz["questions"]
        ]

        # Step 6 — randomise order if configured
        if quiz.get("randomise_order", False):
            random.shuffle(questions)

        return QuizAttemptResponse(
            quiz_id=quiz.get("quiz_id", ""),
            title=quiz.get("title", ""),
            time_limit_seconds=quiz.get("time_limit_seconds"),
            questions=questions,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch quiz attempt", extra={
            "course_id": course_id,
            "module_id": module_id,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail={
            "code": "QUIZ_FETCH_FAILED",
            "message": "Failed to fetch quiz attempt"
        })


@router.get("/courses/{course_id}/modules/{module_id}/quiz/results", response_model=CourseQuizResultsResponse)
async def get_course_quiz_results(
        course_id: str,
        module_id: str,
        request: Request,
) -> CourseQuizResultsResponse:
    pass
