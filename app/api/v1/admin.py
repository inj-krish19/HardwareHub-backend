from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

import uuid

from app.core.admin_auth import require_admin
from app.core.slugs import slugify, unique_slug
from app.db.backfill_slugs import taken_slugs
from app.db.session import get_db
from app.core.links import normalize_links
from app.models.feedback import GuideFeedback
from app.models.catalog import BlogPost, Category, Product, ProductLink
from app.models.rules import DiagnosisRule, Symptom
from app.schemas.admin import (
    BlogPostCreate,
    CategoryCreate,
    MediaSeedEntry,
    ProductCreate,
    ProductSeedEntry,
    SymptomKeywordsUpdate,
    SymptomSeedEntry,
)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/ping")
def ping() -> dict:
    """Credential check only — used by the admin login form to verify before
    storing the session, no side effects."""
    return {"ok": True}



@router.post("/seed/symptoms", status_code=201)
def bulk_upload_symptoms(entries: list[SymptomSeedEntry], db: Session = Depends(get_db)) -> dict:
    """Same shape as the seed generation prompt output — paste the generated
    JSON array straight into this endpoint's request body.

    Guide titles must be unique (ignoring case and surrounding spaces), because
    the chat looks a guide up by the title the person tapped. An entry whose
    title already exists in the database, or appears earlier in the same paste,
    is skipped and listed in `skipped`, so re-pasting a file is safe."""
    taken = {t.strip().lower() for t in db.execute(select(Symptom.title)).scalars()}
    slugs = taken_slugs(db)
    created = 0
    skipped: list[str] = []
    for entry in entries:
        key = entry.title.strip().lower()
        if key in taken:
            skipped.append(entry.title)
            continue
        taken.add(key)
        symptom = Symptom(
            title=entry.title.strip(),
            slug=unique_slug(slugify(entry.title), slugs),
            category=entry.category,
            keywords=", ".join(entry.keywords) if entry.keywords else None,
            bot_type=entry.bot_type,
        )
        db.add(symptom)
        db.flush()
        db.add(DiagnosisRule(symptom_id=symptom.id, question_tree=entry.question_tree))
        created += 1
    db.commit()
    return {"created": created, "skipped": skipped}


def _set_links(db: Session, product_id: uuid.UUID, links: list[dict[str, str]]) -> None:
    """Replace a product's links. Deleting first (and flushing) keeps the
    unique (product_id, position) constraint happy when re-inserting."""
    db.execute(delete(ProductLink).where(ProductLink.product_id == product_id))
    db.flush()
    for position, link in enumerate(links):
        db.add(ProductLink(product_id=product_id, position=position, store=link["store"], url=link["url"]))


@router.post("/seed/products", status_code=201)
def bulk_upload_products(entries: list[ProductSeedEntry], db: Session = Depends(get_db)) -> dict:
    """Products + optional blog post + 1-3 store links in one paste. Categories
    are found by name (created if missing). A product with the same name and
    model number is skipped, so re-pasting the same file is safe. An entry with
    invalid links is skipped and reported in `invalid`."""
    created, skipped = 0, 0
    invalid: list[dict] = []
    categories: dict[str, Category] = {c.name.lower(): c for c in db.execute(select(Category)).scalars()}
    for entry in entries:
        try:
            links = normalize_links(entry.buy_links)
            if not links and entry.blog and entry.blog.buy_links:
                links = normalize_links(entry.blog.buy_links)  # old location, still accepted
        except ValueError as exc:
            invalid.append({"name": entry.name, "reason": str(exc)})
            continue

        key = entry.category.strip().lower()
        category = categories.get(key)
        if category is None:
            category = Category(name=entry.category.strip())
            db.add(category)
            db.flush()
            categories[key] = category

        exists = db.execute(
            select(Product).where(
                Product.name == entry.name, Product.model_number == entry.model_number
            )
        ).scalars().first()
        if exists:
            skipped += 1
            continue

        product = Product(
            category_id=category.id,
            name=entry.name,
            model_number=entry.model_number,
            specs=entry.specs,
            use_case_tags=entry.use_case_tags,
            image_url=entry.image_url or None,
            video_url=entry.video_url or None,
        )
        db.add(product)
        db.flush()
        _set_links(db, product.id, links)
        if entry.blog:
            db.add(
                BlogPost(
                    product_id=product.id,
                    content=entry.blog.content,
                    do_you_know=entry.blog.do_you_know,
                )
            )
        created += 1
    db.commit()
    return {"created": created, "skipped": skipped, "invalid": invalid}


