"""Service for parsing PR URLs and triggering PR review workflows.

Handles URL validation, fetching GitHub pull request metadata,
persisting the repository and pull request, and queueing a new review record.
"""

import logging
import re
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.review import Review
from backend.app.repositories.review import (
    PullRequestRepository,
    RepositoryRepository,
    ReviewRepository,
)
from backend.app.schemas.review import (
    ReviewDetailResponse,
    ReviewResponse,
    ReviewSummaryCounts,
)
from backend.app.services.github_client import GitHubClient

logger = logging.getLogger(__name__)

# Matches GitHub PR path: /{owner}/{repo}/pull/{number} (with optional trailing subpath)
GITHUB_PR_PATH_REGEX = re.compile(
    r"^/([a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+)/pull/(\d+)(?:/.*)?$",
    re.IGNORECASE,
)


def parse_github_pr_url(url: str) -> tuple[str, str, int]:
    """Parse a GitHub pull request URL into owner, repository, and PR number.

    Args:
        url: Full GitHub pull request URL string.

    Returns:
        Tuple of (owner, repo_name, pr_number).

    Raises:
        ValueError: If the URL is not a valid GitHub PR URL.
    """
    clean_url = url.strip()
    if not clean_url:
        raise ValueError("Pull request URL cannot be empty.")

    parsed = urlparse(clean_url if "://" in clean_url else f"https://{clean_url}")
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        raise ValueError(f"Invalid GitHub host '{parsed.netloc}'. Must be github.com.")

    match = GITHUB_PR_PATH_REGEX.match(parsed.path)
    if not match:
        raise ValueError(
            f"Invalid GitHub PR URL '{url}'. "
            "Expected format: https://github.com/owner/repo/pull/123"
        )

    owner, repo, pr_number_str = match.groups()
    try:
        pr_number = int(pr_number_str)
        if pr_number <= 0:
            raise ValueError()
    except ValueError:
        raise ValueError(f"PR number must be a positive integer, got '{pr_number_str}'.") from None

    # Strip .git suffix if present in repo name
    if repo.endswith(".git"):
        repo = repo[:-4]

    return owner, repo, pr_number


def review_to_response(
    review: Review,
    finding_counts: ReviewSummaryCounts | None = None,
) -> ReviewResponse:
    """Map a Review ORM instance to a ReviewResponse Pydantic model."""
    pr = review.pull_request
    repo = pr.repository

    return ReviewResponse(
        id=review.id,
        pull_request_id=review.pull_request_id,
        repository=repo.full_name,
        pr_number=pr.number,
        pr_title=pr.title,
        pr_html_url=pr.html_url,
        head_sha=pr.head_sha,
        status=review.status,
        model=review.model,
        config=review.config,
        prompt_versions=review.prompt_versions,
        tokens_total=review.tokens_total,
        cost_usd=review.cost_usd,
        latency_ms=review.latency_ms,
        error_message=review.error_message,
        trigger_type=review.trigger_type,
        created_at=review.created_at,
        started_at=review.started_at,
        completed_at=review.completed_at,
        finding_counts=finding_counts or ReviewSummaryCounts(),
    )


def review_to_detail_response(
    review: Review,
    findings: list[Any] | None = None,
    diff_text: str | None = None,
    traces: list[dict[str, Any]] | None = None,
) -> ReviewDetailResponse:
    """Map a Review and its Finding models to a ReviewDetailResponse."""
    from backend.app.repositories.finding import finding_to_response

    finding_items = [finding_to_response(f) for f in (findings or [])]
    active_findings = [f for f in finding_items if f.status == "active"]

    counts = ReviewSummaryCounts(
        total=len(active_findings),
        security=sum(1 for f in active_findings if f.category == "security"),
        performance=sum(1 for f in active_findings if f.category == "performance"),
        maintainability=sum(1 for f in active_findings if f.category == "maintainability"),
        correctness=sum(1 for f in active_findings if f.category == "correctness"),
        critical=sum(1 for f in active_findings if f.severity == "critical"),
        high=sum(1 for f in active_findings if f.severity == "high"),
        medium=sum(1 for f in active_findings if f.severity == "medium"),
        low=sum(1 for f in active_findings if f.severity == "low"),
    )

    base = review_to_response(review, finding_counts=counts)
    dumped = base.model_dump(exclude={"findings", "finding_counts", "diff_text", "traces"})
    return ReviewDetailResponse(
        **dumped,
        findings=finding_items,
        finding_counts=counts,
        diff_text=diff_text,
        traces=traces or [],
    )


async def trigger_pr_review(
    session: AsyncSession,
    github_client: GitHubClient,
    pr_url: str,
    config: dict[str, Any] | None = None,
    model: str = "fake-llm",
    trigger_type: str = "manual",
) -> Review:
    """Fetch GitHub PR metadata, persist records, and queue a new code review.

    Args:
        session: Active async SQLAlchemy database session.
        github_client: Configured GitHub API client.
        pr_url: GitHub PR URL string.
        config: Agent configuration options.
        model: LLM identifier to use.
        trigger_type: Source of trigger ('manual' or 'webhook').

    Returns:
        Created Review ORM model in 'queued' status.
    """
    owner, repo, pr_number = parse_github_pr_url(pr_url)
    logger.info("Triggering review for %s/%s PR #%d (model=%s)", owner, repo, pr_number, model)

    # 1. Fetch metadata from GitHub
    pr_meta = await github_client.get_pull_request(owner, repo, pr_number)

    # 2. Persist repository
    repo_repo = RepositoryRepository(session)
    db_repo = await repo_repo.get_or_create(
        owner=owner,
        name=repo,
        default_branch="main",
    )

    # 2b. Enforce tenant daily budget ceiling (T6.2)
    from backend.app.services.cost_caps import enforce_tenant_daily_budget

    await enforce_tenant_daily_budget(
        session=session,
        repository_id=db_repo.id,
        repo_full_name=f"{owner}/{repo}",
    )

    # 3. Persist pull request
    pr_repo = PullRequestRepository(session)
    db_pr = await pr_repo.upsert(
        repository_id=db_repo.id,
        number=pr_number,
        title=pr_meta.title,
        state=pr_meta.state,
        author=pr_meta.author,
        head_sha=pr_meta.head_sha,
        base_sha=pr_meta.base_sha,
        head_ref=pr_meta.head_ref,
        base_ref=pr_meta.base_ref,
        html_url=pr_meta.html_url,
        body=pr_meta.body,
        diff_url=pr_meta.diff_url,
        changed_files=pr_meta.changed_files,
        additions=pr_meta.additions,
        deletions=pr_meta.deletions,
        github_id=pr_meta.id,
    )

    # 4. Create review in queued status
    review_repo = ReviewRepository(session)
    review = await review_repo.create_review(
        pull_request_id=db_pr.id,
        config=config or {},
        model=model,
        prompt_versions={"reviewer": "v1"},
        trigger_type=trigger_type,
        status="queued",
    )

    await session.commit()
    # Refresh to ensure relationships are accessible
    fresh_review = await review_repo.get_by_id(review.id)
    if fresh_review is None:
        raise RuntimeError("Failed to retrieve newly created review")

    return fresh_review
