"""
Build tester_sheet.html: the page testers fill in.

Run from backend/:   python scripts/heldout/make_sheet.py

It is ONE file that works offline: send it to a tester, they open it in any browser (phone
included), read each scenario, type what they would write to a chatbot, and send the CSV
back. Nothing is uploaded anywhere. It holds only the scenario texts; the answer key
(which guide each scenario is for) stays in scenarios.json and is never put in the page.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hardware Hub: help us test</title>
<style>
  :root { color-scheme: light dark; --bg:#f8fafc; --card:#fff; --line:#e2e8f0; --ink:#0f172a; --mute:#64748b; --brand:#0284c7; }
  @media (prefers-color-scheme: dark) { :root { --bg:#0b1220; --card:#111a2e; --line:#223049; --ink:#e5edf9; --mute:#93a4bf; --brand:#38bdf8; } }
  * { box-sizing: border-box; }
  body { margin:0; font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif; background:var(--bg); color:var(--ink); }
  main { max-width:680px; margin:0 auto; padding:20px 16px 120px; }
  h1 { font-size:1.4rem; margin:0 0 4px; } p { margin:8px 0; } .mute { color:var(--mute); font-size:.9rem; }
  .box { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px 16px; margin:14px 0; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px 16px; margin:12px 0; }
  .card .n { font-size:.75rem; color:var(--mute); letter-spacing:.04em; text-transform:uppercase; }
  input, textarea { width:100%; font:inherit; padding:10px 12px; border:1px solid var(--line); border-radius:10px; background:transparent; color:inherit; }
  label { display:block; font-size:.85rem; color:var(--mute); margin:10px 0 4px; }
  .row { display:flex; flex-wrap:wrap; gap:10px; } .row > div { flex:1 1 120px; } .row > div.wide { flex-basis:100%; }
  button { font:inherit; padding:10px 14px; border-radius:10px; border:1px solid var(--brand); background:var(--brand); color:#fff; cursor:pointer; }
  button.ghost { background:transparent; color:var(--brand); }
  .bar { position:fixed; left:0; right:0; bottom:0; background:var(--card); border-top:1px solid var(--line); padding:10px 16px; }
  .bar .in { max-width:680px; margin:0 auto; display:flex; gap:10px; align-items:center; }
  .bar .count { flex:1; font-size:.9rem; color:var(--mute); }
  #msg { color:var(--brand); font-size:.9rem; min-height:1.2em; }
</style></head><body><main>
<h1>Help us test a PC troubleshooting chatbot</h1>
<p class="mute">Takes about 10 minutes. Nothing you type here is uploaded: it stays on your device until you send the file yourself. Please do not type your name, phone number or email.</p>

<div class="box">
  <p><b>What to do</b></p>
  <p>You will see short situations. For each one, <b>type what you would write to a chatbot to get help</b>, the way you would normally type it, short or long.</p>
  <p><b>Please do not copy the situation text.</b> Put it in your own words, as if it were your own problem. There are no right or wrong answers, and we are testing the chatbot, not you.</p>
  <p class="mute">If a situation is not about computers, just type a question the way you would ask it.</p>
</div>

<div class="box">
  <div class="row">
    <div class="wide"><label for="who">Your tester nickname or number (not your real name)</label><input id="who" placeholder="for example T1" maxlength="20"></div>
    <div><label for="t">I am tester number</label><input id="t" type="number" min="1" value="1"></div>
    <div><label for="of">out of</label><input id="of" type="number" min="1" value="1"></div>
  </div>
  <p class="mute">If you were told "tester 2 of 4", enter 2 and 4. If you were not told anything, leave 1 and 1 and answer them all.</p>
</div>

<div id="list"></div>
<div id="msg" role="status"></div>
</main>
<div class="bar"><div class="in">
  <span class="count" id="count"></span>
  <button class="ghost" id="copy">Copy answers</button>
  <button id="dl">Download file</button>
</div></div>
<script>
const SCENARIOS = __SCENARIOS__;
const $ = (id) => document.getElementById(id);
const answers = {};            // scenario id -> typed text (kept in memory only)

function mine() {
  const of = Math.max(1, parseInt($("of").value || "1", 10));
  const t = Math.min(of, Math.max(1, parseInt($("t").value || "1", 10)));
  return SCENARIOS.filter((s, i) => i % of === t - 1);
}
function seeded(n) { let s = n * 9301 + 49297; return () => (s = (s * 9301 + 49297) % 233280) / 233280; }
function render() {
  const t = parseInt($("t").value || "1", 10), rand = seeded(t), list = mine().slice();
  for (let i = list.length - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [list[i], list[j]] = [list[j], list[i]]; }
  $("list").innerHTML = "";
  list.forEach((s, k) => {
    const d = document.createElement("div"); d.className = "card";
    d.innerHTML = '<div class="n">Situation ' + (k + 1) + ' of ' + list.length + '</div><p></p><label>What would you type to the chatbot?</label><textarea rows="2"></textarea>';
    d.querySelector("p").textContent = s.text;
    const ta = d.querySelector("textarea"); ta.value = answers[s.id] || "";
    ta.addEventListener("input", () => { answers[s.id] = ta.value; count(); });
    $("list").appendChild(d);
  });
  count();
}
function count() { const m = mine(); const done = m.filter((s) => (answers[s.id] || "").trim()).length; $("count").textContent = done + " of " + m.length + " answered"; }
function q(v) { return '"' + String(v).replace(/"/g, '""') + '"'; }
function csv() {
  const who = ($("who").value || "").trim().replace(/[\\r\\n,]+/g, " ") || "tester";
  const rows = mine().filter((s) => (answers[s.id] || "").trim()).map((s) => [who, s.id, (answers[s.id] || "").replace(/\\s+/g, " ").trim()].map(q).join(","));
  return ["tester,scenario_id,query"].concat(rows).join("\\n") + "\\n";
}
$("dl").onclick = () => {
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([csv()], { type: "text/csv" }));
  a.download = "answers_" + (($("who").value || "tester").trim().replace(/[^\\w-]+/g, "") || "tester") + ".csv"; a.click();
  $("msg").textContent = "File saved. Please send it back to whoever gave you this page.";
};
$("copy").onclick = async () => {
  try { await navigator.clipboard.writeText(csv()); $("msg").textContent = "Copied. Paste it into a message to send it back."; }
  catch { $("msg").textContent = "Copying was blocked. Use Download file instead."; }
};
$("t").addEventListener("change", render); $("of").addEventListener("change", render);
render();
</script></body></html>
"""


def build() -> str:
    scenarios = json.loads((HERE / "scenarios.json").read_text(encoding="utf-8"))
    public = [{"id": s["id"], "text": s["text"]} for s in scenarios]  # never the expected guide
    return PAGE.replace("__SCENARIOS__", json.dumps(public, ensure_ascii=False))


if __name__ == "__main__":
    out = HERE / "tester_sheet.html"
    out.write_text(build(), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")