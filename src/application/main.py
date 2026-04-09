# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
CampusIQ API — Application Entry Point

This module creates the FastAPI application instance, registers all
route groups, configures middleware, and exposes the Mangum handler
for AWS Lambda invocation.

Architecture:
    API Gateway receives the HTTP request and invokes the Lambda function.
    Mangum translates the API Gateway event into an ASGI scope that
    FastAPI understands. The Lambda Authorizer runs before every route
    handler and injects the authenticated user context into request.state.

Middleware:
    CORSMiddleware — allows the Next.js frontend to call the API
    cross-origin. Allowed origins are set via the ALLOWED_ORIGINS
    environment variable configured by CDK at deploy time.

Lambda Handler:
    handler = Mangum(app)
    AWS Lambda invokes handler(event, context) on every API request.
    The CDK stack sets the Lambda handler to 'main.handler'.

Local Development:
    Run with uvicorn: uvicorn src.application.main:app --reload
    The Mangum handler is not used locally — Uvicorn acts as the
    ASGI server instead.
"""



from fastapi import FastAPI
from mangum import Mangum
from fastapi.middleware.cors import CORSMiddleware
import os
from src.application.routes.auth import router as auth_router
from src.application.routes.courses import router as courses_router

app = FastAPI(
    title="CampusIQ API",
    description="AI-native adaptive learning platform",
    version="0.1.0",
)

# CORS — origins come from environment variable set by CDK
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(courses_router, prefix="/api/v1")
handler = Mangum(app)
