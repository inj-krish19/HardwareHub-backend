"""
Layer 1 — Intent Router. Keyword/regex only, scoped simple for MVP.
"""
from __future__ import annotations

import re

INTENTS = ("diagnostic", "compatibility", "budget_advisor", "upgrade_advisor", "maintenance")

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("compatibility", re.compile(r"\b(compatible|compatibility|will (this|it) work with|fit(s)? (my|the) (motherboard|socket))\b", re.I)),
    ("upgrade_advisor", re.compile(r"\b(upgrade|bottleneck|should i (replace|upgrade)|worth upgrading)\b", re.I)),
    ("budget_advisor", re.compile(r"\b(budget|₹|under \d|recommend(ed)? (pc|build)|best pc for)\b", re.I)),
    ("maintenance", re.compile(r"\b(clean(ing)?|dust|thermal paste|how often|maintenance|maintain)\b", re.I)),
    ("diagnostic", re.compile(r"\b(not working|won'?t (boot|turn on|start)|broken|crash(es|ing)?|blue ?screen|bsod|no display|not detected|overheating|freezing)\b", re.I)),
]


def route(query: str) -> str | None:
    for intent, pattern in _PATTERNS:
        if pattern.search(query):
            return intent
    return None