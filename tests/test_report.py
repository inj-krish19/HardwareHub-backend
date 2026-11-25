"""The technician report: trace() and format_report() are pure, so they are tested directly."""
import json
from pathlib import Path

import pytest

from app.rule_engine import tree_walker
from app.rule_engine.formatter import format_report

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
                    {"answer": "Yes", "next": {"type": "conclusion", "text": "1. Nothing is wrong."}},
                    {"answer": "No", "next": {"type": "escalate", "text": "1. Take it to a technician.\n2. Say the screen stays black."}},
                ],
            },
        },
    ],
}


def test_trace_returns_every_question_with_the_answer_given():
    steps, result = tree_walker.trace(TREE, ["Yes", "No"])
    assert [(s.question, s.answer) for s in steps] == [
        ("Does the PC turn on?", "Yes"),
        ("Is there a picture on the monitor?", "No"),
    ]
    assert result.node_type == "escalate" and "technician" in result.text


def test_trace_of_an_empty_path_is_the_first_question_with_no_steps():
    steps, result = tree_walker.trace(TREE, [])
    assert steps == [] and result.node_type == "question" and result.node_id == "q1"


def test_trace_rejects_bad_paths_like_answer_does():
    with pytest.raises(tree_walker.TreeWalkerError):
        tree_walker.trace(TREE, ["Maybe"])
    with pytest.raises(tree_walker.TreeWalkerError):
        tree_walker.trace(TREE, ["No", "Yes"])  # continues past a final answer


def test_answer_still_agrees_with_trace():
    for path in ([], ["No"], ["Yes"], ["Yes", "No"]):
        assert tree_walker.answer(TREE, path) == tree_walker.trace(TREE, path)[1]


def test_report_lists_the_problem_the_checks_in_order_and_the_finding():
    steps, result = tree_walker.trace(TREE, ["Yes", "No"])
    report = format_report("  Black screen  ", "Display ", steps, result)
    assert report["header"].splitlines() == [
        "PC PROBLEM SUMMARY",
        "Problem: Black screen",
        "Area: Display",
        "Source: Hardware Hub guided troubleshooting",
    ]
    assert report["body"].splitlines()[:5] == [
        "WHAT WAS CHECKED (in order)",
        "1. Does the PC turn on?",
        "   Answer: Yes",
        "2. Is there a picture on the monitor?",
        "   Answer: No",
    ]
    assert "WHAT THE GUIDE FOUND\n1. Take it to a technician.\n2. Say the screen stays black." in report["body"]
    assert "not a diagnosis" in report["body"]
    assert report["text"] == report["header"] + "\n\n" + report["body"]
    assert report["finding"] == "1. Take it to a technician.\n2. Say the screen stays black."


def test_report_copes_with_no_questions_and_no_text():
    result = tree_walker.WalkResult(node_type="escalate", text="")
    report = format_report("Title", "Cat", [], result)
    assert "No questions were asked." in report["body"]
    assert "The guide recommends professional help." in report["body"]


def test_report_adds_nothing_the_guide_did_not_say():
    steps, result = tree_walker.trace(TREE, ["Yes", "No"])
    text = format_report("T", "C", steps, result)["text"]
    allowed = {"PC PROBLEM SUMMARY", "Source: Hardware Hub guided troubleshooting", "WHAT WAS CHECKED (in order)",
               "WHAT THE GUIDE FOUND", "NOTE", ""}
    for line in text.splitlines():
        line = line.strip()
        assert (
            line in allowed or line.startswith(("Problem:", "Area:", "Answer:", "This summary comes"))
            or any(line.endswith(q) for q in ("Does the PC turn on?", "Is there a picture on the monitor?"))
            or line in ("1. Take it to a technician.", "2. Say the screen stays black.")
        ), line


# ---- every real "needs a professional" answer in the guide files ----

SEED_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "seed"


def _escalations():
    """(title, category, path, tree) for every path that ends in an escalate."""
    def walk(node, prefix=()):
        if node.get("type") == "escalate":
            yield list(prefix)
        elif node.get("type") != "conclusion":
            for option in node["options"]:
                yield from walk(option["next"], prefix + (option["answer"],))

    for file in sorted(SEED_DIR.glob("*_symptoms.json")):
        for entry in json.loads(file.read_text(encoding="utf-8")):
            for path in walk(entry["question_tree"]):
                yield entry["title"], entry["category"], path, entry["question_tree"]


ESCALATIONS = list(_escalations())


def test_there_are_real_escalations_to_check():
    assert len(ESCALATIONS) >= 10


@pytest.mark.parametrize("title,category,path,tree", ESCALATIONS, ids=[f"{t} | {' > '.join(p)}"[:100] for t, _, p, _ in ESCALATIONS])
def test_every_real_escalation_gives_a_complete_report(title, category, path, tree):
    steps, result = tree_walker.trace(tree, path)
    assert result.node_type == "escalate" and len(steps) == len(path)
    report = format_report(title, category, steps, result)
    assert f"Problem: {title.strip()}" in report["header"]
    for step in steps:
        assert step.question.strip() in report["body"] and f"Answer: {step.answer.strip()}" in report["body"]
    assert report["finding"] and report["finding"] in report["body"]