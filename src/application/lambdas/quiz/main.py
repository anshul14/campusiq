# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Quiz Lambda — Entry Point

This Lambda handles all quiz routes:
    - Submit Quiz
    - Create Quiz

Trigger:    API Gateway
Memory:     512 MB
Timeout:    15 seconds
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from application.routes.quiz import router as quiz_router

app = FastAPI(
    title="CampusIQ Quiz API",
    description="Quiz results, create, delete",
    version="1.0.0",
)

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(quiz_router, prefix="")

handler = Mangum(app)