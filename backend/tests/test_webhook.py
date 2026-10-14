"""Tests for GitHub webhook signature verification, idempotency, and endpoints."""

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.core.config import Settings, get_settings
from backend.app.core.database import Base, get_db_session
from backend.app.main import create_app
from backend.app.repositories.webhook_delivery import WebhookDeliveryRepository
from backend.app.services.github_webhook import (
    MAX_WEBHOOK_PAYLOAD_BYTES,
    compute_signature,
    verify_signature,
)

TEST_SECRET = "test-webhook-secret-12345"


@pytest.fixture
def test_settings() -> Settings:
    """Settings instance with configured webhook secret for tests."""
    return Settings(
        app_env="test",
        log_level="warning",
        github_webhook_secret=TEST_SECRET,
    )


@pytest.fixture
async def test_session() -> AsyncIterator[AsyncSession]:
    """Provide an in-memory SQLite async session with all tables created."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def client(test_settings: Settings, test_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Async test client with dependency overrides for settings and db session."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: test_settings

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield test_session

    app.dependency_overrides[get_db_session] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def sample_pr_payload() -> dict[str, Any]:
    """Minimal valid GitHub pull_request webhook payload."""
    return {
        "action": "opened",
        "number": 42,
        "pull_request": {
            "id": 1001,
            "number": 42,
            "title": "feat: add user authentication",
            "state": "open",
            "html_url": "https://github.com/owner/repo/pull/42",
            "head": {"sha": "abc123head", "ref": "feature-branch"},
            "base": {"sha": "def456base", "ref": "main"},
            "draft": False,
        },
        "repository": {
            "id": 99999,
            "name": "repo",
            "full_name": "owner/repo",
            "private": False,
            "html_url": "https://github.com/owner/repo",
        },
        "sender": {"login": "octocat"},
    }


# ─────────────────────────────────────────────────────────────
# Unit Tests: Signature Verification
# ─────────────────────────────────────────────────────────────


def test_compute_and_verify_signature_valid() -> None:
    payload = b'{"hello": "world"}'
    sig = compute_signature(payload, TEST_SECRET)
    assert sig.startswith("sha256=")
    assert verify_signature(payload, sig, TEST_SECRET) is True


def test_verify_signature_tampered_payload_fails() -> None:
    payload = b'{"hello": "world"}'
    sig = compute_signature(payload, TEST_SECRET)
    tampered = b'{"hello": "tampered"}'
    assert verify_signature(tampered, sig, TEST_SECRET) is False


def test_verify_signature_invalid_header_format_fails() -> None:
    payload = b'{"hello": "world"}'
    assert verify_signature(payload, "invalid_no_prefix", TEST_SECRET) is False
    assert verify_signature(payload, None, TEST_SECRET) is False
    assert verify_signature(payload, "", TEST_SECRET) is False


def test_verify_signature_empty_secret_fails() -> None:
    payload = b'{"hello": "world"}'
    sig = compute_signature(payload, TEST_SECRET)
    assert verify_signature(payload, sig, "") is False


# ─────────────────────────────────────────────────────────────
# Unit Tests: Repository Idempotency
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_repository_creates_and_retrieves_delivery(test_session: AsyncSession) -> None:
    repo = WebhookDeliveryRepository(test_session)
    delivery = await repo.create_delivery(
        delivery_id="del-unique-100",
        event_type="pull_request",
        action="opened",
        payload={"key": "val"},
        status="received",
    )
    assert delivery.id is not None
    assert delivery.delivery_id == "del-unique-100"

    fetched = await repo.get_by_delivery_id("del-unique-100")
    assert fetched is not None
    assert fetched.id == delivery.id
    assert fetched.event_type == "pull_request"
    assert fetched.action == "opened"

    non_existent = await repo.get_by_delivery_id("does-not-exist")
    assert non_existent is None


# ─────────────────────────────────────────────────────────────
# Integration Tests: Webhook HTTP Endpoint & Idempotency
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_missing_signature_returns_401(
    client: AsyncClient, sample_pr_payload: dict[str, Any]
) -> None:
    body = json.dumps(sample_pr_payload).encode("utf-8")
    headers = {
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": "del-uuid-001",
        "Content-Type": "application/json",
    }
    response = await client.post("/api/webhook/github", content=body, headers=headers)
    assert response.status_code == 401
    assert "Invalid or missing" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_invalid_signature_returns_401(
    client: AsyncClient, sample_pr_payload: dict[str, Any]
) -> None:
    body = json.dumps(sample_pr_payload).encode("utf-8")
    headers = {
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": "del-uuid-002",
        "X-Hub-Signature-256": "sha256=0000000000000000000000000000000000000000000000000000000000000000",
        "Content-Type": "application/json",
    }
    response = await client.post("/api/webhook/github", content=body, headers=headers)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_missing_required_headers_returns_422(
    client: AsyncClient, sample_pr_payload: dict[str, Any]
) -> None:
    body = json.dumps(sample_pr_payload).encode("utf-8")
    sig = compute_signature(body, TEST_SECRET)
    headers = {
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": sig,
        "Content-Type": "application/json",
    }
    response = await client.post("/api/webhook/github", content=body, headers=headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_webhook_valid_ping_event_returns_200(client: AsyncClient) -> None:
    ping_payload = {"zen": "Non-blocking is better than blocking.", "hook_id": 12345}
    body = json.dumps(ping_payload).encode("utf-8")
    sig = compute_signature(body, TEST_SECRET)
    headers = {
        "X-GitHub-Event": "ping",
        "X-GitHub-Delivery": "delivery-ping-99",
        "X-Hub-Signature-256": sig,
        "Content-Type": "application/json",
    }
    response = await client.post("/api/webhook/github", content=body, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["message"] == "pong"
    assert data["delivery_id"] == "delivery-ping-99"


@pytest.mark.asyncio
async def test_webhook_valid_pull_request_returns_202(
    client: AsyncClient, sample_pr_payload: dict[str, Any]
) -> None:
    body = json.dumps(sample_pr_payload).encode("utf-8")
    sig = compute_signature(body, TEST_SECRET)
    headers = {
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": "delivery-pr-42",
        "X-Hub-Signature-256": sig,
        "Content-Type": "application/json",
    }
    response = await client.post("/api/webhook/github", content=body, headers=headers)
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["event"] == "pull_request"
    assert data["action"] == "opened"
    assert data["delivery_id"] == "delivery-pr-42"
    assert data["repository"] == "owner/repo"
    assert data["pr_number"] == 42
    assert "review_id" in data
    assert isinstance(data["review_id"], int)


@pytest.mark.asyncio
async def test_webhook_idempotency_duplicate_delivery_rejected(
    client: AsyncClient, sample_pr_payload: dict[str, Any], test_session: AsyncSession
) -> None:
    body = json.dumps(sample_pr_payload).encode("utf-8")
    sig = compute_signature(body, TEST_SECRET)
    delivery_id = "delivery-duplicate-test-123"
    headers = {
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": delivery_id,
        "X-Hub-Signature-256": sig,
        "Content-Type": "application/json",
    }

    # First delivery: should be accepted (HTTP 202)
    first_response = await client.post("/api/webhook/github", content=body, headers=headers)
    assert first_response.status_code == 202
    assert first_response.json()["status"] == "accepted"

    # Second delivery with identical delivery_id: should return duplicate (HTTP 200)
    second_response = await client.post("/api/webhook/github", content=body, headers=headers)
    assert second_response.status_code == 200
    second_data = second_response.json()
    assert second_data["status"] == "duplicate"
    assert second_data["delivery_id"] == delivery_id
    assert "already received" in second_data["message"]

    # Verify only one record exists in DB
    repo = WebhookDeliveryRepository(test_session)
    saved = await repo.get_by_delivery_id(delivery_id)
    assert saved is not None
    assert saved.delivery_id == delivery_id


@pytest.mark.asyncio
async def test_webhook_unhandled_event_returns_ignored(client: AsyncClient) -> None:
    body = b'{"action": "created"}'
    sig = compute_signature(body, TEST_SECRET)
    headers = {
        "X-GitHub-Event": "star",
        "X-GitHub-Delivery": "del-star-1",
        "X-Hub-Signature-256": sig,
        "Content-Type": "application/json",
    }
    response = await client.post("/api/webhook/github", content=body, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ignored"
    assert data["event"] == "star"


@pytest.mark.asyncio
async def test_webhook_unconfigured_secret_returns_500(test_session: AsyncSession) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_env="test",
        log_level="warning",
        github_webhook_secret="",  # Unconfigured
    )

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield test_session

    app.dependency_overrides[get_db_session] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        headers = {
            "X-GitHub-Event": "ping",
            "X-GitHub-Delivery": "del-1",
            "X-Hub-Signature-256": "sha256=dummy",
            "Content-Type": "application/json",
        }
        response = await c.post("/api/webhook/github", content=b"{}", headers=headers)
        assert response.status_code == 500
        assert "not configured" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_payload_exceeding_size_limit_returns_413(
    client: AsyncClient,
) -> None:
    oversized_body = b"x" * (MAX_WEBHOOK_PAYLOAD_BYTES + 1)
    sig = compute_signature(oversized_body, TEST_SECRET)
    headers = {
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": "del-large",
        "X-Hub-Signature-256": sig,
        "Content-Type": "application/json",
    }
    response = await client.post("/api/webhook/github", content=oversized_body, headers=headers)
    assert response.status_code == 413
    assert "exceeds" in response.json()["detail"]
