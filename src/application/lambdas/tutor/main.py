# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Tutor Lambda — Entry Point

This Lambda handles all AI Tutor routes:
    - POST /tutor/chat    — streaming SSE chat with Bedrock AgentCore
    - GET  /tutor/history — conversation history from ElastiCache Redis

Higher memory and timeout than other Lambdas — Bedrock streaming
responses can take longer and require more memory.

Trigger:    API Gateway
Memory:     1024 MB
Timeout:    30 seconds
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
import os

from src.application.routes.tutor import router as tutor_router

app = FastAPI(
    title="CampusIQ Tutor API",
    description="AI Tutor — streaming chat and conversation history",
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

app.include_router(tutor_router, prefix="/api/v1")

handler = Mangum(app)