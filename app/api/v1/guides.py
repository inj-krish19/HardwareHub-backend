"""Public, read-only guide pages: list every guide, and fetch one with its
whole decision tree. These feed the crawlable /guides/<slug> pages on the site."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.rules import DiagnosisRule, Symptom

router = APIRouter(prefix="/guides", tags=["guides"])

RELATED_LIMIT = 4


def _summary(s: Symptom) -> dict:
    return {"slug": s.slug, "title": s.title, "category": s.category, "bot_type": s.bot_type}


@router.get("")
def list_guides(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Symptom)
        .where(Symptom.slug.is_not(None))
        .order_by(Symptom.bot_type, Symptom.category, Symptom.title)
    ).scalars().all()
    return [_summary(s) for s in rows]


@router.get("/{slug}")
def get_guide(slug: str, db: Session = Depends(get_db)) -> dict:
    symptom = db.execute(select(Symptom).where(Symptom.slug == slug)).scalars().first()
    if symptom is None:
        raise HTTPException(status_code=404, detail="Guide not found.")
    rule = db.execute(
        select(DiagnosisRule).where(DiagnosisRule.symptom_id == symptom.id)
    ).scalars().first()
    if rule is None:
        raise HTTPException(status_code=404, detail="Guide not found.")

    related = db.execute(
        select(Symptom)
        .where(Symptom.category == symptom.category, Symptom.id != symptom.id, Symptom.slug.is_not(None))
        .order_by(Symptom.title)
        .limit(RELATED_LIMIT)
    ).scalars().all()

    return {
        **_summary(symptom),
        "keywords": [k.strip() for k in (symptom.keywords or "").split(",") if k.strip()],
        "question_tree": rule.question_tree,
        "related": [{"slug": r.slug, "title": r.title} for r in related],
    }