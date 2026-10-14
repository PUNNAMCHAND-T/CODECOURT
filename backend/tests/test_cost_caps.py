"""Tests for review budget caps, LangGraph circuit breaker, and tenant daily spend limits.

PROJECT.md §6 & §7: Phase 6 Hardening - T6.2 Cost caps verification.
"""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.agents.graph import run_review_pipeline
from backend.app.api.reviews import get_github_client
from backend.app.core.config import Settings, get_settings
from backend.app.core.database import Base, get_db_session
from backend.app.llm.fake import FakeLLMClient
from backend.app.main import create_app
from backend.app.models.pull_request import PullRequest
from backend.app.models.repository import Repository
from backend.app.models.review import Review
from backend.app.services.cost_caps import (
    BudgetExceededError,
    check_review_circuit_breaker,
    check_tenant_daily_budget,
    enforce_tenant_daily_budget,
    get_repository_24h_spend,
)
from backend.app.services.github_client import GitHubClient
from backend.tests.fixtures.github_fixtures import SAMPLE_PR_RESPONSE


@pytest.fixture
def test_settings() -> Settings:
    """Settings with explicit budget limits for testing."""
    return Settings(
        app_env="test",
        log_level="warning",
        max_review_budget_usd=0.50,
        tenant_daily_budget_usd=10.00,
        circuit_breaker_token_limit=50_000,
    )


@pytest.fixture
async def test_session() -> AsyncIterator[AsyncSession]:
    """In-memory SQLite async session with schema initialized."""
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


def make_mock_github_client(payload: dict[str, Any] | None = None) -> GitHubClient:
    """Mock GitHubClient returning standard PR payload."""
    data = payload or SAMPLE_PR_RESPONSE

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=data)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://api.github.com")
    gh = GitHubClient(token="mock_token")
    gh._client = client
    return gh


# ── Circuit Breaker Unit Tests ──


def test_check_review_circuit_breaker_under_budget() -> None:
    """Verify circuit breaker permits execution when spend and tokens are within bounds."""
    state = {
        "cost_usd": 0.05,
        "max_budget_usd": 0.50,
        "tokens_prompt": 1000,
        "tokens_completion": 500,
    }
    tripped, reason = check_review_circuit_breaker(state, max_budget_usd=0.50)
    assert not tripped
    assert reason is None


def test_check_review_circuit_breaker_cost_exceeded() -> None:
    """Verify circuit breaker trips when cumulative cost reaches or exceeds ceiling."""
    state = {
        "cost_usd": 0.52,
        "max_budget_usd": 0.50,
        "tokens_prompt": 1000,
        "tokens_completion": 500,
    }
    tripped, reason = check_review_circuit_breaker(state, max_budget_usd=0.50)
    assert tripped
    assert reason is not None
    assert "$0.50" in reason
    assert "$0.5200" in reason


def test_check_review_circuit_breaker_token_limit_exceeded() -> None:
    """Verify circuit breaker trips when cumulative token usage reaches limit."""
    state = {
        "cost_usd": 0.01,
        "max_budget_usd": 0.50,
        "tokens_prompt": 30_000,
        "tokens_completion": 25_000,
    }
    tripped, reason = check_review_circuit_breaker(state, token_limit=50_000)
    assert tripped
    assert reason is not None
    assert "token limit" in reason
    assert "55,000" in reason


def test_check_review_circuit_breaker_flag_preserved() -> None:
    """Verify pre-tripped circuit breaker flag is respected."""
    state = {
        "circuit_breaker_tripped": True,
        "circuit_breaker_reason": "Pre-existing trip",
    }
    tripped, reason = check_review_circuit_breaker(state)
    assert tripped
    assert reason == "Pre-existing trip"


# ── Graph Circuit Breaker Execution Tests ──


@pytest.mark.asyncio
async def test_circuit_breaker_halts_reviewers_and_marks_partial() -> None:
    """Verify circuit breaker halts reviewer LLM calls when budget breached and returns partial."""
    fake_llm = FakeLLMClient(
        responses=[
            '{"summary": "Test review", "findings": []}',
        ],
        model="gemini-1.5-flash",
    )

    diff = "--- a/file.py\n+++ b/file.py\n@@ -1,1 +1,1 @@\n-old\n+new\n"

    # Run review with budget of 0.0 so circuit breaker immediately trips
    result = await run_review_pipeline(
        owner="octocat",
        repo="Hello-World",
        pull_number=42,
        head_sha="6dcb09b5b57875f334f61aebed695e2e4193db5e",
        diff_text=diff,
        config="single_agent",
        dry_run=True,
        llm_client=fake_llm,
        max_budget_usd=0.0,
    )

    # Review finishes with partial status and circuit breaker trace
    assert result["status"] == "partial"
    traces = result.get("traces", [])
    cb_nodes = [t for t in traces if t.get("circuit_breaker_tripped")]
    assert len(cb_nodes) > 0
    # Ensure LLM was skipped
    assert len(fake_llm.calls) == 0


# ── Tenant 24h Spend & Budget Tests ──