@router.post("/seed/media")
def bulk_update_media(entries: list[MediaSeedEntry], db: Session = Depends(get_db)) -> dict:
    """Attach image / video / store links to products already in the catalog,
    matched by model number. Empty fields leave the current value untouched.
    If buy_links is given it REPLACES the product's links (1 to 3 allowed)."""
    updated: list[str] = []
    not_found: list[str] = []
    invalid: list[dict] = []
    for entry in entries:
        product = db.execute(
            select(Product).where(Product.model_number == entry.model_number)
        ).scalars().first()
        if product is None:
            not_found.append(entry.model_number)
            continue
        try:
            links = normalize_links(entry.buy_links)
        except ValueError as exc:
            invalid.append({"model_number": entry.model_number, "reason": str(exc)})
            continue

        changed = False
        if entry.image_url and entry.image_url.strip():
            product.image_url = entry.image_url.strip()
            changed = True
        if entry.video_url and entry.video_url.strip():
            product.video_url = entry.video_url.strip()
            changed = True
        if links:
            _set_links(db, product.id, links)
            changed = True
        if changed:
            updated.append(entry.model_number)
    db.commit()
    return {"updated": len(updated), "not_found": not_found, "invalid": invalid}


@router.get("/feedback/summary")
def feedback_summary(db: Session = Depends(get_db)) -> dict:
    """Numbers for the admin Feedback page: the headline helpful rate, how each
    guide is doing, and the individual final answers people say did not help."""
    total, helpful = db.execute(
        select(func.count(), func.count().filter(GuideFeedback.helpful))
    ).one()

    guide_rows = db.execute(
        select(
            Symptom.id, Symptom.title, Symptom.category, Symptom.bot_type,
            func.count(GuideFeedback.id), func.count().filter(GuideFeedback.helpful),
        )
        .join(GuideFeedback, GuideFeedback.symptom_id == Symptom.id)
        .group_by(Symptom.id)
    ).all()
    guides = sorted(
        (
            {"symptom_id": str(i), "title": t, "category": c, "bot_type": b, "total": n, "helpful": h}
            for i, t, c, b, n, h in guide_rows
        ),
        key=lambda g: (g["helpful"] / g["total"], -g["total"]),
    )

    outcome_rows = db.execute(
        select(
            Symptom.title, GuideFeedback.outcome_key, GuideFeedback.outcome_kind,
            func.count(), func.count().filter(GuideFeedback.helpful),
        )
        .join(Symptom, Symptom.id == GuideFeedback.symptom_id)
        .group_by(Symptom.title, GuideFeedback.outcome_key, GuideFeedback.outcome_kind)
        .having(func.count() >= 3)
    ).all()
    weak = sorted(
        (
            {"title": t, "outcome_key": k or "(first question)", "kind": kind, "total": n, "helpful": h}
            for t, k, kind, n, h in outcome_rows
            if h / n < 0.6
        ),
        key=lambda o: (o["helpful"] / o["total"], -o["total"]),
    )[:15]

    return {"total": total, "helpful": helpful, "guides": guides, "weak_outcomes": weak}


@router.get("/symptoms")
def list_symptoms(db: Session = Depends(get_db)) -> list[dict]:
    symptoms = db.execute(select(Symptom)).scalars().all()
    return [
        {
            "id": str(s.id),
            "title": s.title,
            "slug": s.slug,
            "category": s.category,
            "bot_type": s.bot_type,
            "keywords": s.keywords or "",
        }
        for s in symptoms
    ]


@router.patch("/symptoms/{symptom_id}/keywords")
def update_symptom_keywords(
    symptom_id: uuid.UUID, payload: SymptomKeywordsUpdate, db: Session = Depends(get_db)
) -> dict:
    symptom = db.get(Symptom, symptom_id)
    if symptom is None:
        raise HTTPException(status_code=404, detail="Symptom not found.")
    symptom.keywords = ", ".join(k.strip() for k in payload.keywords if k.strip()) or None
    db.commit()
    return {"id": str(symptom.id), "keywords": symptom.keywords or ""}


@router.post("/categories", status_code=201)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)) -> dict:
    category = Category(name=payload.name, description=payload.description)
    db.add(category)
    db.commit()
    db.refresh(category)
    return {"id": str(category.id)}


@router.post("/products", status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)) -> dict:
    product = Product(
        category_id=payload.category_id,
        name=payload.name,
        model_number=payload.model_number,
        specs=payload.specs,
        use_case_tags=payload.use_case_tags,
        image_url=payload.image_url,
        video_url=payload.video_url,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return {"id": str(product.id)}


@router.post("/blog", status_code=201)
def create_blog_post(payload: BlogPostCreate, db: Session = Depends(get_db)) -> dict:
    post = BlogPost(
        product_id=payload.product_id,
        content=payload.content,
        do_you_know=payload.do_you_know,
        buy_links=payload.buy_links,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return {"id": str(post.id)}