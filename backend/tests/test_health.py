"""Tests for the /api/health endpoint."""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.main import create_app


@pytest.fixture
def app():
    """Create a fresh app instance for each test."""
    return create_app()


@pytest_asyncio.fixture
async def client(app):
    """Async HTTP client wired to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_returns_200(client):
    """GET /api/health returns 200."""
    response = await client.get("/api/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_body_has_status_healthy(client):
    """Response body contains status=healthy."""
    response = await client.get("/api/health")
    body = response.json()
    assert body["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_body_has_valid_timestamp(client):
    """Response body contains a valid ISO 8601 UTC timestamp."""
    before = datetime.now(UTC)
    response = await client.get("/api/health")
    after = datetime.now(UTC)

    body = response.json()
    timestamp = datetime.fromisoformat(body["timestamp"])
    assert before <= timestamp <= after


@pytest.mark.asyncio
async def test_health_returns_json_content_type(client):
    """Content-Type header is application/json."""
    response = await client.get("/api/health")
    assert "application/json" in response.headers["content-type"]
