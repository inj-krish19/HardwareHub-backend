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


def format_recommendation(task_type: str, budget_amount: int, component_set: dict) -> dict:
    """Layer 3 for the Budget/Build Advisor bot. component_set is a flat
    {component_category: recommendation_text} JSONB dict — no question_tree
    involved for this bot, so this is templated directly rather than going
    through tree_walker. Reuses the "conclusion" kind so the frontend needs
    no new rendering path for the final answer."""
    lines = [
        f"Here's a suggested build for {task_type} around ₹{budget_amount:,}:",
        "",
    ]
    for i, (component, recommendation) in enumerate(component_set.items(), start=1):
        lines.append(f"{i}. {component.upper()}: {recommendation}")
    return {"kind": "conclusion", "message": "\n".join(lines)}