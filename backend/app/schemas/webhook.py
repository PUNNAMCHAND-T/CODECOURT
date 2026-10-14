"""Pydantic schemas for GitHub webhook payloads.

Validates incoming webhook structures from GitHub.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RepositorySummary(BaseModel):
    """Summary of the repository involved in the webhook."""

    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    full_name: str
    owner: dict[str, Any] = Field(default_factory=dict)
    private: bool = False
    html_url: str | None = None


class PullRequestHeadBase(BaseModel):
    """Head or base commit info for a pull request."""

    model_config = ConfigDict(extra="ignore")

    sha: str
    ref: str


class PullRequestSummary(BaseModel):
    """Summary of the pull request payload."""

    model_config = ConfigDict(extra="ignore")

    id: int
    number: int
    title: str
    state: str
    html_url: str
    head: PullRequestHeadBase
    base: PullRequestHeadBase
    draft: bool = False


class PullRequestWebhookPayload(BaseModel):
    """Payload sent by GitHub for pull_request events."""

    model_config = ConfigDict(extra="ignore")

    action: str
    number: int
    pull_request: PullRequestSummary
    repository: RepositorySummary
    sender: dict[str, Any] = Field(default_factory=dict)


class PingWebhookPayload(BaseModel):
    """Payload sent by GitHub for ping events upon webhook registration."""

    model_config = ConfigDict(extra="ignore")

    zen: str | None = None
    hook_id: int | None = None
    hook: dict[str, Any] = Field(default_factory=dict)
    repository: RepositorySummary | None = None
