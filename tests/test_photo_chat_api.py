"""POST /chat/start with text read from a photo. Safe on a database with real data: see conftest.py."""
import pytest
from sqlalchemy import text

import app.api.v1.admin as admin_module  # noqa: F401  (keeps the import side effects the other API tests rely on)

TREE = {"id": "q1", "question": "Does it work?", "options": [
    {"answer": "Yes", "next": {"type": "conclusion", "text": "1. Fine."}},
    {"answer": "No", "next": {"type": "escalate", "text": "1. See a technician."}}]}

BSOD = ("Your PC ran into a problem and needs to restart. We're just collecting some error info. "
        "42% complete. Stop code: CRITICAL_PROCESS_DIED")


@pytest.fixture()
def blue_screen_guide(client, db, admin_headers, tag):
    title = f"{tag} Random crashes or Blue Screen errors"
    body = [{"title": title, "category": f"Cat {tag}", "bot_type": "diagnostic",
             "keywords": ["blue screen of death", "bsod errors"], "question_tree": TREE}]
    assert client.post("/api/v1/admin/seed/symptoms", json=body, headers=admin_headers).status_code == 201
    return title


def _start(client, query, source=None):
    body = {"query": query} if source is None else {"query": query, "source": source}
    return client.post("/api/v1/chat/start", json=body)


def test_photo_text_of_a_blue_screen_suggests_the_guide_and_says_what_it_recognised(client, db, blue_screen_guide):
    r = _start(client, BSOD, "photo")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "suggest" and blue_screen_guide in body["options"]
    assert body["message"].startswith("That looks like a Windows blue screen.")


def test_the_same_text_typed_is_matched_as_before_without_the_screen_wording(client, db, blue_screen_guide):
    body = _start(client, BSOD).json()
    assert "That looks like" not in body["message"]


def test_photo_text_is_never_written_to_the_missed_query_log(client, db, qtag):
    wording = f"{qtag}a {qtag}b"
    assert _start(client, wording, "photo").status_code == 200  # matches nothing
    assert db.execute(text("SELECT count(*) FROM unmatched_query WHERE normalized LIKE :p"), {"p": f"%{qtag}%"}).scalar() == 0
    assert _start(client, wording, "typed").status_code == 200  # the same text typed IS logged
    assert db.execute(text("SELECT count(*) FROM unmatched_query WHERE normalized LIKE :p"), {"p": f"%{qtag}%"}).scalar() == 1


def test_typed_text_is_still_limited_to_500_characters_but_photo_text_may_be_longer(client, db, qtag):
    long_text = f"{qtag}a " * 120  # about 1,000 characters
    assert _start(client, long_text).status_code == 422
    assert _start(client, long_text, "photo").status_code == 200
    assert _start(client, "x" * 4001, "photo").status_code == 422


def test_an_unknown_source_is_refused(client, db):
    assert _start(client, "hello there", "voice").status_code == 422