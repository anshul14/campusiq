# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Parent Lambda — Entry Point

This Lambda handles all K-12 parent routes:
    - GET /parent/children                          — linked children
    - GET /parent/children/{studentId}/progress     — child progress summary

Read-only access to linked child data only.
Lambda Authorizer enforces parent-child link before allowing access.

Trigger:    API Gateway
Memory:     256 MB
Timeout:    10 seconds
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
import os

from src.application.routes.parent import router as parent_router

app = FastAPI(
    title="CampusIQ Parent API",
    description="Parent portal — K-12 child progress (read-only)",
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

app.include_router(parent_router, prefix="/api/v1")

handler = Mangum(app)