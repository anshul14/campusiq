# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Tutor routes for CampusIQ.

These routes handle tutor chat and history operations.

"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.application.schemas import TutorHistoryResponse, TutorChatRequest

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/tutor",
    tags=["tutor"]
)


@router.post("/chat")
async def chat_with_tutor(body: TutorChatRequest, request: Request) -> StreamingResponse:
    async def generate_tutor_stream():
        yield 'data: {"token": "hello", "done": false}\n\n'
        yield 'data: {"done": true}\n\n'

    return StreamingResponse(
        generate_tutor_stream(),
        media_type="text/event-stream",
    )


@router.get("/history", response_model=TutorHistoryResponse)
async def get_tutor_history(
        request: Request,
        course_id: str = None,
        limit: int = 20,
) -> TutorHistoryResponse:
    pass
