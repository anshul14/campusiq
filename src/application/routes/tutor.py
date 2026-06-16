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
import src.application.services.bedrock as bedrock
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.application.schemas import TutorHistoryResponse, TutorChatRequest, TutorChatResponse

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


@router.post("/chat", response_model=TutorChatResponse)
async def tutor_chat(body: TutorChatRequest, request: Request):
    """
    Send a message to the Tutor Agent running in Bedrock AgentCore.

    session_id — maintain across turns for multi-turn conversation context.
                 Generate a UUID on the client for a new session.
    message    — the student's question or input.

    The Tutor Agent has access to the student's enrolled course content
    via its Knowledge Base. AgentCore maintains session state between calls
    using the session_id — the caller is responsible for generating and
    persisting a consistent session_id per conversation.
    """
    # user_id available for future use — e.g. audit logging, rate limiting
    user_id = request.state.authorizer["sub"]  # noqa: F841

    response_text = bedrock.invoke_tutor_agent(
        session_id=body.session_id,
        user_message=body.message,
    )

    return TutorChatResponse(
        session_id=body.session_id,
        response=response_text,
    )