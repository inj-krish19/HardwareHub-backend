"""Validation and normalisation for a product's store links (1 to 3 per product)."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

MAX_LINKS = 3


def derive_store(url: str) -> str:
    """'https://www.amazon.in/dp/x' -> 'Amazon'."""
    host = (urlparse(url).hostname or "").removeprefix("www.")
    name = host.split(".")[0]
    return name.capitalize() if name else "Store"


def normalize_links(raw: Any) -> list[dict[str, str]]:
    """
    Accepts any of:
      - None / "" (no links)
      - a comma-separated string of URLs (the old format)
      - a list of URL strings
      - a list of {"store": "...", "url": "..."} objects (store is optional)
    Returns a clean, de-duplicated list of {"store", "url"} in the given order,
    where index 0 is the primary ("Check price") link. Blank entries are
    ignored. Raises ValueError for a non-http(s) URL or more than MAX_LINKS.
    """
    if raw is None:
        return []
    items = raw.split(",") if isinstance(raw, str) else list(raw)

    out: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, str):
            url, store = item.strip(), ""
        elif isinstance(item, dict):
            url, store = (item.get("url") or "").strip(), (item.get("store") or "").strip()
        else:
            raise ValueError(f"unsupported link entry: {item!r}")
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"not a valid http(s) link: {url}")
        if len(url) > 1000:
            raise ValueError("link is longer than 1000 characters")
        if any(o["url"] == url for o in out):
            continue
        out.append({"store": (store or derive_store(url))[:60], "url": url})

    if len(out) > MAX_LINKS:
        raise ValueError(f"at most {MAX_LINKS} links per product, got {len(out)}")
    return out