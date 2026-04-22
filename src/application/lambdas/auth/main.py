# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Auth Lambda — Entry Point

This Lambda handles all authentication routes:
    - GET  /auth/session  — return current authenticated user session
    - POST /auth/logout   — revoke Cognito refresh token

Trigger:    API Gateway
Memory:     256 MB
Timeout:    10 seconds
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
import os

from src.application.routes.auth import router as auth_router

app = FastAPI(
    title="CampusIQ Auth API",
    description="Authentication — session and logout",
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

app.include_router(auth_router, prefix="/api/v1")

handler = Mangum(app)