@pytest.mark.asyncio
async def test_get_repository_24h_spend_calculation(test_session: AsyncSession) -> None:
    """Verify calculation of cumulative spend over rolling 24 hours."""
    repo = Repository(owner="org", name="repo", full_name="org/repo", default_branch="main")
    test_session.add(repo)
    await test_session.flush()

    pr = PullRequest(
        repository_id=repo.id,
        number=1,
        title="PR 1",
        state="open",
        author="alice",
        head_sha="abc",
        base_sha="def",
        head_ref="feat",
        base_ref="main",
        html_url="https://github.com/org/repo/pull/1",
    )
    test_session.add(pr)
    await test_session.flush()

    r1 = Review(
        pull_request_id=pr.id,
        status="completed",
        config={},
        model="fake-llm",
        prompt_versions={},
        cost_usd=2.50,
        trigger_type="manual",
    )
    r2 = Review(
        pull_request_id=pr.id,
        status="completed",
        config={},
        model="fake-llm",
        prompt_versions={},
        cost_usd=3.75,
        trigger_type="manual",
    )
    test_session.add_all([r1, r2])
    await test_session.commit()

    spend = await get_repository_24h_spend(test_session, repo.id)
    assert abs(spend - 6.25) < 1e-5

    allowed, cur_spend, budget = await check_tenant_daily_budget(
        session=test_session,
        repository_id=repo.id,
        repo_full_name="org/repo",
        settings=Settings(tenant_daily_budget_usd=10.00),
    )
    assert allowed
    assert abs(cur_spend - 6.25) < 1e-5
    assert budget == 10.00


@pytest.mark.asyncio
async def test_enforce_tenant_daily_budget_raises_on_exceeded(test_session: AsyncSession) -> None:
    """Verify BudgetExceededError is raised when spend exceeds the daily budget."""
    repo = Repository(owner="bigcorp", name="core", full_name="bigcorp/core", default_branch="main")
    test_session.add(repo)
    await test_session.flush()

    pr = PullRequest(
        repository_id=repo.id,
        number=99,
        title="Heavy PR",
        state="open",
        author="bob",
        head_sha="sha1",
        base_sha="sha2",
        head_ref="patch",
        base_ref="main",
        html_url="https://github.com/bigcorp/core/pull/99",
    )
    test_session.add(pr)
    await test_session.flush()

    r = Review(
        pull_request_id=pr.id,
        status="completed",
        config={},
        model="fake-llm",
        prompt_versions={},
        cost_usd=11.50,  # Exceeds $10 default daily budget
        trigger_type="manual",
    )
    test_session.add(r)
    await test_session.commit()

    with pytest.raises(BudgetExceededError) as exc_info:
        await enforce_tenant_daily_budget(
            session=test_session,
            repository_id=repo.id,
            repo_full_name="bigcorp/core",
            settings=Settings(tenant_daily_budget_usd=10.00),
        )

    assert "Daily cost limit of $10.00 exceeded" in str(exc_info.value)
    assert exc_info.value.current_spend == 11.50
    assert exc_info.value.budget == 10.00


# ── REST API Budget Verification ──


@pytest.mark.asyncio
async def test_trigger_review_api_blocks_on_budget_exceeded(
    test_session: AsyncSession,
    test_settings: Settings,
) -> None:
    """Verify POST /api/reviews/trigger returns 429 when tenant daily budget is breached."""
    # Pre-populate repository with over-budget spend
    repo = Repository(owner="owner", name="repo", full_name="owner/repo", default_branch="main")
    test_session.add(repo)
    await test_session.flush()

    pr = PullRequest(
        repository_id=repo.id,
        number=1,
        title="Existing PR",
        state="open",
        author="carol",
        head_sha="h1",
        base_sha="b1",
        head_ref="feat",
        base_ref="main",
        html_url="https://github.com/owner/repo/pull/1",
    )
    test_session.add(pr)
    await test_session.flush()

    test_session.add(
        Review(
            pull_request_id=pr.id,
            status="completed",
            config={},
            model="fake-llm",
            prompt_versions={},
            cost_usd=15.00,  # Exceeds $10.00 daily budget
            trigger_type="manual",
        )
    )
    await test_session.commit()

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = lambda: test_session
    mock_gh = make_mock_github_client()
    app.dependency_overrides[get_github_client] = lambda: mock_gh

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/reviews/trigger",
            json={"pr_url": "https://github.com/owner/repo/pull/2"},
        )
        assert resp.status_code == 429
        data = resp.json()
        assert "Daily cost limit" in data["detail"]
        assert resp.headers.get("retry-after") == "3600"


@pytest.mark.asyncio
async def test_get_repo_budget_status_api(
    test_session: AsyncSession,
    test_settings: Settings,
) -> None:
    """Verify GET /api/reviews/budget/{owner}/{repo} returns accurate quota info."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = lambda: test_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/reviews/budget/nonexistent/repo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["repository"] == "nonexistent/repo"
        assert data["spend_24h_usd"] == 0.0
        assert data["daily_budget_usd"] == 10.0
        assert data["is_exceeded"] is False
