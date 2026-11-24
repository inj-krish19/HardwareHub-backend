"""Guide API tests against a real PostgreSQL. Safe on a database with real data:
see conftest.py (every change is rolled back; each test only looks at its own rows)."""
from sqlalchemy import text

from app.db.backfill_slugs import assign_missing_slugs


def _tree() -> dict:
    return {
        "id": "q1",
        "question": "Does it work?",
        "options": [
            {"answer": "Yes", "next": {"type": "conclusion", "text": "1. Do the thing."}},
            {"answer": "No", "next": {"type": "escalate", "text": "1. See a technician."}},
        ],
    }


def _guide(title: str, category: str, keywords=None) -> dict:
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


def _mine(client, tag):
    return [g for g in client.get("/api/v1/guides").json() if tag in g["slug"]]


def test_uploaded_guides_get_slugs_and_are_listed(client, db, admin_headers, tag):
    _seed(client, admin_headers, [_guide(f"{tag} No power / PC will not turn on", f"Cat {tag}"), _guide(f"{tag} RAM not detected", f"Cat {tag}")])
    mine = _mine(client, tag)
    assert {g["slug"] for g in mine} == {f"{tag}-no-power-pc-will-not-turn-on", f"{tag}-ram-not-detected"}
    assert set(mine[0]) == {"slug", "title", "category", "bot_type"}


def test_titles_that_slugify_the_same_get_different_slugs(client, db, admin_headers, tag):
    _seed(client, admin_headers, [_guide(f"{tag} RAM: not detected", f"Cat {tag}"), _guide(f"{tag} RAM not detected!!", f"Cat {tag}")])
    assert sorted(g["slug"] for g in _mine(client, tag)) == [f"{tag}-ram-not-detected", f"{tag}-ram-not-detected-2"]


def test_guide_detail_has_the_whole_tree_keywords_and_related(client, db, admin_headers, tag):
    _seed(
        client,
        admin_headers,
        [
            _guide(f"{tag} PSU overheating", f"PSU {tag}", ["psu hot", "power supply hot"]),
            _guide(f"{tag} Loud coil whine from PSU", f"PSU {tag}"),
            _guide(f"{tag} RAM not detected", f"RAM {tag}"),
        ],
    )
    body = client.get(f"/api/v1/guides/{tag}-psu-overheating").json()
    assert body["title"] == f"{tag} PSU overheating"
    assert body["keywords"] == ["psu hot", "power supply hot"]
    assert body["question_tree"]["options"][0]["next"]["type"] == "conclusion"
    # related = other guides in the same category, never itself or another category
    assert [r["slug"] for r in body["related"]] == [f"{tag}-loud-coil-whine-from-psu"]


def test_unknown_slug_is_404(client, db, tag):
    assert client.get(f"/api/v1/guides/does-not-exist-{tag}").status_code == 404


def test_guide_without_a_slug_is_not_listed_until_backfilled(client, db, tag):
    db.execute(
        text("INSERT INTO symptom (id, title, category, bot_type) VALUES (gen_random_uuid(), :t, :c, 'diagnostic')"),
        {"t": f"{tag} Old guide", "c": f"Cat {tag}"},
    )
    assert _mine(client, tag) == []
    assert assign_missing_slugs(db) >= 1
    assert assign_missing_slugs(db) == 0  # a second run changes nothing
    assert [g["slug"] for g in _mine(client, tag)] == [f"{tag}-old-guide"]


def test_upload_skips_duplicate_titles(client, db, admin_headers, tag):
    first = _seed(client, admin_headers, [_guide(f"{tag} RAM not detected", f"Cat {tag}"), _guide(f"{tag.upper()} ram NOT detected ", f"Cat {tag}")])
    assert first == {"created": 1, "skipped": [f"{tag.upper()} ram NOT detected "]}
    second = _seed(client, admin_headers, [_guide(f"{tag} RAM not detected", f"Cat {tag}"), _guide(f"{tag} Another", f"Cat {tag}")])
    assert second == {"created": 1, "skipped": [f"{tag} RAM not detected"]}
    assert len(_mine(client, tag)) == 2


def test_chat_still_opens_a_guide_by_title(client, db, admin_headers, tag):
    _seed(client, admin_headers, [_guide(f"{tag} RAM not detected", f"Cat {tag}")])
    r = client.post("/api/v1/chat/symptom-selection", json={"title": f"{tag} RAM not detected"})
    assert r.status_code == 200 and r.json()["kind"] == "question"