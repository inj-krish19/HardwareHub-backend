"""
Run with: python -m app.db.seed
Run app.db.init_db FIRST so the tables exist.

Loads every *_symptoms.json file in app/data/seed/ — drop in ram_symptoms.json,
storage_symptoms.json, psu_symptoms.json, etc. (generated via the seed prompt
template) and they're all picked up automatically, no code change needed.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.core.slugs import slugify, unique_slug
from app.db.backfill_slugs import taken_slugs
from app.db.session import SessionLocal
from app.models.rules import DiagnosisRule, Symptom

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"


def seed_symptoms() -> None:
    db = SessionLocal()
    total = 0
    skipped = 0
    try:
        # Guide titles must be unique (case-insensitive): the chat looks a guide up
        # by title. Anything already in the database, or repeated across the
        # files, is skipped, so running this twice no longer duplicates guides.
        taken = {t.strip().lower() for t in db.execute(select(Symptom.title)).scalars()}
        slugs = taken_slugs(db)
        for path in sorted(SEED_DIR.glob("*_symptoms.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            added = 0
            for entry in data:
                key = entry["title"].strip().lower()
                if key in taken:
                    skipped += 1
                    print(f"  skipped duplicate title: {entry['title']!r}")
                    continue
                taken.add(key)
                keywords = entry.get("keywords")
                symptom = Symptom(
                    title=entry["title"].strip(),
                    slug=unique_slug(slugify(entry["title"]), slugs),
                    category=entry["category"],
                    keywords=", ".join(keywords) if keywords else None,
                    bot_type=entry.get("bot_type", "diagnostic"),
                )
                db.add(symptom)
                db.flush()
                db.add(DiagnosisRule(symptom_id=symptom.id, question_tree=entry["question_tree"]))
                total += 1
                added += 1
            print(f"  {path.name}: {added} added")
        db.commit()
        print(f"Seeded {total} symptoms + diagnosis rules total ({skipped} duplicate titles skipped).")
    finally:
        db.close()


if __name__ == "__main__":
    seed_symptoms()