"""Repository for persisting, querying, and updating CodeCourt findings.

Provides typed async operations for inserting findings, querying by review,
and aggregating severity/category metrics.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.finding import Finding
from backend.app.schemas.finding import FindingCreate, FindingResponse


def finding_to_response(finding: Finding) -> FindingResponse:
    """Map a Finding ORM instance to a FindingResponse schema."""
    from backend.app.repositories.feedback import feedback_to_response

    fb_response = None
    fb = getattr(finding, "feedback", None)
    if fb is not None:
        fb_response = feedback_to_response(fb)

    return FindingResponse(
        id=finding.id,
        review_id=finding.review_id,
        agent=finding.agent,
        category=finding.category,
        severity=finding.severity,
        file=finding.file,
        line_start=finding.line_start,
        line_end=finding.line_end,
        title=finding.title,
        explanation=finding.explanation,
        evidence=finding.evidence,
        suggested_fix=finding.suggested_fix,
        confidence=finding.confidence,
        status=finding.status,
        merged_from=finding.merged_from,
        decision_reason=finding.decision_reason,
        drop_reason=finding.drop_reason,
        created_at=finding.created_at,
        feedback=fb_response,
    )


class FindingRepository:
    """Data access repository for code review findings."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_finding(self, data: FindingCreate) -> Finding:
        """Insert a single validated finding into the database."""
        finding = Finding(
            review_id=data.review_id,
            agent=data.agent,
            category=data.category,
            severity=data.severity,
            file=data.file,
            line_start=data.line_start,
            line_end=data.line_end,
            title=data.title,
            explanation=data.explanation,
            evidence=data.evidence,
            suggested_fix=data.suggested_fix,
            confidence=data.confidence,
            status=data.status,
            merged_from=data.merged_from,
            decision_reason=data.decision_reason,
            drop_reason=data.drop_reason,
        )
        self.session.add(finding)
        await self.session.flush()
        return finding

    async def create_findings_batch(
        self,
        findings_data: list[FindingCreate],
    ) -> list[Finding]:
        """Insert a batch of findings."""
        if not findings_data:
            return []

        models = [
            Finding(
                review_id=f.review_id,
                agent=f.agent,
                category=f.category,
                severity=f.severity,
                file=f.file,
                line_start=f.line_start,
                line_end=f.line_end,
                title=f.title,
                explanation=f.explanation,
                evidence=f.evidence,
                suggested_fix=f.suggested_fix,
                confidence=f.confidence,
                status=f.status,
                merged_from=f.merged_from,
                decision_reason=f.decision_reason,
                drop_reason=f.drop_reason,
            )
            for f in findings_data
        ]
        self.session.add_all(models)
        await self.session.flush()
        return models

    async def get_by_id(self, finding_id: int) -> Finding | None:
        """Find a finding by its ID."""
        stmt = (
            select(Finding).where(Finding.id == finding_id).options(selectinload(Finding.feedback))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_review_id(
        self,
        review_id: int,
        status: str | None = None,
    ) -> list[Finding]:
        """List findings belonging to a specific review, optionally filtered by status."""
        stmt = (
            select(Finding)
            .where(Finding.review_id == review_id)
            .options(selectinload(Finding.feedback))
        )
        if status is not None:
            stmt = stmt.where(Finding.status == status)
        stmt = stmt.order_by(Finding.file, Finding.line_start)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_summary_counts_by_review_id(
        self,
        review_id: int,
    ) -> dict[str, int]:
        """Aggregate counts by category and severity for active findings."""
        findings = await self.list_by_review_id(review_id, status="active")
        counts: dict[str, int] = {
            "total": len(findings),
            "security": 0,
            "performance": 0,
            "maintainability": 0,
            "correctness": 0,
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        }
        for f in findings:
            if f.category in counts:
                counts[f.category] += 1
            if f.severity in counts:
                counts[f.severity] += 1
        return counts

    async def update_status(
        self,
        finding_id: int,
        status: str,
        decision_reason: str | None = None,
        drop_reason: str | None = None,
    ) -> Finding | None:
        """Update finding status and explanation reasons."""
        finding = await self.get_by_id(finding_id)
        if finding is None:
            return None
        finding.status = status
        if decision_reason is not None:
            finding.decision_reason = decision_reason
        if drop_reason is not None:
            finding.drop_reason = drop_reason
        await self.session.flush()
        return finding
