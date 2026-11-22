"""
Measure how well query -> guide matching works.

Run from backend/:
    python scripts/match_eval.py PATH_TO_GUIDE_JSON_FOLDER match_eval_queries.json

  - the folder holds your *_symptoms.json files (the same ones you upload)
  - the queries file is a list of {"query": "...", "expected": "<guide title>" or null}
    ("expected": null means the query is off-topic and should match nothing)

Prints top-1 accuracy (the right guide is first) and top-3 accuracy (it is among
the three suggestions the chat shows), then lists every miss. Queries whose
expected guide is not in the folder are skipped and counted separately.

Use a SEPARATE set of queries for any final claim: once you tune keywords to the
misses, this set stops being an honest test. Collect fresh queries from testers.
"""
import glob
import json
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.rule_engine import router  # noqa: E402
from app.rule_engine.matcher import rank_matches  # noqa: E402


def main(guides_dir: str, queries_path: str) -> None:
    guides = []
    for path in sorted(glob.glob(os.path.join(guides_dir, "*_symptoms.json"))):
        for g in json.load(open(path, encoding="utf-8")):
            guides.append(NS(title=g["title"], keywords=", ".join(g.get("keywords", [])), bot_type=g.get("bot_type", "diagnostic")))
    titles = {g.title for g in guides}
    queries = json.load(open(queries_path, encoding="utf-8"))

    top1 = top3 = used = skipped = 0
    off_ok = off_total = 0
    misses = []
    for item in queries:
        q, expected = item["query"], item["expected"]
        intent = router.route(q)
        bot = router.INTENT_TO_BOT.get(intent) if intent else None
        got = [g.title for g in rank_matches(q, guides, bot, limit=3)]
        if expected is None:
            off_total += 1
            off_ok += not got
            continue
        if expected not in titles:
            skipped += 1
            continue
        used += 1
        top1 += got[:1] == [expected]
        top3 += expected in got
        if got[:1] != [expected]:
            misses.append((q, expected, got))

    print(f"guides loaded: {len(guides)}")
    print(f"queries scored: {used} (skipped {skipped} whose guide isn't in the folder)")
    if used:
        print(f"top-1 accuracy: {top1}/{used} = {top1 / used:.0%}")
        print(f"top-3 accuracy: {top3}/{used} = {top3 / used:.0%}")
    if off_total:
        print(f"off-topic queries correctly ignored: {off_ok}/{off_total}")
    for q, expected, got in misses:
        status = "in top 3" if expected in got else "MISSED"
        print(f"  [{status}] {q!r} -> wanted {expected!r}, got {got}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])