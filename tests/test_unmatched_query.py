"""Missed-query log tests against a real PostgreSQL. Safe on a database with real data:
see conftest.py (every change is rolled back; each test only looks at its own rows).

`tag` names the guides a test creates. `qtag` is a random token, and the chat messages a test
sends are made ONLY of tokens built from it (`{qtag}a`, `{qtag}b`, ...). Real English words must
not be used: any word that is a keyword of a real guide would make the message match that guide,
and a message that matches a guide is not logged."""
import pytest
from sqlalchemy import text

import app.api.v1.admin as admin_module
from app.db import query_log


def _tree() -> dict:
    return {
        "id": "q1",
        "question": "Does it work?",
        "options": [
            {"answer": "Yes", "next": {"type": "conclusion", "text": "1. Fine."}},
            {"answer": "No", "next": {"type": "escalate", "text": "1. See a technician."}},
        ],
    }


@pytest.fixture()
def guides(client, db, admin_headers, tag):
    """Two guides of this test, plus a helper to find their ids. Returns their titles."""
    titles = {"power": f"{tag} No power / PC will not turn on", "ram": f"{tag} RAM not detected"}
    body = [
        {"title": titles["power"], "category": f"Cat {tag}", "bot_type": "diagnostic",
         "keywords": [f"{tag} pc dead"], "question_tree": _tree()},
        {"title": titles["ram"], "category": f"Cat {tag}", "bot_type": "diagnostic",
         "keywords": [f"{tag} ram missing"], "question_tree": _tree()},
    ]
    assert client.post("/api/v1/admin/seed/symptoms", json=body, headers=admin_headers).status_code == 201
    return titles


@pytest.fixture(autouse=True)
def full_listing(monkeypatch):
    # The list is capped at 200 rows; a real log can be longer, so lift the cap for these tests.
    monkeypatch.setattr(admin_module, "UNMATCHED_LIST_LIMIT", 1_000_000)


def _start(client, query):
    return client.post("/api/v1/chat/start", json={"query": query})


def _mine(client, headers, qtag, status="open"):
    r = client.get(f"/api/v1/admin/unmatched?status={status}", headers=headers)
    assert r.status_code == 200, r.text
    return [row for row in r.json() if qtag in row["text"].lower()]


def _logged(db, qtag):
    return db.execute(text("SELECT text FROM unmatched_query WHERE normalized LIKE :p"), {"p": f"%{qtag}%"}).scalars().all()


def _guide_id(client, headers, title):
    return next(s["id"] for s in client.get("/api/v1/admin/symptoms", headers=headers).json() if s["title"] == title)


def _add(client, headers, row_id, guide_id, keyword):
    return client.post(f"/api/v1/admin/unmatched/{row_id}/keyword", json={"symptom_id": guide_id, "keyword": keyword}, headers=headers)


def _status(client, headers, row_id, status):
    return client.post(f"/api/v1/admin/unmatched/{row_id}/status", json={"status": status}, headers=headers)


def test_a_message_that_matches_nothing_is_logged_once_and_counted(client, db, admin_headers, qtag):
    wording = f"{qtag}a {qtag}b"
    for variant in (wording, wording.upper() + "!!", "  " + wording):
        assert _start(client, variant).status_code == 200  # the chat itself still answers
    rows = _mine(client, admin_headers, qtag)
    assert len(rows) == 1
    assert rows[0]["times_seen"] == 3 and rows[0]["text"] == wording and rows[0]["status"] == "open"
    assert set(rows[0]) == {"id", "text", "times_seen", "first_seen", "last_seen", "status", "resolved_guide"}


def test_a_message_that_matches_a_guide_is_not_logged(client, db, admin_headers, guides, tag, qtag):
    # the guide has the keyword "<tag> pc dead", so a message containing it matches
    r = _start(client, f"my {tag} pc dead")
    assert r.json()["kind"] == "suggest" and guides["power"] in r.json()["options"]
    assert _logged(db, tag) == []


