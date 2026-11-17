"""
Layer 1 — Intent Router. Keyword/regex only, scoped simple on purpose.
The intent is only a hint (it nudges matching toward one bot); matching
itself runs across every bot's content.
"""
from __future__ import annotations

import re

INTENTS = ("diagnostic", "compatibility", "budget_advisor", "upgrade_advisor", "maintenance")

# Maps router intent -> Symptom.bot_type
INTENT_TO_BOT = {
    "diagnostic": "diagnostic",
    "compatibility": "compatibility",
    "budget_advisor": "budget",
    "upgrade_advisor": "upgrade",
    "maintenance": "maintenance",
}

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("compatibility", re.compile(r"\b(compatible|compatibility|will (this|it) work with|work with my|fit(s)? (my|the|in)|ddr[345] .*(board|slot)|socket|(power supply|psu).*(handle|support|enough|run))\b", re.I)),
    ("upgrade_advisor", re.compile(r"\b(upgrade|upgrading|bottleneck|holding (my )?\w* ?back|worth upgrading|replace my (cpu|gpu|ram))\b", re.I)),
    ("budget_advisor", re.compile(r"(\bbudget\b|₹|\brs\.?\s?\d|\binr\b|\bunder \d|\bbest pc\b|\bbuild (a|me a)? ?pc\b|\bpc build\b|\b\d{2,3},?\d{3}\b|\brecommend(ed)? (a )?(pc|build|setup))", re.I)),
    ("maintenance", re.compile(r"\b(clean(ing)?|dust(y)?|thermal paste|how often|maintenance|maintain|backup|back up|keep (my )?pc (healthy|running))\b", re.I)),
    ("diagnostic", re.compile(r"\b(not working|won'?t (boot|turn on|start|post)|broken|crash(es|ing)?|blue ?screen|bsod|no display|not detected|overheating|freezing|black screen|no signal|keeps? restarting)\b", re.I)),
]


def route(query: str) -> str | None:
    for intent, pattern in _PATTERNS:
        if pattern.search(query):
            return intent
    return None