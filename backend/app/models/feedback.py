"""ORM model for human-in-the-loop Finding Feedback.

Captures developer acceptance or dismissal of code review findings
(thumbs up / thumbs down) with optional rationale for human-in-the-loop tracking.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base

if TYPE_CHECKING:
    from backend.app.models.finding import Finding


class Feedback(Base):
    """Developer feedback on an individual finding."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finding_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Either 'accepted' or 'dismissed'",
    )
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional developer note or reason for dismissal/acceptance",
    )
    user_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="Optional identifier of the responding developer",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    finding: Mapped["Finding"] = relationship(
        "Finding",
        back_populates="feedback",
    )
