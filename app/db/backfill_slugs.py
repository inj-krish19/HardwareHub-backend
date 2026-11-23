"""
Give every guide that has no slug one, derived from its title.

Run with: python -m app.db.backfill_slugs
(python -m app.db.sync_schema also runs this at the end, so you normally only
need that one command.) Safe to repeat: guides that already have a slug are
left alone.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.slugs import slugify, unique_slug
from app.models.rules import Symptom


def taken_slugs(db: Session) -> set[str]:
    return {s for s in db.execute(select(Symptom.slug).where(Symptom.slug.is_not(None))).scalars()}


def assign_missing_slugs(db: Session) -> int:
    """Fill in slug for every guide without one. Returns how many were set."""
    rows = db.execute(
        select(Symptom).where(Symptom.slug.is_(None)).order_by(Symptom.category, Symptom.title, Symptom.id)
    ).scalars().all()
    taken = taken_slugs(db)
    for symptom in rows:
        symptom.slug = unique_slug(slugify(symptom.title), taken)
    db.commit()
    return len(rows)


if __name__ == "__main__":
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        print(f"Assigned slugs to {assign_missing_slugs(session)} guide(s).")