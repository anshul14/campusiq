# src/application/routes/teacher.py
"""
Teacher-facing routes. Currently: GET /me/courses.

Router prefix is /teacher (singular) per the ADR-016 Lambda-per-router
convention and the earlier fix correcting /teachers -> /teacher to match
the deployed API Gateway resource.

Data access lives in dynamodb.py (see list_teacher_courses,
count_active_enrollments, list_course_gap_records) — this file only holds
request handling and the business logic those raw queries feed into
(per-student-then-course averaging, at-risk counting, None-vs-0.0 handling).
"""

from decimal import Decimal
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request

from application.services import dynamodb as db
from application.schemas import CourseSummaryForTeacher, TeacherCoursesResponse

router = APIRouter(prefix="/teacher")

AT_RISK_SEVERITY_THRESHOLD = Decimal("0.700")


@router.get("/me/courses", response_model=TeacherCoursesResponse)
async def get_my_courses(request: Request):
    """
    Every course this teacher is assigned to, with class-health metrics
    computed fresh on every call — at_risk_count and avg_mastery are not
    stored anywhere; see _compute_gap_metrics for why.
    """
    role = request.state.authorizer["role"]
    if role != "TEACHER":
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Teachers only"})

    teacher_id = request.state.authorizer["userId"]

    assignments = db.list_teacher_courses(teacher_id)
    courses = [_build_course_summary(assignment["course_id"]) for assignment in assignments]

    return TeacherCoursesResponse(courses=courses)


def _build_course_summary(course_id: str) -> CourseSummaryForTeacher:
    course = db.get_course_by_id(course_id)

    if course is None:
        # Assignment record exists but the course itself doesn't — a data
        # integrity issue, not a reason to fail the whole list. Surface it
        # visibly instead of silently dropping the course.
        title, status = f"(missing course record: {course_id})", "unknown"
    else:
        title = course["title"]
        status = course["status"]

    enrolled_count = db.count_active_enrollments(course_id)
    at_risk_count, avg_mastery, assessed_count = _compute_gap_metrics(course_id)

    return CourseSummaryForTeacher(
        course_id=course_id,
        title=title,
        status=status,
        enrolled_count=enrolled_count,
        assessed_count=assessed_count,
        at_risk_count=at_risk_count,
        avg_mastery=avg_mastery,
    )


def _compute_gap_metrics(course_id: str) -> tuple[int, float | None, int]:
    """
    Business logic over db.list_course_gap_records — the raw fetch stays in
    dynamodb.py, the aggregation stays here, matching how count_quiz_attempts
    vs. the retry logic that calls it are already split elsewhere.

    - at_risk_count: distinct students with >=1 concept at gap_severity >= 0.7.
      A student tested on 3 concepts with 1 over threshold counts once, not
      three times.
    - avg_mastery: each student's own average mastery (1 - severity) across
      their assessed concepts, averaged again across students who have at
      least one GAP# record. Per-student-then-course, not a flat average
      across all records — otherwise a heavily-tested student would pull
      the course average harder than a lightly-tested one.
    - assessed_count: how many students have >=1 GAP# record, so the caller
      can tell "no gaps, everyone's fine" apart from "nobody's been tested
      yet." avg_mastery is None when assessed_count is 0 — treating "no
      data" as a real 0.0 (perfect mastery) would be a false claim on a
      teacher-facing dashboard.

    KNOWN LIMITATION: does not cross-reference enrollment status, so a
    withdrawn (archived) student's GAP# records still count here. Excluding
    them would need a per-student enrollment lookup (N+1) against this
    course-scoped query. Acceptable for now — revisit if a course
    accumulates enough withdrawn-student history to skew the numbers
    noticeably.
    """
    items = db.list_course_gap_records(course_id)

    per_student_severities = defaultdict(list)
    for item in items:
        student_id = item["PK"].replace("STUDENT#", "")
        per_student_severities[student_id].append(item["gap_severity"])

    assessed_count = len(per_student_severities)
    if assessed_count == 0:
        return 0, None, 0

    at_risk_count = 0
    per_student_mastery = []
    for severities in per_student_severities.values():
        if any(severity >= AT_RISK_SEVERITY_THRESHOLD for severity in severities):
            at_risk_count += 1
        per_student_mastery.append(sum(Decimal("1") - s for s in severities) / len(severities))

    avg_mastery = float(sum(per_student_mastery) / len(per_student_mastery))
    return at_risk_count, round(avg_mastery, 4), assessed_count