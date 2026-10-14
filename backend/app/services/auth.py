"""JWT authentication and authorization service.

PROJECT.md §6 & §7: Phase 6 Hardening - token issuance, verification, and route guards.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.core.config import Settings, get_settings
from backend.app.schemas.auth import TokenPayload, UserSummary

logger = logging.getLogger(__name__)

security_bearer = HTTPBearer(auto_error=False)


def create_access_token(
    subject: str,
    role: str = "developer",
    expires_delta: timedelta | None = None,
    settings: Settings | None = None,
) -> str:
    """Encode a signed JWT access token for a user or client."""
    cfg = settings or get_settings()
    now = datetime.now(UTC)
    lifetime = expires_delta or timedelta(minutes=cfg.jwt_access_token_expire_minutes)
    expire_at = now + lifetime

    payload = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire_at.timestamp()),
    }

    return jwt.encode(payload, cfg.jwt_secret_key, algorithm=cfg.jwt_algorithm)


def decode_access_token(
    token: str,
    settings: Settings | None = None,
) -> TokenPayload:
    """Decode and validate a signed JWT token."""
    cfg = settings or get_settings()
    try:
        decoded = jwt.decode(
            token,
            cfg.jwt_secret_key,
            algorithms=[cfg.jwt_algorithm],
        )
        return TokenPayload.model_validate(decoded)
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err
    except (jwt.InvalidTokenError, Exception) as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or malformed authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(security_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserSummary:
    """FastAPI dependency to require and extract an authenticated user."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials, settings=settings)
    return UserSummary(username=payload.sub, role=payload.role)


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(security_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserSummary | None:
    """FastAPI dependency for endpoints that optionally authenticate."""
    if credentials is None or not credentials.credentials:
        return None
    try:
        payload = decode_access_token(credentials.credentials, settings=settings)
        return UserSummary(username=payload.sub, role=payload.role)
    except HTTPException:
        return None
