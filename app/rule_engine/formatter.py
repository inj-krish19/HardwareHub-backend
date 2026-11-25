"""
Layer 3 — Response Formatter. Template-based, no text generation.
"""
from __future__ import annotations

from app.rule_engine.tree_walker import TraceStep, WalkResult

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


_REPORT_NOTE = (
    "This summary comes from a fixed troubleshooting guide written by people. "
    "It is a starting point for a technician, not a diagnosis."
)


def format_report(title: str, category: str, steps: list[TraceStep], result: WalkResult) -> dict:
    """Plain-text summary of a guide that ended in "needs a professional", for the
    person to copy and hand to a technician. Template only: every word comes from the
    guide itself (its title, its questions, the person's answers, its final text).

    Returned in two parts so the page can slot the person's own details (device, date,
    notes) between them: `header` (what the problem is) and `body` (what was checked and
    found). `text` is the two joined, for anything that just wants the whole report.
    """
    header = "\n".join(
        [
            "PC PROBLEM SUMMARY",
            f"Problem: {title.strip()}",
            f"Area: {category.strip()}",
            "Source: Hardware Hub guided troubleshooting",
        ]
    )

    checked = ["WHAT WAS CHECKED (in order)"]
    if steps:
        for number, step in enumerate(steps, start=1):
            checked.append(f"{number}. {step.question.strip()}")
            checked.append(f"   Answer: {step.answer.strip()}")
    else:
        checked.append("No questions were asked.")

    finding = (result.text or "").strip()
    body = "\n".join(
        [
            *checked,
            "",
            "WHAT THE GUIDE FOUND",
            finding or "The guide recommends professional help.",
            "",
            "NOTE",
            _REPORT_NOTE,
        ]
    )
    return {
        "header": header,
        "body": body,
        "text": f"{header}\n\n{body}",
        "finding": finding,
    }