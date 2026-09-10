from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.catalog import Product

router = APIRouter(prefix="/compare", tags=["compare"])

MAX_COMPARE = 3


@router.get("")
def compare_products(
    product_ids: list[uuid.UUID] = Query(..., min_length=2, max_length=MAX_COMPARE),
    db: Session = Depends(get_db),
) -> dict:
    """
    Freeform compare, capped at 2-3 products per your comparison module scope.
    All products must share a category — this is enforced rather than left to
    the frontend, since cross-category diffs (RAM vs PSU) aren't meaningful.
    Spec rows are the UNION of all products' spec keys, so it works for any
    product without per-pair admin setup.
    """
    products = db.execute(select(Product).where(Product.id.in_(product_ids))).scalars().all()
    if len(products) != len(set(product_ids)):
        raise HTTPException(status_code=404, detail="One or more product ids not found.")

    category_ids = {p.category_id for p in products}
    if len(category_ids) > 1:
        raise HTTPException(
            status_code=400,
            detail="Products must be in the same category to compare (e.g. RAM vs RAM, not RAM vs PSU).",
        )

    all_spec_keys = sorted({key for p in products for key in p.specs.keys()})

    return {
        "products": [
            {"id": str(p.id), "name": p.name, "model_number": p.model_number} for p in products
        ],
        "rows": [
            {
                "label": key,
                "values": {str(p.id): p.specs.get(key, "—") for p in products},
            }
            for key in all_spec_keys
        ],
    }