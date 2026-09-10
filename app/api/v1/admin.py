from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.admin_auth import require_admin
from app.db.session import get_db
from app.models.catalog import BlogPost, Category, Product
from app.models.rules import DiagnosisRule, Symptom
from app.schemas.admin import (
    BlogPostCreate,
    CategoryCreate,
    ProductCreate,
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
        symptom = Symptom(title=entry.title, category=entry.category)
        db.add(symptom)
        db.flush()
        db.add(DiagnosisRule(symptom_id=symptom.id, question_tree=entry.question_tree))
        created += 1
    db.commit()
    return {"created": created}


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