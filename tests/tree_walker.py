"""Tests for Layer 2 (tree_walker) and for the guide JSON files in app/data/seed.

Run from backend/:  python -m pytest
(`python -m` puts backend/ on the import path so `import app...` works.)
"""
import json
from pathlib import Path

import pytest

from app.rule_engine import tree_walker

SEED_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "seed"

# A small tree built here, so these tests do not depend on any seed file's wording.
TREE = {
    "id": "q1",
    "question": "Does the PC turn on?",
    "options": [
        {"answer": "No", "next": {"type": "conclusion", "text": "1. Check the power cable."}},
        {
            "answer": "Yes",
            "next": {
                "id": "q2",
                "question": "Is there a picture on the monitor?",
                "options": [
                    {"answer": "Yes", "next": {"type": "conclusion", "text": "1. Nothing is wrong with the display."}},
                    {"answer": "No", "next": {"type": "escalate", "text": "1. Take it to a technician."}},
                ],
            },
        },
    ],
}


def test_start_returns_first_question():
    result = tree_walker.start(TREE)
    assert result.node_type == "question"
    assert result.node_id == "q1"
    assert result.options == ["No", "Yes"]


def test_walk_to_conclusion():
    result = tree_walker.answer(TREE, ["No"])
    assert result.node_type == "conclusion"
    assert "power cable" in result.text


def test_walk_multi_level_to_escalate():
    result = tree_walker.answer(TREE, ["Yes", "No"])
    assert result.node_type == "escalate"
    assert "technician" in result.text


def test_empty_path_is_the_first_question():
    assert tree_walker.answer(TREE, []).node_id == "q1"


def test_invalid_answer_raises():
    with pytest.raises(tree_walker.TreeWalkerError):
        tree_walker.answer(TREE, ["Maybe"])


def test_path_past_a_final_answer_raises():
    with pytest.raises(tree_walker.TreeWalkerError):
        tree_walker.answer(TREE, ["No", "Yes"])


def test_malformed_node_raises():
    with pytest.raises(tree_walker.TreeWalkerError):
        tree_walker.start({"id": "q1"})


# ---- the real guide files ---------------------------------------------------

def _guides() -> list[tuple[str, dict]]:
    out = []
    for path in sorted(SEED_DIR.glob("*_symptoms.json")):
        for entry in json.loads(path.read_text(encoding="utf-8")):
            out.append((path.name, entry))
    return out


GUIDES = _guides()


def _all_paths(node: dict, prefix: tuple[str, ...] = ()):
    """Every answer path from the root down to a final answer."""
    if node.get("type") in ("conclusion", "escalate"):
        yield list(prefix)
        return
    for option in node["options"]:
        yield from _all_paths(option["next"], prefix + (option["answer"],))


def test_seed_files_exist():
    assert GUIDES, f"no *_symptoms.json files found in {SEED_DIR}"


@pytest.mark.parametrize("filename,entry", GUIDES, ids=[f"{f}:{e['title']}" for f, e in GUIDES])
def test_every_path_of_every_guide_reaches_a_final_answer(filename, entry):
    paths = list(_all_paths(entry["question_tree"]))
    assert paths, "guide has no final answers"
    for path in paths:
        result = tree_walker.answer(entry["question_tree"], path)
        assert result.node_type in ("conclusion", "escalate"), path
        assert result.text and result.text.strip(), f"empty final answer at {path}"


def test_guide_titles_are_unique_across_files():
    seen: dict[str, str] = {}
    for filename, entry in GUIDES:
        key = entry["title"].strip().lower()
        assert key not in seen, f"{entry['title']!r} is in both {seen[key]} and {filename}"
        seen[key] = filename