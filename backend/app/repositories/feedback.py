"""Repository for persisting and querying human feedback on findings."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.feedback import Feedback
from backend.app.models.finding import Finding
from backend.app.schemas.feedback import FeedbackResponse, FeedbackSummary


def feedback_to_response(fb: Feedback) -> FeedbackResponse:
    """Map a Feedback ORM instance to a FeedbackResponse Pydantic model."""
    return FeedbackResponse(
        id=fb.id,
        finding_id=fb.finding_id,
        action=fb.action,
        reason=fb.reason,
        user_id=fb.user_id,
        created_at=fb.created_at,
        updated_at=fb.updated_at,
    )


class FeedbackRepository:
    """Data access repository for finding feedback."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_finding_id(self, finding_id: int) -> Feedback | None:
        """Fetch feedback for a finding by finding ID."""
        stmt = select(Feedback).where(Feedback.finding_id == finding_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_feedback(
        self,
        finding_id: int,
        action: str,
        reason: str | None = None,
        user_id: str | None = None,
    ) -> Feedback:
        """Create or update feedback on a finding."""
        existing = await self.get_by_finding_id(finding_id)
        if existing is not None:
            existing.action = action
            existing.reason = reason
            if user_id is not None:
                existing.user_id = user_id
            await self.session.flush()
            await self.session.refresh(existing)
            return existing

        fb = Feedback(
            finding_id=finding_id,
            action=action,
            reason=reason,
            user_id=user_id,
        )
        self.session.add(fb)
        await self.session.flush()
        await self.session.refresh(fb)
        return fb

    async def list_by_review_id(self, review_id: int) -> list[Feedback]:
        """Fetch all feedback records for findings within a given review."""
        stmt = (
            select(Feedback)
            .join(Finding, Finding.id == Feedback.finding_id)
            .where(Finding.review_id == review_id)
            .order_by(Feedback.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_summary_by_review_id(self, review_id: int) -> FeedbackSummary:
        """Calculate human feedback counts and acceptance rate for a review."""
        items = await self.list_by_review_id(review_id)
        accepted = sum(1 for fb in items if fb.action == "accepted")
        dismissed = sum(1 for fb in items if fb.action == "dismissed")
        total = len(items)
        rate = (accepted / total * 100.0) if total > 0 else 0.0

        return FeedbackSummary(
            total=total,
            accepted=accepted,
            dismissed=dismissed,
            acceptance_rate=round(rate, 1),
        )
