from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

import uuid

from app.core.admin_auth import require_admin
from app.db.session import get_db
from app.models.catalog import BlogPost, Category, Product
from app.models.rules import DiagnosisRule, Symptom
from app.schemas.admin import (
    BlogPostCreate,
    CategoryCreate,
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
    JSON array straight into this endpoint's request body."""
    created = 0
    for entry in entries:
        symptom = Symptom(
            title=entry.title,
            category=entry.category,
            keywords=", ".join(entry.keywords) if entry.keywords else None,
            bot_type=entry.bot_type,
        )
        db.add(symptom)
        db.flush()
        db.add(DiagnosisRule(symptom_id=symptom.id, question_tree=entry.question_tree))
        created += 1
    db.commit()
    return {"created": created}


@router.post("/seed/products", status_code=201)
def bulk_upload_products(entries: list[ProductSeedEntry], db: Session = Depends(get_db)) -> dict:
    """Products + optional blog post in one paste. Categories are found by name
    (created if missing). A product with the same name and model number is
    skipped, so re-pasting the same file is safe."""
    created, skipped = 0, 0
    categories: dict[str, Category] = {c.name.lower(): c for c in db.execute(select(Category)).scalars()}
    for entry in entries:
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
        )
        db.add(product)
        db.flush()
        if entry.blog:
            db.add(
                BlogPost(
                    product_id=product.id,
                    content=entry.blog.content,
                    do_you_know=entry.blog.do_you_know,
                    buy_links=entry.blog.buy_links or None,
                )
            )
        created += 1
    db.commit()
    return {"created": created, "skipped": skipped}


@router.get("/symptoms")
def list_symptoms(db: Session = Depends(get_db)) -> list[dict]:
    symptoms = db.execute(select(Symptom)).scalars().all()
    return [
        {
            "id": str(s.id),
            "title": s.title,
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