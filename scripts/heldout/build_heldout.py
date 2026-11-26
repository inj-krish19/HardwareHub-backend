"""
Turn the CSV files testers send back into a query file for scripts/match_eval.py.

Run from backend/:
    python scripts/heldout/build_heldout.py answers_T1.csv answers_T2.csv -o heldout_queries.json
    python scripts/heldout/build_heldout.py --scenario-texts -o stress_queries.json   (no CSV: a stress test)

Each CSV has the columns  tester,scenario_id,query  (the tester sheet writes them).
The expected guide for each query comes from scenarios.json, never from the tester.

What it refuses, and says so in its summary:
  * a scenario id that is not in scenarios.json
  * an empty or very short answer
  * an answer that looks like personal data (an email address or a long number)
  * an answer that is the scenario text copied over, not the tester's own words
Two answers from the same tester to the same scenario: the later one wins.
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from app.core.query_log import clean_query  # noqa: E402  (the same privacy rules the chat uses)
from app.rule_engine.matcher import tokens  # noqa: E402

COPIED_AT = 0.7  # share of shared words above which an answer counts as a copy of the card


def words(text: str) -> set[str]:
    return tokens(text)


def looks_copied(query: str, scenario_text: str) -> bool:
    q, s = words(query), words(scenario_text)
    if not q or not s:
        return False
    return len(q & s) / len(q | s) >= COPIED_AT


def build(scenarios: list[dict], csv_paths: list[Path]) -> tuple[list[dict], Counter, Counter]:
    by_id = {s["id"]: s for s in scenarios}
    kept: dict[tuple[str, str], dict] = {}
    skipped: Counter = Counter()
    per_tester: Counter = Counter()
    for path in csv_paths:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if {"tester", "scenario_id", "query"} - set(reader.fieldnames or []):
                raise SystemExit(f"{path}: expected the columns tester,scenario_id,query")
            for row in reader:
                scenario = by_id.get((row["scenario_id"] or "").strip())
                if scenario is None:
                    skipped["unknown scenario id"] += 1
                    continue
                query = (row["query"] or "").strip()
                if not query:
                    skipped["empty answer"] += 1
                    continue
                cleaned = clean_query(query)
                if cleaned is None:
                    skipped["too short or looks like personal data"] += 1
                    continue
                if looks_copied(cleaned[0], scenario["text"]):
                    skipped["copied the scenario text"] += 1
                    continue
                tester = (row["tester"] or "tester").strip() or "tester"
                kept[(tester, scenario["id"])] = {
                    "query": cleaned[0], "expected": scenario["expected"], "scenario": scenario["id"], "tester": tester,
                }
    for item in kept.values():
        per_tester[item["tester"]] += 1
    items = sorted(kept.values(), key=lambda i: (i["scenario"], i["tester"]))
    return items, skipped, per_tester


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_files", nargs="*", type=Path)
    parser.add_argument(
        "--scenario-texts", action="store_true",
        help="no CSV needed: write the scenario texts themselves as queries. A stress test with formal wording, "
             "not a held-out result (real chat messages are shorter and blunter).",
    )
    parser.add_argument("-o", "--output", type=Path, default=Path("heldout_queries.json"))
    parser.add_argument("--scenarios", type=Path, default=HERE / "scenarios.json")
    args = parser.parse_args()

    scenarios = json.loads(args.scenarios.read_text(encoding="utf-8"))
    if args.scenario_texts:
        items = [{"query": s["text"], "expected": s["expected"], "scenario": s["id"], "tester": "stress-test"} for s in scenarios]
        args.output.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {args.output} ({len(items)} scenario texts as queries). This is a stress test, not a held-out result.")
        return
    if not args.csv_files:
        parser.error("give at least one CSV file, or use --scenario-texts")
    items, skipped, per_tester = build(scenarios, args.csv_files)
    args.output.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")

    covered = {i["scenario"] for i in items}
    print(f"kept {len(items)} queries from {len(per_tester)} tester(s): " + ", ".join(f"{t}={n}" for t, n in sorted(per_tester.items())))
    print(f"scenarios with at least one query: {len(covered)} of {len(scenarios)}")
    never = [s["id"] for s in scenarios if s["id"] not in covered]
    if never:
        print("scenarios nobody answered:", ", ".join(never))
    for reason, n in skipped.items():
        print(f"left out ({reason}): {n}")
    print(f"wrote {args.output}")
    print(f"next:  python scripts/match_eval.py app/data/seed {args.output}")


if __name__ == "__main__":
    main()