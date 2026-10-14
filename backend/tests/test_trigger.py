"""Tests for PR URL parsing, repository/PR persistence, and review trigger endpoints."""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.api.reviews import get_github_client
from backend.app.core.config import Settings, get_settings
from backend.app.core.database import Base, get_db_session
from backend.app.main import create_app
from backend.app.repositories.review import (
    PullRequestRepository,
    RepositoryRepository,
    ReviewRepository,
)
from backend.app.services.github_client import GitHubClient
from backend.app.services.pr_trigger import (
    parse_github_pr_url,
    trigger_pr_review,
)
from backend.tests.fixtures.github_fixtures import SAMPLE_PR_RESPONSE


@pytest.fixture
def test_settings() -> Settings:
    """Settings instance for trigger tests."""
    return Settings(
        app_env="test",
        log_level="warning",
        github_token="ghp_test_token_12345",
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


def make_mock_github_client(
    status_code: int = 200,
    json_data: dict[str, Any] | None = None,
) -> GitHubClient:
    """Create a GitHubClient backed by an in-memory MockTransport."""

    def handler(request: httpx.Request) -> httpx.Response:
        if status_code == 200:
            return httpx.Response(200, json=json_data or SAMPLE_PR_RESPONSE)
        return httpx.Response(status_code, json={"message": "Mock error"})

    transport = httpx.MockTransport(handler)
    return GitHubClient(token="ghp_test_token", transport=transport)


@pytest.fixture
async def client(
    test_settings: Settings,
    test_session: AsyncSession,
) -> AsyncIterator[AsyncClient]:
    """Async test client with dependency overrides."""
    mock_gh = make_mock_github_client(200, SAMPLE_PR_RESPONSE)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = lambda: test_session
    app.dependency_overrides[get_github_client] = lambda: mock_gh

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac

    await mock_gh.close()


# -----------------------------------------------------------------------------
# Unit Tests: URL Parser
# -----------------------------------------------------------------------------


def test_parse_github_pr_url_valid() -> None:
    """Verify valid GitHub PR URLs in various formats."""
    assert parse_github_pr_url("https://github.com/octocat/Spoon-Knife/pull/1") == (
        "octocat",
        "Spoon-Knife",
        1,
    )
    assert parse_github_pr_url("http://github.com/fastapi/fastapi/pull/42/") == (
        "fastapi",
        "fastapi",
        42,
    )
    assert parse_github_pr_url("https://github.com/facebook/react/pull/999/files") == (
        "facebook",
        "react",
        999,
    )
    assert parse_github_pr_url("https://github.com/facebook/react/pull/999#discussion") == (
        "facebook",
        "react",
        999,
    )
    assert parse_github_pr_url("github.com/owner/repo.git/pull/10") == (
        "owner",
        "repo",
        10,
    )


def test_parse_github_pr_url_invalid() -> None:
    """Verify malformed or invalid URLs raise ValueError."""
    invalid_urls = [
        "",
        "   ",
        "https://gitlab.com/owner/repo/pull/1",
        "https://github.com/owner/repo",
        "https://github.com/owner/repo/issues/10",
        "https://github.com/owner/repo/pull/notanumber",
        "https://github.com/owner/repo/pull/0",
        "https://github.com/owner/repo/pull/-5",
    ]
    for url in invalid_urls:
        with pytest.raises(ValueError):
            parse_github_pr_url(url)


# -----------------------------------------------------------------------------
# Unit Tests: Repositories
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repository_and_pr_repositories(test_session: AsyncSession) -> None:
    """Verify CRUD and idempotency behavior of Repository and PullRequest repos."""
    repo_repo = RepositoryRepository(test_session)
    pr_repo = PullRequestRepository(test_session)
    review_repo = ReviewRepository(test_session)

    # 1. Get or create repository
    repo1 = await repo_repo.get_or_create(owner="octocat", name="Hello-World")
    await test_session.commit()
    assert repo1.id is not None
    assert repo1.full_name == "octocat/hello-world"

    # Idempotent re-fetch
    repo2 = await repo_repo.get_or_create(owner="octocat", name="Hello-World")
    assert repo1.id == repo2.id

    # 2. Upsert pull request
    pr1 = await pr_repo.upsert(
        repository_id=repo1.id,
        number=101,
        title="Initial PR",
        state="open",
        author="octocat",
        head_sha="head123",
        base_sha="base123",
        head_ref="feature",
        base_ref="main",
        html_url="https://github.com/octocat/Hello-World/pull/101",
    )
    await test_session.commit()
    assert pr1.id is not None
    assert pr1.title == "Initial PR"

    # Update PR fields
    pr2 = await pr_repo.upsert(
        repository_id=repo1.id,
        number=101,
        title="Updated PR Title",
        state="open",
        author="octocat",
        head_sha="head456",
        base_sha="base123",
        head_ref="feature",
        base_ref="main",
        html_url="https://github.com/octocat/Hello-World/pull/101",
    )
    await test_session.commit()
    assert pr2.id == pr1.id
    assert pr2.title == "Updated PR Title"
    assert pr2.head_sha == "head456"

    # 3. Create and query review
    review = await review_repo.create_review(
        pull_request_id=pr1.id,
        model="fake-llm",
        status="queued",
    )
    await test_session.commit()
    assert review.id is not None
    assert review.status == "queued"

    loaded_review = await review_repo.get_by_id(review.id)
    assert loaded_review is not None
    assert loaded_review.pull_request.number == 101
    assert loaded_review.pull_request.repository.full_name == "octocat/hello-world"

    # Update status
    updated = await review_repo.update_status(
        review_id=review.id,
        status="completed",
        tokens_total=150,
        cost_usd=0.002,
    )
    await test_session.commit()
    assert updated is not None
    assert updated.status == "completed"
    assert updated.tokens_total == 150
    assert updated.cost_usd == 0.002


# -----------------------------------------------------------------------------
# Service Tests: trigger_pr_review
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_pr_review_service(test_session: AsyncSession) -> None:
    """Verify trigger service orchestrates GitHub fetch, persistence, and review queueing."""
    mock_gh = make_mock_github_client(200, SAMPLE_PR_RESPONSE)
    pr_url = "https://github.com/octocat/Hello-World/pull/101"

    review = await trigger_pr_review(
        session=test_session,
        github_client=mock_gh,
        pr_url=pr_url,
        config={"system": "multi_agent_judge"},
        model="fake-llm",
    )
    await mock_gh.close()

    assert review.id is not None
    assert review.status == "queued"
    assert review.trigger_type == "manual"
    assert review.model == "fake-llm"
    assert review.pull_request.number == 101
    assert review.pull_request.repository.full_name == "octocat/hello-world"
    assert review.pull_request.head_sha == "7d9b9a6d89283f3e1b01c34a2c9182390234abcd"


# -----------------------------------------------------------------------------
# API Route Tests: POST /api/reviews/trigger and GET /api/reviews
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_trigger_success(client: AsyncClient) -> None:
    """Verify POST /api/reviews/trigger enqueues review and returns 201 Created."""
    response = await client.post(
        "/api/reviews/trigger",
        json={"pr_url": "https://github.com/octocat/Hello-World/pull/101"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "queued"
    assert data["pr_number"] == 101
    assert data["repository"] == "octocat/hello-world"
    assert data["trigger_type"] == "manual"
    assert data["model"] == "fake-llm"
    assert "id" in data

    # Test GET /api/reviews/{id}
    review_id = data["id"]
    get_res = await client.get(f"/api/reviews/{review_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == review_id

    # Test GET /api/reviews
    list_res = await client.get("/api/reviews")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert list_data["items"][0]["id"] == review_id

    # Test GET /api/reviews with status filter
    filter_res = await client.get("/api/reviews?status=queued")
    assert filter_res.status_code == 200
    assert filter_res.json()["total"] >= 1

    empty_res = await client.get("/api/reviews?status=failed")
    assert empty_res.status_code == 200
    assert empty_res.json()["total"] == 0

    # Test GET /api/reviews/{id}/diff
    diff_res = await client.get(f"/api/reviews/{review_id}/diff")
    assert diff_res.status_code == 200
    assert "diff_text" in diff_res.json()


@pytest.mark.asyncio
async def test_post_trigger_invalid_url(client: AsyncClient) -> None:
    """Verify POST /api/reviews/trigger rejects invalid URLs with 422."""
    response = await client.post(
        "/api/reviews/trigger",
        json={"pr_url": "https://gitlab.com/not/github/pull/1"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_trigger_not_found(
    test_settings: Settings,
    test_session: AsyncSession,
) -> None:
    """Verify POST /api/reviews/trigger returns 404 when PR is not found on GitHub."""
    mock_gh_404 = make_mock_github_client(404)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = lambda: test_session
    app.dependency_overrides[get_github_client] = lambda: mock_gh_404

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        response = await ac.post(
            "/api/reviews/trigger",
            json={"pr_url": "https://github.com/octocat/Hello-World/pull/999"},
        )
        assert response.status_code == 404

    await mock_gh_404.close()


@pytest.mark.asyncio
async def test_post_trigger_rate_limited(
    test_settings: Settings,
    test_session: AsyncSession,
) -> None:
    """Verify POST /api/reviews/trigger returns 429 when GitHub rate limit is exceeded."""
    mock_gh_429 = make_mock_github_client(429)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = lambda: test_session
    app.dependency_overrides[get_github_client] = lambda: mock_gh_429

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        response = await ac.post(
            "/api/reviews/trigger",
            json={"pr_url": "https://github.com/octocat/Hello-World/pull/101"},
        )
        assert response.status_code == 429

    await mock_gh_429.close()


@pytest.mark.asyncio
async def test_get_review_nonexistent(client: AsyncClient) -> None:
    """Verify GET /api/reviews/{id} returns 404 for unknown review ID."""
    response = await client.get("/api/reviews/99999")
    assert response.status_code == 404
