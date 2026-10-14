"""Pydantic schemas for JWT authentication and user sessions.

PROJECT.md §6 & §7: Phase 6 Hardening data contracts.
"""

from pydantic import BaseModel, ConfigDict, Field


class TokenResponse(BaseModel):
    """JWT access token response model."""

    model_config = ConfigDict(extra="ignore")

    access_token: str = Field(..., description="Encoded JWT access token")
    token_type: str = Field(default="bearer", description="Token scheme")
    expires_in: int = Field(..., description="Lifetime of token in seconds")


class TokenPayload(BaseModel):
    """Decoded JWT payload claims."""

    model_config = ConfigDict(extra="ignore")

    sub: str = Field(..., description="Subject identifier (e.g. username or service account)")
    role: str = Field(default="developer", description="Assigned user role")
    exp: int = Field(..., description="Expiration epoch timestamp")
    iat: int = Field(..., description="Issued-at epoch timestamp")


class LoginRequest(BaseModel):
    """Developer / client login request."""

    model_config = ConfigDict(extra="ignore")

    username: str = Field(..., min_length=1, max_length=64, description="Username or client ID")
    password: str = Field(..., min_length=1, max_length=128, description="Authentication secret")


class UserSummary(BaseModel):
    """Authenticated user profile representation."""

    model_config = ConfigDict(extra="ignore")

    username: str
    role: str
