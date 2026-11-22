"""
Layer 3 — Response Formatter. Template-based, no text generation.
"""
from __future__ import annotations

from app.rule_engine.tree_walker import WalkResult

_ESCALATE_PREFIX = "This one's beyond a quick fix — here's what we found, and next steps: "


def format_result(result: WalkResult) -> dict:
    if result.node_type == "question":
        return {
            "kind": "question",
            "node_id": result.node_id,
            "message": result.question,
            "options": result.options,
        }
    if result.node_type == "conclusion":
        return {"kind": "conclusion", "message": result.text}
    return {"kind": "escalate", "message": f"{_ESCALATE_PREFIX}{result.text}"}