# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Teacher Lambda — Entry Point

This Lambda handles all teacher-facing routes:
    - GET /teachers/me/courses         — teacher's assigned courses
    - GET /courses/{courseId}/dashboard — faculty dashboard composite
    - GET /courses/{courseId}/at-risk   — at-risk students (GSI3)
    - GET /courses/{courseId}/gaps      — concept gap heatmap (GSI3)
    - GET /courses/{courseId}/progress  — all student progress (GSI1)

Queries DynamoDB via GSI1 (course-scoped) and GSI3 (at-risk detection).

Trigger:    API Gateway
Memory:     512 MB
Timeout:    15 seconds
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
import os

from src.application.routes.teacher import router as teacher_router

app = FastAPI(
    title="CampusIQ Teacher API",
    description="Teacher dashboard — courses, progress, gaps, at-risk",
    version="0.1.0",
)

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(teacher_router, prefix="/api/v1")

handler = Mangum(app)