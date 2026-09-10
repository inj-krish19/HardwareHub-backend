import json
from pathlib import Path

import pytest

from app.rule_engine import tree_walker

SEED_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "seed" / "ram_symptoms.json"
TREES = json.loads(SEED_PATH.read_text())


def _tree(title: str) -> dict:
    return next(t["question_tree"] for t in TREES if t["title"] == title)


def test_start_returns_first_question():
    result = tree_walker.start(_tree("RAM not detected / no display"))
    assert result.node_type == "question"
    assert result.node_id == "q1"
    assert "No / Not sure" in result.options


def test_walk_to_conclusion():
    result = tree_walker.answer(_tree("RAM not detected / no display"), ["No / Not sure"])
    assert result.node_type == "conclusion"
    assert "Reseat the RAM" in result.text


def test_walk_multi_level_to_escalate():
    result = tree_walker.answer(
        _tree("RAM not detected / no display"),
        ["Yes, it's locked in", "Yes, same issue in other slots", "No / Don't know"],
    )
    assert result.node_type == "escalate"
    assert "professional diagnosis" in result.text


def test_invalid_answer_raises():
    with pytest.raises(tree_walker.TreeWalkerError):
        tree_walker.answer(_tree("RAM not detected / no display"), ["Not a real option"])


def test_all_five_ram_trees_are_walkable_end_to_end():
    def walk_all_paths(node: dict):
        if node.get("type") in ("conclusion", "escalate"):
            return
        for option in node["options"]:
            walk_all_paths(option["next"])

    for entry in TREES:
        walk_all_paths(entry["question_tree"])