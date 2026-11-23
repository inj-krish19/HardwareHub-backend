"""API tests against a real PostgreSQL (see conftest.py for how to run them)."""
from sqlalchemy import text

from app.db.backfill_slugs import assign_missing_slugs
from app.db.session import SessionLocal, engine


def _tree(answer_text: str = "1. Do the thing.") -> dict:
    return {
        "id": "q1",
        "question": "Does it work?",
        "options": [
            {"answer": "Yes", "next": {"type": "conclusion", "text": answer_text}},
            {"answer": "No", "next": {"type": "escalate", "text": "1. See a technician."}},
        ],
    }


def _guide(title: str, category: str = "PSU", keywords=None) -> dict:
    return {
        "title": title,
        "category": category,
        "bot_type": "diagnostic",
        "keywords": keywords or ["a phrase"],
        "question_tree": _tree(),
    }


def _seed(client, headers, guides):
    r = client.post("/api/v1/admin/seed/symptoms", json=guides, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_uploaded_guides_get_slugs_and_are_listed(client, clean_db, admin_headers):
    _seed(client, admin_headers, [_guide("No power / PC will not turn on"), _guide("RAM not detected", "RAM")])
    listing = client.get("/api/v1/guides").json()
    assert {g["slug"] for g in listing} == {"no-power-pc-will-not-turn-on", "ram-not-detected"}
    assert set(listing[0]) == {"slug", "title", "category", "bot_type"}


def test_titles_that_slugify_the_same_get_different_slugs(client, clean_db, admin_headers):
    _seed(client, admin_headers, [_guide("RAM: not detected"), _guide("RAM not detected!!")])
    assert sorted(g["slug"] for g in client.get("/api/v1/guides").json()) == [
        "ram-not-detected",
        "ram-not-detected-2",
    ]


def test_guide_detail_has_the_whole_tree_keywords_and_related(client, clean_db, admin_headers):
    _seed(
        client,
        admin_headers,
        [
            _guide("PSU overheating", "PSU", ["psu hot", "power supply hot"]),
            _guide("Loud coil whine from PSU", "PSU"),
            _guide("RAM not detected", "RAM"),
        ],
    )
    body = client.get("/api/v1/guides/psu-overheating").json()
    assert body["title"] == "PSU overheating"
    assert body["keywords"] == ["psu hot", "power supply hot"]
    assert body["question_tree"]["options"][0]["next"]["type"] == "conclusion"
    # related = other guides in the same category, never itself or other categories
    assert [r["slug"] for r in body["related"]] == ["loud-coil-whine-from-psu"]


def test_unknown_slug_is_404(client, clean_db):
    assert client.get("/api/v1/guides/does-not-exist").status_code == 404


def test_guide_without_a_slug_is_not_listed_until_backfilled(client, clean_db):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO symptom (id, title, category, bot_type) VALUES (gen_random_uuid(), 'Old guide', 'PSU', 'diagnostic')"))
    assert client.get("/api/v1/guides").json() == []
    with SessionLocal() as db:
        assert assign_missing_slugs(db) == 1
        assert assign_missing_slugs(db) == 0  # a second run changes nothing
    assert [g["slug"] for g in client.get("/api/v1/guides").json()] == ["old-guide"]


def test_upload_skips_duplicate_titles(client, clean_db, admin_headers):
    first = _seed(client, admin_headers, [_guide("RAM not detected"), _guide("ram NOT detected ")])
    assert first == {"created": 1, "skipped": ["ram NOT detected "]}
    second = _seed(client, admin_headers, [_guide("RAM not detected"), _guide("Another")])
    assert second == {"created": 1, "skipped": ["RAM not detected"]}
    assert len(client.get("/api/v1/guides").json()) == 2


def test_chat_still_opens_a_guide_by_title(client, clean_db, admin_headers):
    _seed(client, admin_headers, [_guide("RAM not detected", "RAM")])
    r = client.post("/api/v1/chat/symptom-selection", json={"title": "RAM not detected"})
    assert r.status_code == 200 and r.json()["kind"] == "question"