from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, field_validator


class SymptomSeedEntry(BaseModel):
    title: str
    category: str
    question_tree: dict
    keywords: list[str] = []  # optional synonyms, joined to a comma-string on save
    bot_type: str = "diagnostic"  # diagnostic | compatibility | budget | upgrade | maintenance


class BlogSeedEntry(BaseModel):
    content: str
    do_you_know: str | None = None
    buy_links: str | None = None


class ProductSeedEntry(BaseModel):
    category: str  # matched by name (case-insensitive); created if missing
    name: str
    model_number: str
    specs: dict = {}
    use_case_tags: str | None = None
    image_url: str | None = None
    video_url: str | None = None
    # 1 to 3 store links; [0] is the primary "Check price" link. Each item is a
    # URL string or {"store": "...", "url": "..."}. A comma-separated string works too.
    buy_links: Any = None
    blog: BlogSeedEntry | None = None


class MediaSeedEntry(BaseModel):
    """Update media/links on an existing product, matched by model number.
    Empty or missing fields leave the current value untouched."""
    model_number: str
    image_url: str | None = None
    video_url: str | None = None
    buy_links: Any = None  # same accepted shapes as ProductSeedEntry.buy_links; replaces existing links


class SymptomKeywordsUpdate(BaseModel):
    keywords: list[str]


class ProductCreate(BaseModel):
    category_id: uuid.UUID
    name: str
    model_number: str
    specs: dict = {}
    use_case_tags: str | None = None
    image_url: str | None = None
    video_url: str | None = None

    @field_validator("image_url", "video_url")
    @classmethod
    def _clean_media_url(cls, value: str | None) -> str | None:
        """Blank means "no media". Anything else must be an http(s) link that
        fits the 500-character database column."""
        if value is None or not value.strip():
            return None
        value = value.strip()
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("must be a full http(s) link")
        if len(value) > 500:
            raise ValueError("must be 500 characters or fewer")
        return value


class CategoryCreate(BaseModel):
    name: str
    description: str | None = None


class BlogPostCreate(BaseModel):
    product_id: uuid.UUID
    content: str
    do_you_know: str | None = None
    buy_links: str | None = None