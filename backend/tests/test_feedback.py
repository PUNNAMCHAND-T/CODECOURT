"""Tests for finding feedback endpoints, persistence, and summary metrics."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.core.config import Settings, get_settings
from backend.app.core.database import Base, get_db_session
from backend.app.main import create_app
from backend.app.repositories.finding import FindingRepository
from backend.app.repositories.review import (
    PullRequestRepository,
    RepositoryRepository,
    ReviewRepository,
)
from backend.app.schemas.finding import FindingCreate


@pytest.fixture
def test_settings() -> Settings:
    return Settings(app_env="test", log_level="warning")


@pytest.fixture
async def test_session() -> AsyncIterator[AsyncSession]:
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
async def seeded_data(test_session: AsyncSession) -> tuple[int, int, int]:
    """Seed repository, PR, review, and two findings. Returns (review_id, finding_1_id, finding_2_id)."""
    repo_repo = RepositoryRepository(test_session)
    repo = await repo_repo.get_or_create(owner="octocat", name="codecourt-test")

    pr_repo = PullRequestRepository(test_session)
    pr = await pr_repo.upsert(
        repository_id=repo.id,
        number=42,
        title="Test PR",
        state="open",
        author="alice",
        head_sha="abcdef123456",
        base_sha="123456abcdef",
        head_ref="feature",
        base_ref="main",
        html_url="https://github.com/octocat/codecourt-test/pull/42",
    )

    review_repo = ReviewRepository(test_session)
    review = await review_repo.create_review(pull_request_id=pr.id)

    finding_repo = FindingRepository(test_session)
    f1 = await finding_repo.create_finding(
        FindingCreate(
            review_id=review.id,
            agent="security",
            category="security",
            severity="high",
            file="app/auth.py",
            line_start=10,
            line_end=15,
            title="SQL Injection vulnerability",
            explanation="Unsanitized user parameter passed directly to raw query format.",
            evidence="cursor.execute(f'SELECT * FROM users WHERE id = {user_id}')",
            suggested_fix="cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))",
            confidence=0.95,
        )
    )
    f2 = await finding_repo.create_finding(
        FindingCreate(
            review_id=review.id,
            agent="performance",
            category="performance",
            severity="medium",
            file="app/db.py",
            line_start=50,
            line_end=55,
            title="N+1 Query loop",
            explanation="Multiple synchronous queries executed within iteration loop.",
            evidence="for item in items: db.query()",
            confidence=0.88,
        )
    )
    return review.id, f1.id, f2.id


@pytest.mark.asyncio
async def test_submit_feedback_accepted(
    test_settings: Settings,
    test_session: AsyncSession,
    seeded_data: tuple[int, int, int],
) -> None:
    _, f1_id, _ = seeded_data
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = lambda: test_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        res = await client.post(
            f"/api/findings/{f1_id}/feedback",
            json={"action": "accepted", "reason": "Accurate finding, patching immediately."},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["finding_id"] == f1_id
        assert data["action"] == "accepted"
        assert "Accurate finding" in data["reason"]


@pytest.mark.asyncio
async def test_submit_feedback_dismissed_and_update(
    test_settings: Settings,
    test_session: AsyncSession,
    seeded_data: tuple[int, int, int],
) -> None:
    _, f1_id, _ = seeded_data
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = lambda: test_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # Initial dismiss
        res1 = await client.post(
            f"/api/findings/{f1_id}/feedback",
            json={"action": "dismissed", "reason": "False alarm in test environment"},
        )
        assert res1.status_code == 200
        assert res1.json()["action"] == "dismissed"

        # Update action to accepted (idempotent upsert)
        res2 = await client.post(
            f"/api/findings/{f1_id}/feedback",
            json={"action": "accepted", "reason": "Re-evaluated and confirmed bug"},
        )
        assert res2.status_code == 200
        assert res2.json()["action"] == "accepted"
        assert res2.json()["id"] == res1.json()["id"]


@pytest.mark.asyncio
async def test_submit_feedback_nonexistent_finding(
    test_settings: Settings,
    test_session: AsyncSession,
) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = lambda: test_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        res = await client.post(
            "/api/findings/99999/feedback",
            json={"action": "accepted"},
        )
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_get_finding_feedback_and_review_summary(
    test_settings: Settings,
    test_session: AsyncSession,
    seeded_data: tuple[int, int, int],
) -> None:
    review_id, f1_id, f2_id = seeded_data
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = lambda: test_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # Submit feedback for f1 (accepted) and f2 (dismissed)
        await client.post(f"/api/findings/{f1_id}/feedback", json={"action": "accepted"})
        await client.post(
            f"/api/findings/{f2_id}/feedback",
            json={"action": "dismissed", "reason": "Already handled by caching layer"},
        )

        # GET single finding feedback
        get_fb = await client.get(f"/api/findings/{f1_id}/feedback")
        assert get_fb.status_code == 200
        assert get_fb.json()["action"] == "accepted"

        # GET review aggregate feedback
        rev_fb = await client.get(f"/api/reviews/{review_id}/feedback")
        assert rev_fb.status_code == 200
        summary = rev_fb.json()["summary"]
        assert summary["total"] == 2
        assert summary["accepted"] == 1
        assert summary["dismissed"] == 1
        assert summary["acceptance_rate"] == 50.0

        # Verify GET /api/reviews/{id} eagerly includes feedback on each finding
        rev_detail = await client.get(f"/api/reviews/{review_id}")
        assert rev_detail.status_code == 200
        findings = rev_detail.json()["findings"]
        f1_data = next(f for f in findings if f["id"] == f1_id)
        assert f1_data["feedback"] is not None
        assert f1_data["feedback"]["action"] == "accepted"
