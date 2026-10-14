"""Pydantic models for code review trigger and response schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.schemas.finding import FindingResponse


class ReviewTriggerRequest(BaseModel):
    """Payload for manually triggering a code review by PR URL."""

    model_config = ConfigDict(extra="forbid")

    pr_url: str = Field(
        ...,
        description="Full URL to the GitHub pull request, e.g. https://github.com/owner/repo/pull/123",
        examples=["https://github.com/octocat/hello-world/pull/42"],
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Configuration options for reviewer agents and judge",
    )
    model: str = Field(
        default="fake-llm",
        description="LLM model identifier to use for the review",
    )

    @field_validator("config", mode="before")
    @classmethod
    def normalize_config(cls, v: Any) -> dict[str, Any]:
        """Normalize string configs like 'multi_agent_judge' into a dict."""
        if isinstance(v, str):
            return {"system": v}
        if isinstance(v, dict):
            return v
        return {}


class ReviewSummaryCounts(BaseModel):
    """Aggregated finding counts for a review run."""

    model_config = ConfigDict(extra="forbid")

    total: int = 0
    security: int = 0
    performance: int = 0
    maintainability: int = 0
    correctness: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class ReviewResponse(BaseModel):
    """Summary of a code review run."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    pull_request_id: int
    repository: str
    pr_number: int
    pr_title: str
    pr_html_url: str
    head_sha: str
    status: str
    model: str
    config: dict[str, Any]
    prompt_versions: dict[str, Any]
    tokens_total: int
    cost_usd: float
    latency_ms: int | None
    error_message: str | None
    trigger_type: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    finding_counts: ReviewSummaryCounts = Field(default_factory=ReviewSummaryCounts)


class ReviewDetailResponse(ReviewResponse):
    """Detailed review response including all anchored findings, diff, and traces."""

    findings: list[FindingResponse] = Field(default_factory=list)
    diff_text: str | None = Field(
        default=None,
        description="Unified diff text for the pull request",
    )
    traces: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Per-node execution traces",
    )


class ReviewListResponse(BaseModel):
    """Paginated list of code reviews."""

    items: list[ReviewResponse]
    total: int
