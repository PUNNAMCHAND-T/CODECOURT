"""Tests for finding schemas, ORM persistence, and review detail endpoints."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
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
from backend.app.schemas.finding import (
    AgentReviewOutput,
    FindingCreate,
    RawAgentFinding,
)


@pytest.fixture
def test_settings() -> Settings:
    """Settings instance for findings tests."""
    return Settings(
        app_env="test",
        log_level="warning",
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
async def seeded_review(test_session: AsyncSession) -> int:
    """Seed a test repository, PR, and review record."""
    repo_repo = RepositoryRepository(test_session)
    repo = await repo_repo.get_or_create(owner="octocat", name="codecourt-test")

    pr_repo = PullRequestRepository(test_session)
    pr = await pr_repo.upsert(
        repository_id=repo.id,
        number=42,
        title="Test Pull Request",
        state="open",
        author="octocat",
        head_sha="head123456",
        base_sha="base123456",
        head_ref="feature",
        base_ref="main",
        html_url="https://github.com/octocat/codecourt-test/pull/42",
    )

    review_repo = ReviewRepository(test_session)
    review = await review_repo.create_review(
        pull_request_id=pr.id,
        model="fake-llm",
        status="completed",
    )
    await test_session.commit()
    return review.id


@pytest.fixture
async def client(
    test_settings: Settings,
    test_session: AsyncSession,
) -> AsyncIterator[AsyncClient]:
    """Async test client with dependency overrides."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = lambda: test_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


# -----------------------------------------------------------------------------
# Unit Tests: Schema Validation
# -----------------------------------------------------------------------------


def test_raw_agent_finding_valid() -> None:
    """Verify valid finding passes validation."""
    finding = RawAgentFinding(
        category="security",
        severity="critical",
        file="auth/jwt.py",
        line_start=15,
        line_end=20,
        title="Hardcoded JWT Secret Key",
        explanation="The JWT secret key is hardcoded directly in the source file.",
        evidence="SECRET_KEY = 'insecure_default_secret'",
        suggested_fix="SECRET_KEY = os.environ['JWT_SECRET_KEY']",
        confidence=0.95,
    )
    assert finding.category == "security"
    assert finding.severity == "critical"
    assert finding.line_start == 15
    assert finding.line_end == 20
    assert finding.confidence == 0.95


def test_raw_agent_finding_invalid_category() -> None:
    """Verify invalid category is rejected."""
    with pytest.raises(ValidationError):
        RawAgentFinding(
            category="cosmetic",  # type: ignore[arg-type]
            severity="low",
            file="app.py",
            line_start=1,
            line_end=1,
            title="Formatting issue",
            explanation="Unnecessary whitespace",
            evidence="  ",
            confidence=0.5,
        )


def test_raw_agent_finding_invalid_severity() -> None:
    """Verify invalid severity is rejected."""
    with pytest.raises(ValidationError):
        RawAgentFinding(
            category="performance",
            severity="urgent",  # type: ignore[arg-type]
            file="db.py",
            line_start=1,
            line_end=1,
            title="Slow query",
            explanation="N+1 query problem",
            evidence="query",
            confidence=0.8,
        )


def test_raw_agent_finding_inverted_lines() -> None:
    """Verify line_end < line_start is rejected."""
    with pytest.raises(ValidationError, match="cannot be less than line_start"):
        RawAgentFinding(
            category="maintainability",
            severity="medium",
            file="utils.py",
            line_start=50,
            line_end=40,  # Inverted range
            title="Complex function",
            explanation="Cyclomatic complexity is too high",
            evidence="def func():",
            confidence=0.7,
        )


def test_raw_agent_finding_confidence_out_of_bounds() -> None:
    """Verify confidence must be between 0.0 and 1.0."""
    with pytest.raises(ValidationError):
        RawAgentFinding(
            category="correctness",
            severity="high",
            file="calc.py",
            line_start=1,
            line_end=2,
            title="Division by zero",
            explanation="Zero divisor check missing",
            evidence="a / b",
            confidence=1.5,  # Out of bounds
        )


def test_agent_review_output_parsing() -> None:
    """Verify LLM output schema parses summary and findings list."""
    raw_json = """
    {
        "summary": "Found 1 security vulnerability and 1 performance bottleneck.",
        "findings": [
            {
                "category": "security",
                "severity": "critical",
                "file": "auth.py",
                "line_start": 10,
                "line_end": 12,
                "title": "SQL Injection",
                "explanation": "Unsanitized user input formatted into SQL query string.",
                "evidence": "f'SELECT * FROM users WHERE id = {user_id}'",
                "suggested_fix": "Use parameterized queries.",
                "confidence": 0.98,
                "extra_agent_field": "ignored"
            }
        ]
    }
    """
    output = AgentReviewOutput.model_validate_json(raw_json)
    assert "1 security vulnerability" in output.summary
    assert len(output.findings) == 1
    assert output.findings[0].category == "security"
    assert output.findings[0].severity == "critical"


