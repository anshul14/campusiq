# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Assessment Lambda

NOTE: Unlike the other event-driven Lambdas, the Assessment Lambda
is HTTP-triggered via API Gateway — not EventBridge. It lives here
because it uses Bedrock InvokeModel directly (not AgentCore) and
has no conversational memory requirement.

Handles:
    POST /api/v1/courses/{courseId}/modules/{moduleId}/quiz/generate

Flow:
    1. Read module content from S3
    2. Build quiz generation prompt
    3. Call Bedrock InvokeModel (Claude 3 Haiku)
    4. Parse structured JSON response
    5. Write quiz draft to DynamoDB

Trigger:    API Gateway (HTTP)
Memory:     512 MB
Timeout:    30 seconds
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
import os

# Assessment routes are part of the quiz router
# This Lambda only handles the /quiz/generate route
# In Phase 3 this will be refactored to a dedicated quiz_generate router
from src.application.routes.courses import router as courses_router

app = FastAPI(
    title="CampusIQ Assessment API",
    description="AI quiz generation from module content",
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

app.include_router(courses_router, prefix="/api/v1")

handler = Mangum(app)