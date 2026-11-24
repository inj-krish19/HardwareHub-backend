import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy import text as sql_text  # the column below is also called "text"
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UnmatchedQuery(Base):
    """A chat message that matched no guide, kept once per distinct wording.

    Only the text is stored: no user id, no IP, no timestamp per message. Repeats
    of the same wording add 1 to `times_seen` instead of adding a row, so the table
    only grows with distinct messages. See app/core/query_log.py for what is
    refused (emails, phone numbers) and app/db/query_log.py for the size cap.
    """

    __tablename__ = "unmatched_query"
    __table_args__ = (Index("uq_unmatched_query_normalized", "normalized", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # First wording seen, as typed (tidied), and the lower-case words used to group repeats.
    text: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized: Mapped[str] = mapped_column(String(200), nullable=False)
    times_seen: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql_text("1"))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # open = needs a decision, fixed = a keyword was added, dismissed = junk or off-topic
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default=sql_text("'open'"))
    # The guide the admin attached this wording to (labels the evaluation set).
    resolved_symptom_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("symptom.id", ondelete="SET NULL"), nullable=True
    )