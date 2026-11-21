import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GuideFeedback(Base):
    """One anonymous "did this fix it?" vote on a final answer of a guide.

    No user id, no IP, no free text: just which answer was rated and the vote.
    `outcome_key` is the user's answers joined with " > ", which identifies the
    exact final answer (leaf) they reached in that guide's decision tree.
    """

    __tablename__ = "guide_feedback"
    __table_args__ = (Index("ix_guide_feedback_symptom_outcome", "symptom_id", "outcome_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symptom_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("symptom.id", ondelete="CASCADE"), nullable=False
    )
    outcome_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    outcome_kind: Mapped[str] = mapped_column(String(12), nullable=False)  # conclusion | escalate
    helpful: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())