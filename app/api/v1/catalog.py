from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.catalog import BlogPost, Category, Product

router = APIRouter(tags=["catalog"])


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)) -> list[dict]:
    categories = db.execute(select(Category)).scalars().all()
    return [{"id": str(c.id), "name": c.name, "description": c.description} for c in categories]


@router.get("/products")
def list_products(category_id: uuid.UUID | None = None, db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(Product)
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    products = db.execute(stmt).scalars().all()
    return [
        {
            "id": str(p.id),
            "category_id": str(p.category_id),
            "name": p.name,
            "model_number": p.model_number,
            "specs": p.specs,
            "use_case_tags": p.use_case_tags,
        }
        for p in products
    ]


@router.get("/products/{product_id}")
def get_product(product_id: uuid.UUID, db: Session = Depends(get_db)) -> dict | None:
    product = db.get(Product, product_id)
    if product is None:
        return None
    blog_posts = db.execute(
        select(BlogPost).where(BlogPost.product_id == product_id)
    ).scalars().all()
    return {
        "id": str(product.id),
        "category_id": str(product.category_id),
        "name": product.name,
        "model_number": product.model_number,
        "specs": product.specs,
        "use_case_tags": product.use_case_tags,
        "blog_posts": [
            {
                "id": str(bp.id),
                "content": bp.content,
                "do_you_know": bp.do_you_know,
                "buy_links": bp.buy_links,
            }
            for bp in blog_posts
        ],
    }