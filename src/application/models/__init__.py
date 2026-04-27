# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
CampusIQ data models.
This is the centralized class from where all the DynamoDB entity dataclasses and key builders
can be exported throughout the application

Usage:
    from src.application.models import Course, Module, StudentProfile
    from src.application.models import dynamodb_keys as keys
"""

from .course   import Course, Module, CourseStatus, CMSSource, ContentType, IngestionStatus
from .student  import StudentProfile, Enrolment, TeacherCourseAssignment, EnrolmentStatus, TeacherRole
from .progress import ModuleProgress, ProgressStatus
from .quiz     import QuizDefinition, QuizResult, QuizQuestion, QuizAnswer, QuizOption, QuestionType, QuizStatus
from .gap      import KnowledgeGap, LearningPath
from .parent   import ParentChildLink, LinkStatus
from .config   import CMSPluginConfig, DomainConfig, IngestionManifest
from src.application.utils import dynamodb_keys

__all__ = [
    # Course
    "Course", "Module", "CourseStatus", "CMSSource", "ContentType", "IngestionStatus",
    # Student
    "StudentProfile", "Enrolment", "TeacherCourseAssignment", "EnrolmentStatus", "TeacherRole",
    # Progress
    "ModuleProgress", "ProgressStatus",
    # Quiz
    "QuizDefinition", "QuizResult", "QuizQuestion", "QuizAnswer", "QuizOption",
    "QuestionType", "QuizStatus",
    # Gap & Learning Path
    "KnowledgeGap", "LearningPath",
    # Parent
    "ParentChildLink", "LinkStatus",
    # Config
    "CMSPluginConfig", "DomainConfig", "IngestionManifest",
    # Keys
    "dynamodb_keys",
]
