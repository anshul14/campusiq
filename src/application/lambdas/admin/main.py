# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Admin Lambda — Entry Point

This Lambda handles all admin routes:
    - User management (list, role assignment)
    - Teacher assignment to courses
    - CMS plugin and domain config
    - CMS sync jobs
    - Parent-child links

Trigger:    API Gateway
Memory:     512 MB
Timeout:    15 seconds
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from src.application.routes.admin import router as admin_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CampusIQ Admin API",
    desription="Admin operations - users, config, CMS sync",
    version="1.0.0",
)

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").strip(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router, prefix="/api/v1")

handler = Mangum(app)
