"""POST /chat/report against a real PostgreSQL. Safe on a database with real data:
see conftest.py (every change is rolled back; each test only looks at its own rows)."""
import pytest
from sqlalchemy import text

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
                    {"answer": "No", "next": {"type": "escalate", "text": "1. Take it to a technician."}},
                ],
            },
        },
    ],
}


@pytest.fixture()
def guide(client, db, admin_headers, tag):
    title = f"{tag} Black screen"
    body = [{"title": title, "category": f"Cat {tag}", "bot_type": "diagnostic", "keywords": ["x y"], "question_tree": TREE}]
    assert client.post("/api/v1/admin/seed/symptoms", json=body, headers=admin_headers).status_code == 201
    gid = next(s["id"] for s in client.get("/api/v1/admin/symptoms", headers=admin_headers).json() if s["title"] == title)
    return {"id": gid, "title": title, "category": f"Cat {tag}"}


def _report(client, gid, path):
    return client.post("/api/v1/chat/report", json={"symptom_id": gid, "answer_path": path})


def test_a_guide_that_ends_in_a_professional_gives_a_report(client, db, guide):
    r = _report(client, guide["id"], ["Yes", "No"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == guide["title"] and body["category"] == guide["category"]
    assert body["steps"] == [
        {"question": "Does the PC turn on?", "answer": "Yes"},
        {"question": "Is there a picture on the monitor?", "answer": "No"},
    ]
    assert body["finding"] == "1. Take it to a technician."
    assert f"Problem: {guide['title']}" in body["header"]
    assert "   Answer: No" in body["body"] and body["text"] == body["header"] + "\n\n" + body["body"]
    assert set(body) == {"title", "category", "steps", "finding", "header", "body", "text"}


def test_a_fix_is_not_a_report(client, db, guide):
    r = _report(client, guide["id"], ["No"])
    assert r.status_code == 400 and "professional help" in r.json()["detail"]


def test_an_unfinished_path_is_not_a_report(client, db, guide):
    assert _report(client, guide["id"], []).status_code == 400
    assert _report(client, guide["id"], ["Yes"]).status_code == 400


def test_an_invalid_path_is_refused(client, db, guide):
    assert _report(client, guide["id"], ["Maybe"]).status_code == 400
    assert _report(client, guide["id"], ["No", "Yes"]).status_code == 400  # continues past a final answer


def test_an_unknown_guide_is_404(client, db):
    assert _report(client, "00000000-0000-0000-0000-000000000000", ["Yes", "No"]).status_code == 404
    assert client.post("/api/v1/chat/report", json={"symptom_id": "not-a-uuid", "answer_path": []}).status_code == 422


def test_a_path_that_is_too_long_is_refused(client, db, guide):
    assert _report(client, guide["id"], ["Yes"] * 16).status_code == 422


def test_making_a_report_stores_nothing(client, db, guide):
    tables = ("guide_feedback", "unmatched_query", "symptom", "diagnosis_rule")
    before = {t: db.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in tables}
    assert _report(client, guide["id"], ["Yes", "No"]).status_code == 200
    assert _report(client, guide["id"], ["No"]).status_code == 400
    assert {t: db.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in tables} == before