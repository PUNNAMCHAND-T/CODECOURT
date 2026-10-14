"""Pydantic schemas for finding feedback (accept / dismiss).

Supports human-in-the-loop tracking, accuracy verification, and rationale.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FeedbackAction = Literal["accepted", "dismissed"]


class FeedbackCreate(BaseModel):
    """Payload for submitting feedback on a finding."""

    model_config = ConfigDict(extra="forbid")

    action: FeedbackAction = Field(
        ...,
        description="User action: 'accepted' (thumbs up / valid finding) or 'dismissed' (thumbs down / false positive)",
    )
    reason: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional developer explanation or reason for dismissal/acceptance",
    )
    user_id: str | None = Field(
        default=None,
        max_length=128,
        description="Optional developer username or identifier",
    )


class FeedbackResponse(BaseModel):
    """API response representing persisted finding feedback."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    finding_id: int
    action: str
    reason: str | None = None
    user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class FeedbackSummary(BaseModel):
    """Summary metrics of human feedback across findings."""

    model_config = ConfigDict(extra="forbid")

    total: int = 0
    accepted: int = 0
    dismissed: int = 0
    acceptance_rate: float = 0.0


class ReviewFeedbackResponse(BaseModel):
    """Review-level aggregate feedback report."""

    model_config = ConfigDict(extra="forbid")

    review_id: int
    summary: FeedbackSummary
    items: list[FeedbackResponse] = Field(default_factory=list)
