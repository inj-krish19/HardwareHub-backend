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
misses, this set stops being an honest test. Collect fresh queries from testers
(see docs/HELDOUT_EVALUATION.md and scripts/heldout/).

Every percentage is followed by a 95% interval (Wilson). With few queries the interval
is wide, and it is the interval, not the single number, that you can honestly claim.
"""
import glob
import json
import math
import os
import sys
from collections import defaultdict
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.rule_engine import router  # noqa: E402
from app.rule_engine.matcher import rank_matches  # noqa: E402


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for a proportion (Wilson score). (0, 1) when there is no data."""
    if total == 0:
        return 0.0, 1.0
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def fmt(successes: int, total: int) -> str:
    lo, hi = wilson(successes, total)
    pct = f"{successes / total:.0%}" if total else "n/a"
    return f"{successes}/{total} = {pct}  (95% interval {lo:.0%} to {hi:.0%})"


def main(guides_dir: str, queries_path: str) -> None:
    guides = []
    for path in sorted(glob.glob(os.path.join(guides_dir, "*_symptoms.json"))):
        for g in json.load(open(path, encoding="utf-8")):
            guides.append(NS(title=g["title"], keywords=", ".join(g.get("keywords", [])), bot_type=g.get("bot_type", "diagnostic")))
    titles = {g.title for g in guides}
    queries = json.load(open(queries_path, encoding="utf-8"))

    bot_of = {g.title: g.bot_type for g in guides}
    top1 = top3 = used = skipped = 0
    off_ok = off_total = 0
    misses = []
    false_matches = []
    per_bot = defaultdict(lambda: [0, 0, 0])  # bot -> [queries, top-1 right, top-3 right]
    for item in queries:
        q, expected = item["query"], item["expected"]
        intent = router.route(q)
        bot = router.INTENT_TO_BOT.get(intent) if intent else None
        got = [g.title for g in rank_matches(q, guides, bot, limit=3)]
        if expected is None:
            off_total += 1
            off_ok += not got
            if got:
                false_matches.append((q, got))
            continue
        if expected not in titles:
            skipped += 1
            continue
        used += 1
        top1 += got[:1] == [expected]
        top3 += expected in got
        bucket = per_bot[bot_of[expected]]
        bucket[0] += 1
        bucket[1] += got[:1] == [expected]
        bucket[2] += expected in got
        if got[:1] != [expected]:
            misses.append((q, expected, got))

    print(f"guides loaded: {len(guides)}")
    print(f"queries scored: {used} (skipped {skipped} whose guide isn't in the folder)")
    if used:
        print(f"top-1 accuracy: {fmt(top1, used)}")
        print(f"top-3 accuracy: {fmt(top3, used)}")
        if len(per_bot) > 1:
            print("by kind of question (queries, top-1, top-3):")
            for bot, (n, t1, t3) in sorted(per_bot.items()):
                print(f"  {bot:14} {n:3}   {t1 / n:4.0%}   {t3 / n:4.0%}")
    if off_total:
        print(f"off-topic queries correctly ignored: {fmt(off_ok, off_total)}")
        for q, got in false_matches:
            print(f"  [FALSE MATCH] off-topic {q!r} matched {got}")
    for q, expected, got in misses:
        status = "in top 3" if expected in got else "MISSED"
        print(f"  [{status}] {q!r} -> wanted {expected!r}, got {got}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])