# -----------------------------------------------------------------------------
# Unit Tests: FindingRepository
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finding_repository_crud(
    test_session: AsyncSession,
    seeded_review: int,
) -> None:
    """Verify creation, batch insertion, querying, and status updating in FindingRepository."""
    repo = FindingRepository(test_session)

    # 1. Single creation
    finding1 = await repo.create_finding(
        FindingCreate(
            review_id=seeded_review,
            agent="security_reviewer",
            category="security",
            severity="high",
            file="auth/jwt.py",
            line_start=20,
            line_end=25,
            title="Weak hashing algorithm",
            explanation="MD5 should not be used for cryptographic hashes.",
            evidence="hashlib.md5()",
            confidence=0.9,
        )
    )
    await test_session.commit()
    assert finding1.id is not None
    assert finding1.status == "active"

    # 2. Batch creation
    batch_items = [
        FindingCreate(
            review_id=seeded_review,
            agent="performance_reviewer",
            category="performance",
            severity="medium",
            file="services/fetch.py",
            line_start=10,
            line_end=15,
            title="Missing connection pool",
            explanation="Creating a new client on each request causes overhead.",
            evidence="httpx.Client()",
            confidence=0.85,
        ),
        FindingCreate(
            review_id=seeded_review,
            agent="maintainability_reviewer",
            category="maintainability",
            severity="low",
            file="services/fetch.py",
            line_start=30,
            line_end=35,
            title="Magic numbers in timeout",
            explanation="Replace literal 45 with named constant.",
            evidence="timeout=45",
            confidence=0.8,
        ),
    ]
    created_batch = await repo.create_findings_batch(batch_items)
    await test_session.commit()
    assert len(created_batch) == 2

    # 3. List by review ID
    all_findings = await repo.list_by_review_id(seeded_review)
    assert len(all_findings) == 3

    # 4. Summary counts
    counts = await repo.get_summary_counts_by_review_id(seeded_review)
    assert counts["total"] == 3
    assert counts["security"] == 1
    assert counts["performance"] == 1
    assert counts["maintainability"] == 1
    assert counts["high"] == 1
    assert counts["medium"] == 1
    assert counts["low"] == 1

    # 5. Status update (e.g. dropped by judge)
    updated = await repo.update_status(
        finding_id=finding1.id,
        status="dropped",
        drop_reason="False positive: test mock only",
    )
    await test_session.commit()
    assert updated is not None
    assert updated.status == "dropped"
    assert updated.drop_reason == "False positive: test mock only"

    # Verify active filter
    active_findings = await repo.list_by_review_id(seeded_review, status="active")
    assert len(active_findings) == 2


# -----------------------------------------------------------------------------
# API Route Tests: Review detail with findings
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_review_detail_with_findings(
    client: AsyncClient,
    test_session: AsyncSession,
    seeded_review: int,
) -> None:
    """Verify GET /api/reviews/{id} returns findings and populated finding_counts."""
    # Seed findings
    repo = FindingRepository(test_session)
    await repo.create_finding(
        FindingCreate(
            review_id=seeded_review,
            agent="security_reviewer",
            category="security",
            severity="critical",
            file="auth.py",
            line_start=1,
            line_end=5,
            title="SQL Injection",
            explanation="Unsanitized parameters in query.",
            evidence="f'SELECT {user}'",
            confidence=0.99,
        )
    )
    await test_session.commit()

    response = await client.get(f"/api/reviews/{seeded_review}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == seeded_review
    assert len(data["findings"]) == 1
    assert data["findings"][0]["category"] == "security"
    assert data["findings"][0]["severity"] == "critical"
    assert data["finding_counts"]["total"] == 1
    assert data["finding_counts"]["critical"] == 1

    # Test GET /api/reviews/{id}/findings
    findings_response = await client.get(f"/api/reviews/{seeded_review}/findings")
    assert findings_response.status_code == 200
    findings_list = findings_response.json()
    assert len(findings_list) == 1
    assert findings_list[0]["title"] == "SQL Injection"

    # Test GET /api/reviews includes finding_counts
    list_response = await client.get("/api/reviews")
    assert list_response.status_code == 200
    list_data = list_response.json()
    assert len(list_data["items"]) >= 1
    assert list_data["items"][0]["finding_counts"]["total"] == 1
