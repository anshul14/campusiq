import logging
from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Request, HTTPException

from src.application.schemas import SubmitQuizRequest, SubmitQuizResponse, QuizDefinitionResponse, GenerateQuizRequest, \
    GenerateQuizResponse, SaveQuizResponse, SaveQuizRequest, QuizAttemptResponse, CourseQuizResultsResponse
from src.application.services import dynamodb as db

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
        )

        return SubmitQuizResponse(
            attempt_id=attempt_id,
            score_pct=score_pct,
            passed=passed,
            concept_scores=concept_scores,
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
    pass

@router.post("/courses/{course_id}/modules/{module_id}/quiz/submit", response_model=SubmitQuizResponse)
async def submit_quiz_attempt(
        course_id: str,
        module_id: str,
        request: Request,
        body: SubmitQuizRequest,
) -> SubmitQuizResponse:
    pass

@router.get("/courses/{course_id}/modules/{module_id}/quiz/results", response_model=CourseQuizResultsResponse)
async def get_course_quiz_results(
        course_id: str,
        module_id: str,
        request: Request,
) -> CourseQuizResultsResponse:
    pass
