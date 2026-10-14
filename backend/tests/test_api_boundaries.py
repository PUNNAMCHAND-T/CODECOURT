"""API error boundary and finding validation hardening tests.

PROJECT.md §6, §7 & §8: Phase 6 Hardening - T6.4 Coverage and security review.
Verifies finding validator path normalization, diff boundary rejection,
API 404 boundaries, GitHub client authentication error mapping, and logging setup.
"""

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.api.reviews import get_github_client
from backend.app.core.config import Settings, get_settings
from backend.app.core.database import Base, get_db_session
from backend.app.core.logging import setup_logging
from backend.app.main import create_app
from backend.app.schemas.finding import RawAgentFinding
from backend.app.services.diff_parser import parse_unified_diff
from backend.app.services.eval_service import get_benchmark_overview
from backend.app.services.finding_validator import validate_finding
from backend.app.services.github_client import (
    GitHubAuthenticationError,
    GitHubClient,
)


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        app_env="test",
        log_level="warning",
        jwt_secret_key="test-secret-key-for-boundary-tests",
    )


@pytest.fixture
async def test_session() -> Any:
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


# ── 1. Finding Validator Robustness ──


def test_validator_path_normalization_repair() -> None:
    """Verify validator normalizes git prefixes like 'b/app.py' to 'app.py'."""
    raw_diff = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -10,3 +10,4 @@\n"
        " def login():\n"
        "+    SELECT * FROM users\n"
    )
    diff = parse_unified_diff(raw_diff)

    finding = RawAgentFinding(
        category="security",
        severity="high",
        file="b/app.py",  # Git prefixed
        line_start=10,
        line_end=11,
        title="SQL injection",
        explanation="Unsafe query format in login handler",
        evidence="SELECT * FROM users",
        confidence=0.9,
    )

    result = validate_finding(finding, diff)
    assert result.is_valid
    assert result.repaired
    assert result.finding.file == "app.py"


def test_validator_rejects_lines_not_in_diff() -> None:
    """Verify validator rejects findings outside modified line numbers."""
    raw_diff = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -10,3 +10,4 @@\n"
        " def login():\n"
        "+    pass\n"
    )
    diff = parse_unified_diff(raw_diff)

    finding = RawAgentFinding(
        category="security",
        severity="low",
        file="app.py",
        line_start=90,
        line_end=95,
        title="Unmodified line bug",
        explanation="Finding on code line not touched in PR",
        evidence="unused_var = 1",
        confidence=0.8,
    )
    result = validate_finding(finding, diff)
    assert not result.is_valid
    assert "lines_not_in_diff" in (result.drop_reason or "")


# ── 2. API Error Boundaries & Feedback 404s ──


@pytest.mark.asyncio
async def test_feedback_api_404_cases(test_settings: Settings, test_session: AsyncSession) -> None:
    """Verify 404 responses for finding feedback and review feedback when entities absent."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = lambda: test_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # GET feedback for finding with no feedback
        res1 = await client.get("/api/findings/9999/feedback")
        assert res1.status_code == 404

        # GET review feedback for non-existent review
        res2 = await client.get("/api/reviews/9999/feedback")
        assert res2.status_code == 404

        # GET findings for non-existent review
        res3 = await client.get("/api/reviews/9999/findings")
        assert res3.status_code == 404

        # GET diff for non-existent review
        res4 = await client.get("/api/reviews/9999/diff")
        assert res4.status_code == 404


@pytest.mark.asyncio
async def test_trigger_github_auth_error_returns_502(
    test_settings: Settings,
    test_session: AsyncSession,
) -> None:
    """Verify GitHub auth failure during trigger returns HTTP 502 Bad Gateway."""
    mock_gh = GitHubClient(token="invalid_token")

    async def mock_get_pr(*args: Any, **kwargs: Any) -> Any:
        raise GitHubAuthenticationError("Bad credentials")

    mock_gh.get_pull_request = mock_get_pr  # type: ignore[method-assign]

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = lambda: test_session
    app.dependency_overrides[get_github_client] = lambda: mock_gh

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/reviews/trigger", json={"pr_url": "https://github.com/o/r/pull/1"}
        )
        assert res.status_code == 502
        assert "GitHub authentication error" in res.json()["detail"]


# ── 3. Logging & Eval Service Boundaries ──


def test_setup_logging_execution() -> None:
    """Verify setup_logging configures root log level without error."""
    setup_logging("debug")
    setup_logging("info")


def test_eval_service_invalid_split_raises() -> None:
    """Verify get_benchmark_overview raises ValueError on invalid split."""
    with pytest.raises(ValueError) as exc:
        get_benchmark_overview("unknown_split")
    assert "Invalid evaluation split" in str(exc.value)
