"""Write side of the unmatched-query log (see app/models/query_log.py)."""
from __future__ import annotations

import logging

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.query_log import clean_query
from app.models.query_log import UnmatchedQuery

logger = logging.getLogger(__name__)

# Upper limit on distinct messages kept. Once reached, new wordings are not stored
# (known ones still count up), so someone typing random text cannot fill the database.
MAX_DISTINCT_QUERIES = 5000


def log_unmatched(db: Session, raw_query: str) -> bool:
    """Record a message that matched no guide. Returns True if it was stored.

    Never raises: logging must not be able to break the chat. A failure is
    logged on the server and the chat carries on.
    """
    cleaned = clean_query(raw_query)
    if cleaned is None:
        return False
    text, normalized = cleaned
    try:
        known = db.execute(
            select(UnmatchedQuery.id).where(UnmatchedQuery.normalized == normalized)
        ).first()
        if known is None and db.scalar(select(func.count()).select_from(UnmatchedQuery)) >= MAX_DISTINCT_QUERIES:
            return False
        stmt = insert(UnmatchedQuery).values(text=text, normalized=normalized)
        stmt = stmt.on_conflict_do_update(
            index_elements=["normalized"],
            set_={
                "times_seen": UnmatchedQuery.times_seen + 1,
                "last_seen": func.now(),
                # A "fixed" message that fails again means the fix did not work: reopen it.
                "status": case((UnmatchedQuery.status == "fixed", "open"), else_=UnmatchedQuery.status),
            },
        )
        db.execute(stmt)
        db.commit()
        return True
    except SQLAlchemyError:
        db.rollback()
        logger.exception("could not log unmatched query")
        return False