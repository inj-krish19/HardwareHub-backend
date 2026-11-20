from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.links import normalize_links
from app.models.catalog import BlogPost, Category, Product, ProductLink

router = APIRouter(tags=["catalog"])


def _product_dict(p: Product, category_name: str) -> dict:
    return {
        "id": str(p.id),
        "category_id": str(p.category_id),
        "category_name": category_name,
        "name": p.name,
        "model_number": p.model_number,
        "specs": p.specs,
        "use_case_tags": p.use_case_tags,
        "image_url": p.image_url,
        "video_url": p.video_url,
    }


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)) -> list[dict]:
    categories = db.execute(select(Category).order_by(Category.name)).scalars().all()
    return [{"id": str(c.id), "name": c.name, "description": c.description} for c in categories]


@router.get("/products")
def list_products(category_id: uuid.UUID | None = None, db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(Product, Category.name).join(Category, Product.category_id == Category.id)
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    rows = db.execute(stmt.order_by(Category.name, Product.name)).all()
    return [_product_dict(p, cat_name) for p, cat_name in rows]


@router.get("/products/{product_id}")
def get_product(product_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    category = db.get(Category, product.category_id)
    blog_posts = db.execute(
        select(BlogPost).where(BlogPost.product_id == product_id)
    ).scalars().all()
    links = db.execute(
        select(ProductLink).where(ProductLink.product_id == product_id).order_by(ProductLink.position)
    ).scalars().all()
    buy_links = [{"position": l.position, "store": l.store, "url": l.url} for l in links]
    if not buy_links:
        # Legacy fallback: links that were saved on the blog post before ProductLink existed.
        for post in blog_posts:
            try:
                legacy = normalize_links(post.buy_links)[:3]
            except ValueError:
                legacy = []
            if legacy:
                buy_links = [{"position": i, **l} for i, l in enumerate(legacy)]
                break
    return {
        **_product_dict(product, category.name if category else ""),
        "buy_links": buy_links,
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