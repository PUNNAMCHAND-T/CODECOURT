"""API routes for human-in-the-loop finding feedback (accept / dismiss)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db_session
from backend.app.repositories.feedback import FeedbackRepository, feedback_to_response
from backend.app.repositories.finding import FindingRepository
from backend.app.repositories.review import ReviewRepository
from backend.app.schemas.feedback import (
    FeedbackCreate,
    FeedbackResponse,
    ReviewFeedbackResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])


@router.post(
    "/api/findings/{finding_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit or update feedback on a finding (accept/dismiss)",
)
async def submit_finding_feedback(
    finding_id: int,
    body: FeedbackCreate,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> FeedbackResponse:
    """Submit developer feedback (accepted / dismissed) on a finding.

    Persists thumbs up/down and optional reasoning. Idempotently updates
    if feedback already exists for this finding.
    """
    finding_repo = FindingRepository(db)
    finding = await finding_repo.get_by_id(finding_id)
    if finding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Finding with id {finding_id} not found.",
        )

    feedback_repo = FeedbackRepository(db)
    fb = await feedback_repo.upsert_feedback(
        finding_id=finding_id,
        action=body.action,
        reason=body.reason,
        user_id=body.user_id,
    )
    return feedback_to_response(fb)


@router.get(
    "/api/findings/{finding_id}/feedback",
    response_model=FeedbackResponse,
    summary="Get feedback for a finding",
)
async def get_finding_feedback(
    finding_id: int,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> FeedbackResponse:
    """Fetch human feedback submitted for a finding."""
    feedback_repo = FeedbackRepository(db)
    fb = await feedback_repo.get_by_finding_id(finding_id)
    if fb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feedback for finding with id {finding_id} not found.",
        )
    return feedback_to_response(fb)


@router.get(
    "/api/reviews/{review_id}/feedback",
    response_model=ReviewFeedbackResponse,
    summary="Get aggregate feedback report for a review",
)
async def get_review_feedback(
    review_id: int,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReviewFeedbackResponse:
    """Fetch summary metrics and feedback items for all findings in a review."""
    review_repo = ReviewRepository(db)
    review = await review_repo.get_by_id(review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review with id {review_id} not found.",
        )

    feedback_repo = FeedbackRepository(db)
    summary = await feedback_repo.get_summary_by_review_id(review_id)
    items = await feedback_repo.list_by_review_id(review_id)
    return ReviewFeedbackResponse(
        review_id=review_id,
        summary=summary,
        items=[feedback_to_response(fb) for fb in items],
    )
