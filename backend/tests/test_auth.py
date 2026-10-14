"""Tests for JWT authentication and rate limiting.

T6.1: Validates token issuance, verification, expiration, route guards, and rate limiting.
"""

from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.core.config import get_settings
from backend.app.main import app
from backend.app.services.auth import create_access_token
from backend.app.services.rate_limiter import (
    SlidingWindowRateLimiter,
    trigger_rate_limiter,
)


@pytest.mark.asyncio
async def test_token_issuance_success() -> None:
    """Verify POST /api/auth/token returns a valid JWT access token."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/auth/token",
            json={"username": "alice_dev", "password": "securepassword123"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_token_issuance_short_password() -> None:
    """Verify short password rejected with 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/auth/token",
            json={"username": "bob", "password": "12"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_me_endpoint_success() -> None:
    """Verify GET /api/auth/me succeeds with valid Bearer token."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 1. Login to obtain token
        login_res = await client.post(
            "/api/auth/token",
            json={"username": "carol", "password": "mypassword"},
        )
        token = login_res.json()["access_token"]

        # 2. Access protected endpoint
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    user = response.json()
    assert user["username"] == "carol"
    assert user["role"] == "developer"


@pytest.mark.asyncio
async def test_protected_me_endpoint_missing_token() -> None:
    """Verify GET /api/auth/me without authorization header returns 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/auth/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_me_endpoint_invalid_token() -> None:
    """Verify GET /api/auth/me with invalid or tampered token returns 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer not-a-valid-jwt-token"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_token_expiration() -> None:
    """Verify expired JWT token returns 401."""
    settings = get_settings()
    # Create token expired 10 seconds ago
    expired_token = create_access_token(
        subject="expired_user",
        expires_delta=timedelta(seconds=-10),
        settings=settings,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )

    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_sliding_window_rate_limiter_unit() -> None:
    """Verify SlidingWindowRateLimiter permits up to limit then rejects."""
    limiter = SlidingWindowRateLimiter(requests_per_minute=3, window_seconds=10.0)

    # First 3 requests allowed
    ok1, _ = await limiter.check_rate_limit("client-1")
    ok2, _ = await limiter.check_rate_limit("client-1")
    ok3, _ = await limiter.check_rate_limit("client-1")
    assert ok1 is True
    assert ok2 is True
    assert ok3 is True

    # 4th request within window rejected
    ok4, retry_after = await limiter.check_rate_limit("client-1")
    assert ok4 is False
    assert retry_after >= 1

    # Different client key is not blocked
    ok_other, _ = await limiter.check_rate_limit("client-2")
    assert ok_other is True


@pytest.mark.asyncio
async def test_rate_limiter_guard_429() -> None:
    """Verify triggering reviews beyond limit raises HTTP 429 with Retry-After."""
    trigger_rate_limiter.reset()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # Exhaust rate limit quota (10 requests)
        for _ in range(10):
            await client.post(
                "/api/reviews/trigger",
                json={"pr_url": "https://github.com/org/repo/pull/1"},
            )

        # 11th request triggers 429
        overflow_res = await client.post(
            "/api/reviews/trigger",
            json={"pr_url": "https://github.com/org/repo/pull/1"},
        )

    assert overflow_res.status_code == 429
    assert "Retry-After" in overflow_res.headers
    assert "Rate limit exceeded" in overflow_res.json()["detail"]

    # Reset for other tests
    trigger_rate_limiter.reset()
