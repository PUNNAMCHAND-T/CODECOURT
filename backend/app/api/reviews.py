"""API routes for triggering and inspecting code reviews."""

import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.core.database import get_db_session
from backend.app.repositories.finding import FindingRepository, finding_to_response
from backend.app.repositories.review import RepositoryRepository, ReviewRepository
from backend.app.schemas.finding import FindingResponse
from backend.app.schemas.review import (
    ReviewDetailResponse,
    ReviewListResponse,
    ReviewResponse,
    ReviewSummaryCounts,
    ReviewTriggerRequest,
)
from backend.app.services.cost_caps import (
    BudgetExceededError,
    get_repository_24h_spend,
)
from backend.app.services.github_client import (
    GitHubAuthenticationError,
    GitHubClient,
    GitHubClientError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubResourceNotFoundError,
)
from backend.app.services.pr_trigger import (
    review_to_detail_response,
    review_to_response,
    trigger_pr_review,
)
from backend.app.services.rate_limiter import RateLimitGuard, trigger_rate_limiter
from backend.app.services.review_runner import execute_review

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


async def get_github_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[GitHubClient]:
    """Dependency that provides an async GitHubClient instance."""
    client = GitHubClient(token=settings.github_token)
    try:
        yield client
    finally:
        await client.close()


@router.post(
    "/trigger",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger code review by PR URL",
    dependencies=[Depends(RateLimitGuard(trigger_rate_limiter))],
)
async def trigger_review(
    body: ReviewTriggerRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    github_client: Annotated[GitHubClient, Depends(get_github_client)],
) -> ReviewResponse:
    """Trigger a review by providing a GitHub pull request URL.

    Fetches PR metadata from GitHub, stores repository and PR records,
    and enqueues a new review for background execution.
    """
    try:
        review = await trigger_pr_review(
            session=db,
            github_client=github_client,
            pr_url=body.pr_url,
            config=body.config,
            model=body.model,
            trigger_type="manual",
        )
        background_tasks.add_task(execute_review, review.id)
        return review_to_response(review)

    except ValueError as exc:
        logger.warning("Invalid trigger request URL: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except GitHubResourceNotFoundError as exc:
        logger.warning("GitHub resource not found for trigger: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"GitHub PR not found: {exc}",
        ) from exc

    except (GitHubAuthenticationError, GitHubPermissionError) as exc:
        logger.error("GitHub auth/permission failure during review trigger: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub authentication error: {exc}",
        ) from exc

    except GitHubRateLimitError as exc:
        logger.warning("GitHub rate limit exceeded during trigger: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="GitHub API rate limit exceeded. Please try again later.",
        ) from exc

    except BudgetExceededError as exc:
        logger.warning("Tenant budget exceeded during trigger: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": "3600"},
        ) from exc

    except GitHubClientError as exc:
        logger.error("GitHub client failure during review trigger: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub API error: {exc}",
        ) from exc


@router.get(
    "/{review_id}",
    response_model=ReviewDetailResponse,
    summary="Get review by ID with findings",
)
async def get_review(
    review_id: int,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReviewDetailResponse:
    """Fetch review details, current status, and all findings by review ID."""
    review_repo = ReviewRepository(db)
    review = await review_repo.get_by_id(review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review with id {review_id} not found.",
        )
    finding_repo = FindingRepository(db)
    findings = await finding_repo.list_by_review_id(review_id)
    traces = review.config.get("traces", []) if isinstance(review.config, dict) else []
    return review_to_detail_response(review, findings, traces=traces)


@router.get(
    "/{review_id}/diff",
    summary="Get unified diff text for a review",
)
async def get_review_diff(
    review_id: int,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    github_client: Annotated[GitHubClient, Depends(get_github_client)],
) -> dict[str, str | None]:
    """Fetch raw unified diff text for the review's pull request."""
    review_repo = ReviewRepository(db)
    review = await review_repo.get_by_id(review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review with id {review_id} not found.",
        )
    pr = review.pull_request
    if not pr or not pr.repository:
        return {"diff_text": None}

    try:
        diff_text = await github_client.get_pull_request_diff(
            owner=pr.repository.owner,
            repo=pr.repository.name,
            pull_number=pr.number,
        )
        return {"diff_text": diff_text}
    except Exception as exc:
        logger.info("Diff fetch skipped for review %d: %s", review_id, exc)
        return {"diff_text": None}


@router.get(
    "/{review_id}/findings",
    response_model=list[FindingResponse],
    summary="Get findings for review",
)
async def get_review_findings(
    review_id: int,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    finding_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[FindingResponse]:
    """Fetch findings for a review, optionally filtered by status (active/merged/dropped)."""
    review_repo = ReviewRepository(db)
    review = await review_repo.get_by_id(review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review with id {review_id} not found.",
        )
    finding_repo = FindingRepository(db)
    findings = await finding_repo.list_by_review_id(review_id, status=finding_status)
    return [finding_to_response(f) for f in findings]


@router.get(
    "",
    response_model=ReviewListResponse,
    summary="List reviews",
)
async def list_reviews(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    review_status: Annotated[str | None, Query(alias="status")] = None,
) -> ReviewListResponse:
    """List recent code reviews with pagination and finding summary counts."""
    review_repo = ReviewRepository(db)
    finding_repo = FindingRepository(db)
    items = await review_repo.list_reviews(skip=skip, limit=limit, status=review_status)

    response_items: list[ReviewResponse] = []
    for r in items:
        counts_dict = await finding_repo.get_summary_counts_by_review_id(r.id)
        counts = ReviewSummaryCounts(**counts_dict)
        response_items.append(review_to_response(r, finding_counts=counts))

    return ReviewListResponse(items=response_items, total=len(response_items))


@router.get(
    "/budget/{owner}/{repo}",
    status_code=status.HTTP_200_OK,
    summary="Get repository daily budget and 24h spend status",
)
async def get_repo_budget_status(
    owner: str,
    repo: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Return 24h spend and daily budget quota for a repository."""
    repo_repo = RepositoryRepository(db)
    full_name = f"{owner.strip().lower()}/{repo.strip().lower()}"
    db_repo = await repo_repo.get_by_full_name(full_name)
    if db_repo is None:
        return {
            "repository": f"{owner}/{repo}",
            "spend_24h_usd": 0.0,
            "daily_budget_usd": settings.tenant_daily_budget_usd,
            "budget_remaining_usd": settings.tenant_daily_budget_usd,
            "is_exceeded": False,
        }
    spend = await get_repository_24h_spend(db, db_repo.id)
    remaining = max(0.0, settings.tenant_daily_budget_usd - spend)
    return {
        "repository": f"{owner}/{repo}",
        "spend_24h_usd": spend,
        "daily_budget_usd": settings.tenant_daily_budget_usd,
        "budget_remaining_usd": remaining,
        "is_exceeded": spend >= settings.tenant_daily_budget_usd,
    }