def test_personal_data_is_never_stored(client, db, admin_headers, qtag):
    _start(client, f"{qtag}a sam@example.com")
    _start(client, f"{qtag}b 9876543210")
    assert _logged(db, qtag) == []
    _start(client, f"{qtag}c")  # control: the same kind of message without personal data IS logged
    assert _logged(db, qtag) == [f"{qtag}c"]


def test_the_table_has_no_identity_columns(client, db):
    cols = set(db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'unmatched_query'")).scalars())
    assert cols == {"id", "text", "normalized", "times_seen", "first_seen", "last_seen", "status", "resolved_symptom_id"}


def test_a_deleted_guide_would_not_delete_the_logged_message(client, db):
    # Read-only check of the declared rule (the tests never delete anything): the
    # link from a miss to its guide is cleared, not cascaded, when the guide goes away.
    rule = db.execute(text(
        "SELECT rc.delete_rule FROM information_schema.referential_constraints rc "
        "JOIN information_schema.key_column_usage k ON k.constraint_name = rc.constraint_name "
        "WHERE k.table_name = 'unmatched_query' AND k.column_name = 'resolved_symptom_id'"
    )).scalar()
    assert rule == "SET NULL"


def test_admin_endpoints_need_the_admin_login(client):
    assert client.get("/api/v1/admin/unmatched").status_code in (401, 422)
    assert client.get("/api/v1/admin/unmatched", headers={"X-Admin-Id": "x", "X-Admin-Secret": "y"}).status_code == 401


def test_list_puts_the_most_repeated_first_and_filters_by_status(client, db, admin_headers, qtag):
    for _ in range(3):
        _start(client, f"{qtag}a")
    _start(client, f"{qtag}b")
    rows = _mine(client, admin_headers, qtag)
    assert [r["text"] for r in rows] == [f"{qtag}a", f"{qtag}b"]
    assert _status(client, admin_headers, rows[1]["id"], "dismissed").status_code == 200
    assert [r["text"] for r in _mine(client, admin_headers, qtag)] == [f"{qtag}a"]
    assert [r["text"] for r in _mine(client, admin_headers, qtag, "dismissed")] == [f"{qtag}b"]
    assert len(_mine(client, admin_headers, qtag, "all")) == 2
    assert client.get("/api/v1/admin/unmatched?status=bogus", headers=admin_headers).status_code == 422


def test_adding_a_keyword_fixes_the_miss_and_the_chat_then_finds_the_guide(client, db, admin_headers, guides, qtag):
    query = f"{qtag}a {qtag}b {qtag}c"
    assert _start(client, query).json()["kind"] != "suggest"
    row = _mine(client, admin_headers, qtag)[0]

    r = _add(client, admin_headers, row["id"], _guide_id(client, admin_headers, guides["power"]), f"{qtag}a {qtag}b")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["guide"] == guides["power"] and body["now_matches"] is True
    assert f"{qtag}a {qtag}b" in body["keywords"]

    fixed = _mine(client, admin_headers, qtag, "fixed")
    assert [f["resolved_guide"] for f in fixed] == [guides["power"]]
    assert _mine(client, admin_headers, qtag) == []
    again = _start(client, query).json()
    assert again["kind"] == "suggest" and guides["power"] in again["options"]
    assert _mine(client, admin_headers, qtag, "fixed")[0]["times_seen"] == 1  # the fixed message is no longer logged


def test_a_phrase_that_is_too_narrow_is_reported(client, db, admin_headers, guides, qtag):
    _start(client, f"{qtag}a {qtag}b")
    row = _mine(client, admin_headers, qtag)[0]
    r = _add(client, admin_headers, row["id"], _guide_id(client, admin_headers, guides["ram"]), "unrelated phrase")
    assert r.status_code == 200 and r.json()["now_matches"] is False


def test_the_same_keyword_is_not_added_twice_and_bad_keywords_are_refused(client, db, admin_headers, guides, tag, qtag):
    _start(client, f"{qtag}a")
    row = _mine(client, admin_headers, qtag)[0]
    gid = _guide_id(client, admin_headers, guides["ram"])
    _add(client, admin_headers, row["id"], gid, f"{tag.upper()} Ram Missing")
    r = _add(client, admin_headers, row["id"], gid, f"{tag} ram missing")
    assert r.json()["keywords"].lower().count(f"{tag} ram missing") == 1
    assert _add(client, admin_headers, row["id"], gid, "x").status_code == 422
    assert _add(client, admin_headers, row["id"], gid, "123").status_code == 422
    assert _add(client, admin_headers, row["id"], gid, "a, b").status_code == 200  # the comma becomes a space
    nobody = "00000000-0000-0000-0000-000000000000"
    assert _add(client, admin_headers, row["id"], nobody, "valid phrase").status_code == 404
    assert _add(client, admin_headers, nobody, gid, "valid phrase").status_code == 404


def test_a_fixed_message_that_fails_again_is_reopened_but_a_dismissed_one_stays_dismissed(client, db, admin_headers, guides, qtag):
    _start(client, f"{qtag}a")
    _start(client, f"{qtag}b")
    a, b = sorted(_mine(client, admin_headers, qtag), key=lambda r: r["text"])  # ...a, ...b
    gid = _guide_id(client, admin_headers, guides["ram"])
    _add(client, admin_headers, b["id"], gid, "unrelated words")  # fixed, but the phrase does not help
    _status(client, admin_headers, a["id"], "dismissed")
    _start(client, f"{qtag}b")   # still matches nothing: the fix did not work
    _start(client, f"{qtag}a")
    assert [r["text"] for r in _mine(client, admin_headers, qtag)] == [f"{qtag}b"]
    dismissed = _mine(client, admin_headers, qtag, "dismissed")
    assert dismissed[0]["text"] == f"{qtag}a" and dismissed[0]["times_seen"] == 2
    assert _status(client, admin_headers, a["id"], "open").json()["status"] == "open"


def test_export_uses_the_evaluation_file_format(client, db, admin_headers, guides, qtag):
    for name in ("a", "b", "c"):
        _start(client, f"{qtag}{name}")
    rows = {r["text"]: r for r in _mine(client, admin_headers, qtag)}
    _add(client, admin_headers, rows[f"{qtag}a"]["id"], _guide_id(client, admin_headers, guides["power"]), f"{qtag}a")
    _status(client, admin_headers, rows[f"{qtag}b"]["id"], "dismissed")
    exported = [e for e in client.get("/api/v1/admin/unmatched/export", headers=admin_headers).json() if qtag in e["query"].lower()]
    assert {e["query"]: e["expected"] for e in exported} == {
        f"{qtag}a": guides["power"],   # labelled by the admin
        f"{qtag}c": "TODO",            # not labelled yet; the dismissed one (b) is left out
    }
    assert all(set(e) == {"query", "expected"} for e in exported)


def test_the_size_cap_stops_new_wordings_but_known_ones_still_count(client, db, admin_headers, qtag, monkeypatch):
    existing = db.execute(text("SELECT count(*) FROM unmatched_query")).scalar()
    monkeypatch.setattr(query_log, "MAX_DISTINCT_QUERIES", existing + 2)
    for name in ("a", "b", "c", "a"):
        _start(client, f"{qtag}{name}")
    rows = {r["text"]: r["times_seen"] for r in _mine(client, admin_headers, qtag)}
    assert rows == {f"{qtag}a": 2, f"{qtag}b": 1}  # "c" is a new wording over the cap, so it is not stored


def test_a_logging_failure_never_breaks_the_chat(client, db, qtag, monkeypatch):
    from sqlalchemy.exc import OperationalError

    def boom(*args, **kwargs):
        raise OperationalError("insert", {}, Exception("database hiccup"))

    monkeypatch.setattr(db, "execute", boom)
    assert query_log.log_unmatched(db, f"{qtag}a") is False