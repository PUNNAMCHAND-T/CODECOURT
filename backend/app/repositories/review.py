"""Repositories for managing Repository, PullRequest, and Review entities.

Provides typed async database operations using SQLAlchemy 2.0.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.pull_request import PullRequest
from backend.app.models.repository import Repository
from backend.app.models.review import Review


class RepositoryRepository:
    """Data access repository for GitHub repositories."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_full_name(self, full_name: str) -> Repository | None:
        """Find a repository by its full name (e.g. 'octocat/hello-world')."""
        stmt = select(Repository).where(Repository.full_name == full_name.lower())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        owner: str,
        name: str,
        github_id: int | None = None,
        is_private: bool = False,
        default_branch: str = "main",
    ) -> Repository:
        """Get an existing repository or create a new one."""
        full_name = f"{owner.strip().lower()}/{name.strip().lower()}"
        repo = await self.get_by_full_name(full_name)
        if repo is not None:
            if github_id is not None and repo.github_id != github_id:
                repo.github_id = github_id
            return repo

        repo = Repository(
            owner=owner.strip(),
            name=name.strip(),
            full_name=full_name,
            github_id=github_id,
            is_private=is_private,
            default_branch=default_branch,
        )
        self.session.add(repo)
        await self.session.flush()
        return repo


class PullRequestRepository:
    """Data access repository for GitHub pull requests."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_repo_and_number(
        self,
        repository_id: int,
        number: int,
    ) -> PullRequest | None:
        """Find a pull request by repository ID and PR number."""
        stmt = (
            select(PullRequest)
            .where(
                PullRequest.repository_id == repository_id,
                PullRequest.number == number,
            )
            .options(selectinload(PullRequest.repository))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        repository_id: int,
        number: int,
        title: str,
        state: str,
        author: str,
        head_sha: str,
        base_sha: str,
        head_ref: str,
        base_ref: str,
        html_url: str,
        body: str | None = None,
        diff_url: str | None = None,
        changed_files: int = 0,
        additions: int = 0,
        deletions: int = 0,
        github_id: int | None = None,
    ) -> PullRequest:
        """Create a new pull request or update an existing one."""
        pr = await self.get_by_repo_and_number(repository_id, number)
        if pr is None:
            pr = PullRequest(
                repository_id=repository_id,
                number=number,
                github_id=github_id,
                title=title,
                body=body,
                state=state,
                author=author,
                head_sha=head_sha,
                base_sha=base_sha,
                head_ref=head_ref,
                base_ref=base_ref,
                html_url=html_url,
                diff_url=diff_url,
                changed_files=changed_files,
                additions=additions,
                deletions=deletions,
            )
            self.session.add(pr)
        else:
            pr.title = title
            pr.body = body
            pr.state = state
            pr.author = author
            pr.head_sha = head_sha
            pr.base_sha = base_sha
            pr.head_ref = head_ref
            pr.base_ref = base_ref
            pr.html_url = html_url
            pr.diff_url = diff_url
            pr.changed_files = changed_files
            pr.additions = additions
            pr.deletions = deletions
            if github_id is not None:
                pr.github_id = github_id

        await self.session.flush()
        return pr


class ReviewRepository:
    """Data access repository for code reviews."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_review(
        self,
        pull_request_id: int,
        config: dict[str, Any] | None = None,
        model: str = "fake-llm",
        prompt_versions: dict[str, Any] | None = None,
        trigger_type: str = "manual",
        status: str = "queued",
    ) -> Review:
        """Create a new review run record."""
        review = Review(
            pull_request_id=pull_request_id,
            status=status,
            config=config or {},
            model=model,
            prompt_versions=prompt_versions or {},
            trigger_type=trigger_type,
        )
        self.session.add(review)
        await self.session.flush()
        return review

    async def get_by_id(self, review_id: int) -> Review | None:
        """Find a review by ID with pull request and repository loaded."""
        stmt = (
            select(Review)
            .where(Review.id == review_id)
            .options(selectinload(Review.pull_request).selectinload(PullRequest.repository))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_reviews(
        self,
        skip: int = 0,
        limit: int = 50,
        status: str | None = None,
    ) -> list[Review]:
        """List reviews ordered by creation date descending, optionally filtered by status."""
        stmt = select(Review)
        if status is not None:
            stmt = stmt.where(Review.status == status)
        stmt = (
            stmt.order_by(desc(Review.created_at))
            .offset(skip)
            .limit(limit)
            .options(selectinload(Review.pull_request).selectinload(PullRequest.repository))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        review_id: int,
        status: str,
        error_message: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        tokens_total: int | None = None,
        cost_usd: float | None = None,
        latency_ms: int | None = None,
    ) -> Review | None:
        """Update review status, timestamps, and cost metrics."""
        review = await self.get_by_id(review_id)
        if review is None:
            return None

        review.status = status
        if error_message is not None:
            review.error_message = error_message
        if started_at is not None:
            review.started_at = started_at
        if completed_at is not None:
            review.completed_at = completed_at
        if tokens_total is not None:
            review.tokens_total = tokens_total
        if cost_usd is not None:
            review.cost_usd = cost_usd
        if latency_ms is not None:
            review.latency_ms = latency_ms

        await self.session.flush()
        return review
