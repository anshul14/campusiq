# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Students Lambda — Entry Point

This Lambda handles all student routes:
    - Student profile (/me and by ID)
    - Enrolments
    - Module and course progress
    - Knowledge gaps
    - Learning path (get and refresh)
    - Quiz results (own)

Trigger:    API Gateway
Memory:     512 MB
Timeout:    15 seconds
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
import os

from src.application.routes.students import router as students_router

app = FastAPI(
    title="CampusIQ Students API",
    description="Student profile, progress, gaps, and learning path",
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

app.include_router(students_router, prefix="/api/v1")

handler = Mangum(app)