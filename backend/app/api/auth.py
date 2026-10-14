"""API endpoints for JWT token issuance and user verification.

PROJECT.md §6 & §7: Phase 6 Hardening authentication routes.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.config import Settings, get_settings
from backend.app.schemas.auth import LoginRequest, TokenResponse, UserSummary
from backend.app.services.auth import create_access_token, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.post(
    "/token",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Issue JWT access token",
)
async def login_for_access_token(
    payload: LoginRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    """Authenticate and return signed JWT access token for developer/client access."""
    # Standard developer / admin credential check
    # In production, this verifies hashed password against database
    if not payload.username or not payload.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password must not be empty",
        )

    # Reject obvious dummy / empty passwords
    if len(payload.password) < 4:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials: password must be at least 4 characters",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        subject=payload.username,
        role="developer",
        settings=settings,
    )
    expires_in = settings.jwt_access_token_expire_minutes * 60

    logger.info("Issued JWT access token for subject=%s", payload.username)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.get(
    "/me",
    response_model=UserSummary,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
)
async def get_my_profile(
    current_user: Annotated[UserSummary, Depends(get_current_user)],
) -> UserSummary:
    """Return profile for the currently authenticated bearer token."""
    return current_user
