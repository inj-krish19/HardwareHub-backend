"""URL slugs for guides: "No power / PC will not turn on" -> "no-power-pc-will-not-turn-on".

Pure functions, no database, so they can be tested directly. A guide's slug is
generated once, when the guide is created, and then stored. It does NOT change
if the title is edited later, so a guide's public URL stays stable.
"""
from __future__ import annotations

import re
import unicodedata

MAX_SLUG_LENGTH = 80


def slugify(text: str, max_length: int = MAX_SLUG_LENGTH) -> str:
    """Lower-case ASCII letters and digits joined by single hyphens, at most
    `max_length` characters. Falls back to "guide" if nothing usable is left."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    slug = slug[:max_length].strip("-")
    return slug or "guide"


def unique_slug(base: str, taken: set[str]) -> str:
    """`base` if it is free, otherwise base-2, base-3, ... The chosen slug is
    added to `taken`, so calling this in a loop never hands out a slug twice."""
    candidate, n = base, 2
    while candidate in taken:
        candidate = f"{base}-{n}"
        n += 1
    taken.add(candidate)
    return candidate