"""
Layer 2 — Rule Engine. Pure functions over the question_tree JSONB shape.
No I/O here on purpose — testable and reusable across all 5 bots.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

NodeType = Literal["question", "conclusion", "escalate"]


@dataclass
class WalkResult:
    node_type: NodeType
    node_id: str | None = None
    question: str | None = None
    options: list[str] | None = None
    text: str | None = None


class TreeWalkerError(ValueError):
    pass


def _classify(node: dict[str, Any]) -> NodeType:
    if node.get("type") in ("conclusion", "escalate"):
        return node["type"]  # type: ignore[return-value]
    if "question" in node and "options" in node:
        return "question"
    raise TreeWalkerError(f"Malformed tree node, cannot classify: {node!r}")


def start(tree: dict[str, Any]) -> WalkResult:
    return _to_result(tree)


def answer(tree: dict[str, Any], answer_path: list[str]) -> WalkResult:
    node = tree
    for chosen_answer in answer_path:
        node_type = _classify(node)
        if node_type != "question":
            raise TreeWalkerError(f"Answer path continues past a terminal node ({node_type}).")
        options = node.get("options", [])
        match = next((o for o in options if o.get("answer") == chosen_answer), None)
        if match is None:
            valid = [o.get("answer") for o in options]
            raise TreeWalkerError(f"'{chosen_answer}' is not a valid answer here. Valid options: {valid}")
        node = match["next"]
    return _to_result(node)


def _to_result(node: dict[str, Any]) -> WalkResult:
    node_type = _classify(node)
    if node_type == "question":
        return WalkResult(
            node_type="question",
            node_id=node.get("id"),
            question=node["question"],
            options=[o["answer"] for o in node.get("options", [])],
        )
    return WalkResult(node_type=node_type, text=node.get("text", ""))