"""
Run with: python -m app.db.seed
Run app.db.init_db FIRST so the tables exist.

Loads every *_symptoms.json file in app/data/seed/ — drop in ram_symptoms.json,
storage_symptoms.json, psu_symptoms.json, etc. (generated via the seed prompt
template) and they're all picked up automatically, no code change needed.

Also loads app/data/seed/budget_profiles.json for the Budget/Build Advisor
bot — a flat list of {task_type, budget_min, budget_max, component_set}.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.db.session import SessionLocal
from app.models.rules import DiagnosisRule, RecommendationRule, Symptom, UseBudgetProfile

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"


def seed_symptoms() -> None:
    db = SessionLocal()
    total = 0
    try:
        for path in sorted(SEED_DIR.glob("*_symptoms.json")):
            data = json.loads(path.read_text())
            for entry in data:
                keywords = entry.get("keywords")
                symptom = Symptom(
                    title=entry["title"],
                    category=entry["category"],
                    keywords=", ".join(keywords) if keywords else None,
                )
                db.add(symptom)
                db.flush()
                db.add(DiagnosisRule(symptom_id=symptom.id, question_tree=entry["question_tree"]))
                total += 1
            print(f"  {path.name}: {len(data)} symptoms")
        db.commit()
        print(f"Seeded {total} symptoms + diagnosis rules total.")
    finally:
        db.close()


def seed_budget_profiles() -> None:
    path = SEED_DIR / "budget_profiles.json"
    if not path.exists():
        print("  budget_profiles.json not found, skipping.")
        return
    db = SessionLocal()
    total = 0
    try:
        data = json.loads(path.read_text())
        for entry in data:
            profile = UseBudgetProfile(
                task_type=entry["task_type"],
                budget_min=entry["budget_min"],
                budget_max=entry["budget_max"],
            )
            db.add(profile)
            db.flush()
            db.add(RecommendationRule(profile_id=profile.id, component_set=entry["component_set"]))
            total += 1
        db.commit()
        print(f"  budget_profiles.json: {total} budget profiles")
    finally:
        db.close()


if __name__ == "__main__":
    seed_symptoms()
    seed_budget_profiles()