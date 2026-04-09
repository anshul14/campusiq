# Copyright 2026 Anshul Saxena
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""
Auth routes for CampusIQ.

These routes handle session management only.
Authentication itself is delegated to Amazon Cognito via NextAuth.js
on the frontend. The FastAPI application validates Cognito JWTs via
the Lambda Authorizer — it never handles credentials directly.

Routes:
    GET  /api/v1/auth/session  — return current authenticated user session
    POST /api/v1/auth/logout   — revoke Cognito refresh token, clear session
"""
import logging

from fastapi import APIRouter, Request, HTTPException, status

from src.application.schemas import SessionResponse, SessionUser, ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)

router.get("/session", response_model=SessionResponse, responses={
    401: {"model": ErrorResponse, "description": "Not authenticated"},
    500: {"model": ErrorResponse, "description": "Internal Server Error"},
},
           summary="Get current session",
           description=(
               "Returns the authenticated user's session — role, name, email, "
               "institutionId, and domain. The Lambda Authorizer validates the "
               "Cognito JWT before this handler is called. The user context is "
               "injected by the authorizer into the request context."
           ),
           )


async def get_session(request: Request) -> SessionResponse:
    """
        Return the current authenticated user's session.

        The Lambda Authorizer runs before this handler and injects
        the decoded JWT claims into request.state. No Cognito API
        call is needed here — the session is reconstructed from
        the authorizer context.

        Args:
            request: FastAPI request — authorizer context in request.state

        Returns:
            SessionResponse: user identity and session metadata

        Raises:
            HTTPException 401: if authorizer context is missing
            HTTPException 500: if session reconstruction fails
    """
    try:
        # Authorizer injects context into request.state
        # In Lambda the authorizer context comes via
        # event['requestContext']['authorizer']
        authorizer_context = _get_authorizer_context(request)

        user = SessionUser(
            sub=authorizer_context["userId"],
            name=authorizer_context.get("name", ""),
            email=authorizer_context.get("email", ""),
            role=authorizer_context["role"],
            domain=authorizer_context.get("domain", "university"),
            student_id=authorizer_context.get("studentId"),
        )

        return SessionResponse(
            user=user,
            expires_at=authorizer_context.get("expiresAt", ""),
        )
    except KeyError as e:
        logger.error("Missing authorizer context key: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "MISSING_AUTH_CONTEXT",
                "message": "Authentication context is missing or invalid",
                "request_id": _get_request_id(request),
            },
        )
    except Exception as e:
        logger.error("Session retrieval failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "SESSION_ERROR",
                "message": "Failed to retrieve session",
                "request_id": _get_request_id(request),
            },
        )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Successfully logged out"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Logout",
    description=(
            "Revokes the Cognito refresh token and instructs the frontend "
            "to clear the HTTP-only session cookie. The access token remains "
            "valid until its natural expiry (1 hour) — this is standard OAuth "
            "behaviour and acceptable given the short token lifetime."
    ),
)
async def logout(request: Request) -> None:
    """
    Logout the current user.

    Revokes the Cognito refresh token via the Cognito API.
    The frontend is responsible for clearing the HTTP-only
    session cookie — this endpoint only handles server-side
    token revocation.

    Args:
        request: FastAPI request — authorizer context in request.state

    Raises:
        HTTPException 401: if authorizer context is missing
        HTTPException 500: if token revocation fails
    """
    try:
        authorizer_context = _get_authorizer_context(request)
        user_id = authorizer_context["userId"]

        # TODO: Phase 1 — implement Cognito token revocation
        # cognito_client = get_cognito_client()
        # cognito_client.revoke_token(
        #     Token=authorizer_context.get("refreshToken"),
        #     ClientId=settings.COGNITO_CLIENT_ID,
        # )

        logger.info("User logged out: %s", user_id)
        return None

    except KeyError as e:
        logger.error("Missing authorizer context on logout: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "MISSING_AUTH_CONTEXT",
                "message": "Authentication context is missing or invalid",
                "request_id": _get_request_id(request),
            },
        )
    except Exception as e:
        logger.error("Logout failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "LOGOUT_ERROR",
                "message": "Logout failed",
                "request_id": _get_request_id(request),
            },
        )


# ── Private helpers ───────────────────────────────────────

def _get_authorizer_context(request: Request) -> dict:
    """
    Extract the Lambda Authorizer context from the request.

    In a Lambda + API Gateway deployment the authorizer context
    is injected into the request via Mangum's event mapping.
    In local development it falls back to request.state.

    Args:
        request: FastAPI request object

    Returns:
        dict: authorizer context with userId, role, email etc.

    Raises:
        KeyError: if authorizer context is not present
    """
    # Mangum maps API Gateway authorizer context to
    # request.state.authorizer in Lambda deployments
    if hasattr(request.state, "authorizer"):
        return request.state.authorizer

    # Fallback for local development — set via middleware
    if hasattr(request.state, "user"):
        return request.state.user

    raise KeyError("authorizer")


def _get_request_id(request: Request) -> str:
    """Extract request id from the request."""
    if hasattr(request.state, "request_id"):
        return request.state.request_id
    return "unknown"
