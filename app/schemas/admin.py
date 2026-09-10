from __future__ import annotations

import uuid

from pydantic import BaseModel


class SymptomSeedEntry(BaseModel):
    title: str
    category: str
    question_tree: dict


class ProductCreate(BaseModel):
    category_id: uuid.UUID
    name: str
    model_number: str
    specs: dict = {}
    use_case_tags: str | None = None


class CategoryCreate(BaseModel):
    name: str
    description: str | None = None


class BlogPostCreate(BaseModel):
    product_id: uuid.UUID
    content: str
    do_you_know: str | None = None
    buy_links: str | None = None