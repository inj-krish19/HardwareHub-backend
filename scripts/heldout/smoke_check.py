"""
Check a running deployment. READ-ONLY: it only fetches pages and asks the chat questions that
match a real guide, so it changes nothing and adds nothing to the missed-query log.

Run from backend/ (needs no packages beyond Python):
    python scripts/smoke_check.py --api https://your-backend.example.com --site https://yourapp.vercel.app

It checks the things that usually go wrong on deploy day: the API is up and the database has the
guides, every guide has a URL slug, the browser from your site is allowed through CORS, the admin
routes are locked, the chat finds a guide and can build a technician summary, and the website,
its guide pages, sitemap and robots.txt respond. Exit code 0 means every check passed.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def fetch(url: str, method: str = "GET", body: dict | None = None, headers: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.status, dict(res.headers), res.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers), err.read().decode("utf-8", "replace")
    except Exception as err:  # network problem, DNS, timeout, TLS
        return 0, {}, str(err)


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((PASS if ok else FAIL, name, detail))
    print(f"  [{PASS if ok else FAIL}] {name}" + (f"  ({detail})" if detail and not ok else ""))
    return ok


def run(api: str, site: str | None) -> bool:
    api = api.rstrip("/")
    print(f"Backend: {api}")
    status, _, body = fetch(f"{api}/health")
    if not check("API answers /health", status == 200 and '"ok"' in body, f"status {status}: {body[:100]}"):
        print("  The API is not reachable, so the rest cannot be checked.")
        return False

    status, _, body = fetch(f"{api}/api/v1/guides")
    guides = json.loads(body) if status == 200 else []
    check("the database has guides", len(guides) > 0, f"/guides returned status {status} and {len(guides)} guides")
    check("every guide has a URL slug", bool(guides) and all(g.get("slug") for g in guides), "run python -m app.db.sync_schema on the production database")
    titles = [g["title"] for g in guides]
    check("guide titles are unique (ignoring case)", len({t.strip().lower() for t in titles}) == len(titles), "duplicate guide titles in the database")
    if guides:
        status, _, detail = fetch(f"{api}/api/v1/guides/{guides[0]['slug']}")
        tree = json.loads(detail).get("question_tree") if status == 200 else None
        check("one guide opens with its decision tree", status == 200 and isinstance(tree, dict), f"status {status}")

    status, _, body = fetch(f"{api}/api/v1/products")
    check("the catalog answers", status == 200, f"status {status}")
    if status == 200:
        products = json.loads(body)
        print(f"        ({len(products)} products, {sum(1 for p in products if p.get('image_url'))} with a photo)")

    # CORS: the browser on your site must be allowed to call the API
    if site:
        origin = site.rstrip("/")
        status, headers, _ = fetch(f"{api}/api/v1/guides", headers={"Origin": origin})
        allowed = {k.lower(): v for k, v in headers.items()}.get("access-control-allow-origin")
        check("CORS allows your website", allowed in (origin, "*"), f"allow-origin was {allowed!r}; add {origin} to CORS_ORIGIN on the backend")

    status, _, _ = fetch(f"{api}/api/v1/admin/ping")
    check("admin routes refuse requests without a login", status in (401, 422), f"status {status}")
    status, _, _ = fetch(f"{api}/api/v1/admin/ping", headers={"X-Admin-Id": "nobody", "X-Admin-Secret": "wrong-wrong-wrong-wrong"})
    check("admin routes refuse a wrong login", status == 401, f"status {status}")

    # The chat, with a message that matches a real guide (so nothing is added to the missed-query log).
    if guides:
        status, _, body = fetch(f"{api}/api/v1/chat/start", "POST", {"query": guides[0]["title"]})
        step = json.loads(body) if status == 200 else {}
        check("the chat suggests a guide for a known problem", status == 200 and step.get("kind") == "suggest", f"status {status}, kind {step.get('kind')}")
        status, _, body = fetch(f"{api}/api/v1/chat/symptom-selection", "POST", {"title": guides[0]["title"]})
        first = json.loads(body) if status == 200 else {}
        check("a guide opens in the chat", status == 200 and first.get("kind") == "question", f"status {status}")

        escalation = find_escalation(api, guides)
        if escalation:
            symptom_id, path = escalation
            status, _, body = fetch(f"{api}/api/v1/chat/report", "POST", {"symptom_id": symptom_id, "answer_path": path})
            report = json.loads(body) if status == 200 else {}
            check("the technician summary builds", status == 200 and "PC PROBLEM SUMMARY" in report.get("text", ""), f"status {status}")
        else:
            print("  [skip] no 'needs a professional' path found to test the technician summary")

    if site:
        print(f"Website: {site}")
        base = site.rstrip("/")
        for path, needle in (("/", "Hardware Hub"), ("/guides", "guides"), ("/products", "Catalog"), ("/compare", "Compare"), ("/admin/login", "Admin")):
            status, _, body = fetch(base + path)
            check(f"{path} loads", status == 200 and needle.lower() in body.lower(), f"status {status}")
        if guides:
            status, _, body = fetch(f"{base}/guides/{guides[0]['slug']}")
            check("a guide page loads and shows the guide", status == 200 and guides[0]["title"].split(" ")[0] in body, f"status {status}")
            status, _, _ = fetch(f"{base}/guides/this-guide-does-not-exist")
            check("an unknown guide gives a 404", status == 404, f"status {status}")
        status, _, body = fetch(f"{base}/sitemap.xml")
        urls = re.findall(r"<loc>(.*?)</loc>", body)
        check("sitemap.xml lists the pages", status == 200 and len(urls) > len(guides), f"{len(urls)} urls; set NEXT_PUBLIC_SITE_URL on the frontend")
        check("the sitemap uses your real address, not localhost", bool(urls) and not any("localhost" in u for u in urls), "NEXT_PUBLIC_SITE_URL points at localhost")
        status, _, body = fetch(f"{base}/robots.txt")
        check("robots.txt blocks /admin", status == 200 and "Disallow: /admin" in body, f"status {status}")
    return all(r[0] == PASS for r in results)


def find_escalation(api: str, guides: list[dict]):
    """Find one answer path that ends in 'needs a professional' (read-only: it only reads trees)."""
    def walk(node, path):
        if node.get("type") == "escalate":
            return path
        if node.get("type") == "conclusion":
            return None
        for option in node.get("options", []):
            found = walk(option["next"], path + [option["answer"]])
            if found is not None:
                return found
        return None

    for guide in guides:
        status, _, body = fetch(f"{api}/api/v1/guides/{guide['slug']}")
        if status != 200:
            continue
        path = walk(json.loads(body)["question_tree"], [])
        if path is None:
            continue
        status, _, body = fetch(f"{api}/api/v1/chat/symptom-selection", "POST", {"title": guide["title"]})
        if status == 200 and json.loads(body).get("symptom_id"):
            return json.loads(body)["symptom_id"], path
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", required=True, help="the backend address")
    parser.add_argument("--site", help="the website address (also checks CORS, the pages, sitemap and robots)")
    args = parser.parse_args()
    ok = run(args.api, args.site)
    failed = [name for status, name, _ in results if status == FAIL]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed." + (f" Failed: {'; '.join(failed)}" if failed else ""))
    sys.exit(0 if ok else 1)