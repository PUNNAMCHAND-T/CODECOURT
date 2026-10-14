"""Pydantic schemas for GitHub API responses.

Provides validated models for Pull Request metadata and file contents.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PullRequestMetadata(BaseModel):
    """Normalized metadata for a GitHub Pull Request."""

    model_config = ConfigDict(extra="ignore")

    id: int
    number: int
    title: str
    body: str | None = None
    state: str
    owner: str
    repo: str
    head_sha: str
    base_sha: str
    head_ref: str
    base_ref: str
    author: str
    created_at: datetime
    updated_at: datetime | None = None
    html_url: str
    diff_url: str
    changed_files: int = 0
    additions: int = 0
    deletions: int = 0


class RepoFileContent(BaseModel):
    """File content retrieved at a specific Git SHA."""

    model_config = ConfigDict(extra="ignore")

    path: str
    sha: str
    content: str
    size: int


class GitHubReviewComment(BaseModel):
    """Inline review comment attached to specific lines in a GitHub PR review."""

    model_config = ConfigDict(extra="ignore")

    path: str
    body: str
    line: int
    start_line: int | None = None
    side: Literal["RIGHT", "LEFT"] = "RIGHT"


class GitHubReviewPublishPayload(BaseModel):
    """Payload sent to GitHub REST API to create a PR review."""

    model_config = ConfigDict(extra="ignore")

    commit_id: str
    body: str
    event: Literal["COMMENT", "APPROVE", "REQUEST_CHANGES"]
    comments: list[GitHubReviewComment] = Field(default_factory=list)


class GitHubPublishedReview(BaseModel):
    """Outcome of publishing a review to GitHub."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    html_url: str | None = None
    state: str
    comment_count: int
    is_dry_run: bool = False
