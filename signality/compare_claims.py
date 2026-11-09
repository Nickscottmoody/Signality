"""Haiku vs. Sonnet vs. Opus on hard claim decisions (Stage 2b, task #9).

    ./.venv/bin/python -m signality.compare_claims          # find cases, run all models, write report

A "case" is a real claim plus a newer article that might settle it. Each model gets
exactly the same prompt as Signality's live claim decision (resolution.DECIDE_*),
so the comparison shows what each would do in production, and what it costs.
"""
import html
import json
from datetime import datetime

from . import ai, claims, db, resolution
from .dedup import key_words, related
from .settings import ROOT, load_config

MODELS = [("Haiku", "bulk"), ("Sonnet", "high_stakes"), ("Opus", "deep")]
CASES_FILE = ROOT / "data" / "reports" / "claim-cases.json"


def brief_before(conn, claim_id, before_event_id=None):
    """The claim as it looked BEFORE a given event (so a resolved claim can be re-judged fairly)."""
    c = conn.execute(
        "SELECT c.*, a.published_at AS source_published FROM claims c JOIN articles a ON a.id = c.article_id"
        " WHERE c.id = ?", (claim_id,)).fetchone()
    events = [e for e in claims.history(conn, claim_id) if before_event_id is None or e["id"] < before_event_id]
    last = events[-1]
    lines = [f"Claim {c['id']}: {c['text']}",
             f"  claimed by: {c['claimant']}",
             f"  label: {claims.LABELS[last['label']]} | status: {last['status']} | made: {c['source_published'][:10]}"
             + (f" | due: {c['due_date']}" if c["due_date"] else "")]
    lines += [f"  history {e['at'][:10]}: {e['event']} -> {e['label']}/{e['status']}: {e['reason']}" for e in events]
    return "\n".join(lines)


def article(conn, article_id):
    return conn.execute("SELECT a.*, s.name AS source_name, s.type AS source_type FROM articles a"
                        " JOIN sources s ON s.id = a.source_id WHERE a.id = ?", (article_id,)).fetchone()


def find_cases(conn, cfg, n=10, per_saga=4, max_scans=150):
    """Real (claim, article) pairs where Haiku's first pass thinks the claim may have changed.

    Duplicate claim texts are skipped, and no single saga may supply more than per_saga cases,
    so the set tests different kinds of decisions.
    """
    first_id = conn.execute("SELECT MIN(id) - 1 FROM articles WHERE fetched_at >= strftime('%Y-%m-%dT%H:%M:%S',"
                            " 'now', '-4 days')").fetchone()[0]
    arts = conn.execute("SELECT a.*, s.name AS source_name, s.type AS source_type FROM articles a"
                        " JOIN sources s ON s.id = a.source_id WHERE a.id > ? ORDER BY a.id", (first_id,)).fetchall()
    cases, seen_texts, sagas, scans = [], set(), [], 0

    def saga_count(words):
        return sum(1 for w in sagas if related(words, w))

    for art in arts:
        found = [c for c in resolution.candidates(conn, cfg, art)
                 if c["text"].lower() not in seen_texts and saga_count(key_words(c["text"])) < per_saga]
        if not found:
            continue
        scans += 1
        if scans > max_scans or len(cases) >= n:
            break
        prompt = (f"NEW ITEM\n{resolution.evidence_text(conn, art)}\n\nOPEN CLAIMS\n"
                  + "\n\n".join(resolution.claim_brief(conn, c) for c in found))
        data, _ = ai.ask_json(conn, cfg, task="claim_case_search", role="bulk", system=resolution.MATCH_SYSTEM,
                              prompt=prompt, schema=resolution.MATCH_SCHEMA)
        by_id = {c["id"]: c for c in found}
        for a in data["assessments"]:
            c = by_id.get(resolution.claim_number(a["claim_id"]))
            if c is None or a["relation"] not in resolution.SETTLING | {"supports"}:
                continue
            words = key_words(c["text"])
            if c["text"].lower() in seen_texts or saga_count(words) >= per_saga:
                continue
            seen_texts.add(c["text"].lower())
            sagas.append(words)
            cases.append({"claim_id": c["id"], "article_id": art["id"], "first_pass": a["relation"],
                          "first_pass_reason": a["reason"], "before_event_id": None})
    return cases[:n], scans


def materialize(conn, case):
    """Freeze a real case's prompt text (claim as it looked then + the evidence) into the case."""
    if "brief" not in case:
        art = article(conn, case["article_id"])
        cl = conn.execute("SELECT text, claimant FROM claims WHERE id = ?", (case["claim_id"],)).fetchone()
        case.update(claim_text=cl["text"], claimant=cl["claimant"], synthetic=False,
                    brief=brief_before(conn, case["claim_id"], case.get("before_event_id")),
                    evidence=resolution.evidence_text(conn, art),
                    evidence_source=f"{art['source_name']}, {art['published_at'][:10]}")
    return case


def decide(conn, cfg, case, role):
    prompt = (f"CLAIM AND HISTORY\n{case['brief']}\n\nNEW EVIDENCE\n{case['evidence']}\n\n"
              f"First-pass assessment: {case['first_pass']} - {case['first_pass_reason']}")
    data, cost = ai.ask_json(conn, cfg, task=f"claim_compare_{role}", role=role, system=resolution.DECIDE_SYSTEM,
                             prompt=prompt, schema=resolution.DECIDE_SCHEMA)
    return {**data, "cost": cost}


def practice_case(n, claim, claimant, label, made, history, evidence_source, evidence, first_pass, expected,
                  due=""):
    brief = (f"Claim {9000 + n}: {claim}\n  claimed by: {claimant}\n"
             f"  label: {claims.LABELS[label]} | status: open | made: {made}" + (f" | due: {due}" if due else "")
             + f"\n  history {made}: created -> {label}/open: {history}")
    return {"claim_text": claim, "claimant": claimant, "synthetic": True, "expected": expected, "brief": brief,
            "evidence": evidence, "evidence_source": evidence_source, "first_pass": first_pass,
            "first_pass_reason": "practice case"}


PRACTICE = [
    practice_case(1, "Vertex Labs is in advanced talks to be acquired by Microsoft for about $4 billion",
                  "unnamed sources, per The Information", "reported", "2026-11-02",
                  "One outlet so far, citing unnamed sources.", "Reuters, 2026-11-05",
                  "Source: Reuters (type: news)\nPublished: 2026-11-05\nHeadline: Vertex Labs CEO calls Microsoft "
                  "deal report 'false'\nVertex Labs chief executive Dana Ortiz said on X that a report the startup was "
                  "in talks to sell itself to Microsoft was \"false\" and that the company is \"not for sale.\" "
                  "Microsoft declined to comment. The Information said it stands by its reporting.",
                  "contradicts", "disputed"),
    practice_case(2, "Google will lay off 1,200 employees in its cloud AI unit this month",
                  "Bloomberg", "reported", "2026-11-03", "One outlet so far.", "Bloomberg, 2026-11-04",
                  "Source: Bloomberg Technology (type: news)\nPublished: 2026-11-04\nHeadline: Correction: Google cloud "
                  "unit job cuts\nAn earlier version of this story incorrectly said Google would cut 1,200 jobs in its "
                  "cloud AI unit. Google is reorganizing the unit but has not announced layoffs. Bloomberg regrets the error.",
                  "walked_back", "walked_back"),
    practice_case(3, "OpenAI will launch GPT-7 in the European Union by December 31, 2026",
                  "OpenAI", "confirmed", "2026-10-15", "Officially announced by OpenAI; open until it happens.",
                  "OpenAI blog, 2026-11-06",
                  "Source: OpenAI Blog (type: primary)\nPublished: 2026-11-06\nHeadline: Update on GPT-7 availability "
                  "in Europe\nOpenAI said GPT-7 will now reach the EU in the first quarter of 2027, later than planned, "
                  "while it completes reviews required under the EU AI Act. The model is available in the US and UK.",
                  "delayed", "delayed", due="2026-12-31"),
    practice_case(4, "Meta cut about 3,000 jobs in its AI research division",
                  "unnamed sources, per The Information", "reported", "2026-11-01",
                  "One outlet so far, citing unnamed sources.", "Meta newsroom via Reuters, 2026-11-03",
                  "Source: Reuters (type: news)\nPublished: 2026-11-03\nHeadline: Meta confirms AI unit restructuring "
                  "affecting about 600 roles\nMeta said in a statement that a restructuring of its AI research group "
                  "affects about 600 roles, and that some affected employees will be offered other positions. The "
                  "company did not address an earlier report putting the cuts at 3,000.",
                  "contradicts", "disputed"),
    practice_case(5, "Fable 5.2 returns responses 30% faster than Fable 5.1",
                  "Anthropic", "self_reported", "2026-11-08",
                  "Anthropic's own claim about itself; not independently verified.", "Ars Technica, 2026-11-12",
                  "Source: Ars Technica (AI) (type: specialist)\nPublished: 2026-11-12\nHeadline: We tested Fable 5.2: "
                  "it really is faster\nIn Ars Technica's own tests across 500 prompts at three effort levels, Fable 5.2 "
                  "produced responses on average 28% faster than Fable 5.1, close to Anthropic's 30% claim. Independent "
                  "benchmarking firm Artificial Analysis reported a similar 27-31% range.",
                  "confirms", "confirmed"),
    practice_case(6, "Apple will use Google's Gemini to power the new Siri",
                  "unnamed sources, per The Information", "reported", "2026-11-05",
                  "One outlet so far, citing unnamed sources.", "TechCrunch, 2026-11-06",
                  "Source: TechCrunch AI (type: specialist)\nPublished: 2026-11-06\nHeadline: Apple reportedly picks "
                  "Gemini for Siri\nApple will use Google's Gemini models to power a redesigned Siri, The Information "
                  "reported Wednesday, citing people familiar with the matter. The Verge, 9to5Mac and CNBC have also "
                  "covered The Information's report. Apple and Google did not respond to requests for comment.",
                  "supports", "no_change"),
]


def run(conn, cfg, cases, models=MODELS):
    for case in cases:
        materialize(conn, case)
        case.setdefault("results", {})
        for name, role in models:
            if name not in case["results"]:
                try:
                    case["results"][name] = decide(conn, cfg, case, role)
                except ai.AIError as e:
                    case["results"][name] = {"decision": "error", "reason": str(e), "receipt_line": "", "cost": 0}
    CASES_FILE.parent.mkdir(parents=True, exist_ok=True)
    CASES_FILE.write_text(json.dumps(cases, indent=2))
    return cases


CSS = """
:root{--bg:#fbfaf7;--card:#fff;--ink:#1d1d1b;--muted:#6b6a65;--line:#e6e3dc;--warn:#b5651d;--chip:#f2efe8}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--card:#1f1f1c;--ink:#ecebe6;--muted:#a19f97;
--line:#33322e;--warn:#e39a5b;--chip:#2a2926}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:32px 16px 64px}h1{font-size:28px;margin:0 0 4px}
h2{font-size:19px;margin:36px 0 12px}.sub,.note{color:var(--muted)}.note{font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.stat b{display:block;font-size:22px}.stat span{color:var(--muted);font-size:13px}
.case{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:12px 0}
.case.diff{border-left:4px solid var(--warn)}.case h3{margin:0 0 6px;font-size:16px}
.ev{background:var(--chip);border-radius:8px;padding:10px 12px;font-size:13px;margin:8px 0 12px;white-space:pre-wrap}
.cols{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}@media (max-width:760px){.cols{grid-template-columns:1fr}}
.who{font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--muted)}
.dec{font-weight:700;font-size:16px}.chip{display:inline-block;background:var(--chip);border-radius:999px;
padding:1px 9px;font-size:12px;margin-left:6px}p.r{font-size:13px;margin:6px 0}details{font-size:13px;color:var(--muted)}
"""

DECISION_TEXT = {"confirmed": "✅ Confirmed", "walked_back": "↩️ Walked back", "delayed": "⏳ Delayed",
                 "never_happened": "❌ Never happened", "disputed": "🔴 Disputed", "no_change": "No change",
                 "error": "⚠️ Error"}


def write_report(conn, cfg, cases):
    e = lambda t: html.escape(str(t or ""))
    names = [n for n, _ in MODELS]
    total = {n: sum(c["results"][n]["cost"] for c in cases) for n in names}
    agree = sum(len({c["results"][n]["decision"] for n in names}) == 1 for c in cases)
    s_vs_o = sum(c["results"]["Sonnet"]["decision"] == c["results"]["Opus"]["decision"] for c in cases)
    practice = [c for c in cases if c.get("expected")]
    right = {n: sum(c["results"][n]["decision"] == c["expected"] for c in practice) for n in names}
    stats = [(f"${total[n] / len(cases):.4f}", f"{n} per decision") for n in names] + [
        (f"{right[n]}/{len(practice)}", f"{n}: practice cases right") for n in names] + [
        (f"{agree}/{len(cases)}", "all three agreed"), (f"{s_vs_o}/{len(cases)}", "Sonnet and Opus agreed")]
    blocks = []
    for c in cases:
        differs = len({c["results"][n]["decision"] for n in names}) > 1
        expected = c.get("expected")
        cols = "".join(
            f'<div><div class="who">{n}</div><div class="dec">'
            f'{"✓ " if expected and c["results"][n]["decision"] == expected else ("✗ " if expected else "")}'
            f'{DECISION_TEXT.get(c["results"][n]["decision"], c["results"][n]["decision"])}'
            f'<span class="chip">${c["results"][n]["cost"]:.4f}</span></div>'
            f'<p class="r">{e(c["results"][n].get("receipt_line"))}</p>'
            f'<details><summary>full reasoning</summary>{e(c["results"][n]["reason"])}</details></div>'
            for n in names)
        blocks.append(
            f'<div class="case{" diff" if differs else ""}"><h3>{"🧪 Practice · " if c["synthetic"] else "📰 Real · "}'
            f'“{e(c["claim_text"])}”</h3>'
            f'<div class="note">Claimed by {e(c["claimant"])}'
            f'{" · right answer under the rules: <b>" + DECISION_TEXT[expected] + "</b>" if expected else ""}'
            f'{" · ⚠️ models disagree" if differs else ""}</div>'
            f'<div class="ev"><b>New evidence</b> · {e(c["evidence_source"])}\n'
            f'{e(c["evidence"].split(chr(10), 3)[-1])}</div><div class="cols">{cols}</div></div>')
    stat_html = "".join(f'<div class="stat"><b>{v}</b><span>{k}</span></div>' for v, k in stats)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Claim Decisions</title><style>{CSS}</style></head>
<body><main><h1>Haiku vs. Sonnet vs. Opus: hard claim decisions</h1>
<p class="sub">{len(cases) - len(practice)} real cases + {len(practice)} practice cases with a known right answer ·
same prompt for every model ·
generated {datetime.now():%b %d, %Y %I:%M %p}</p><div class="grid">{stat_html}</div>
<h2>The cases</h2><p class="note">Orange edge = the models disagree. Each model's one-line receipt text is shown;
open "full reasoning" to see why. Signality uses Sonnet for these decisions today.</p>{''.join(blocks)}
</main></body></html>"""
    path = ROOT / "data" / "reports" / f"claims-haiku-sonnet-opus-{datetime.now():%Y-%m-%d}.html"
    path.write_text(page, encoding="utf-8")
    return path, total


def main():
    cfg = load_config()
    conn = db.connect(cfg["storage"]["db_path"])
    cases = json.loads(CASES_FILE.read_text()) if CASES_FILE.exists() else find_cases(conn, cfg)[0]
    cases = run(conn, cfg, cases)
    path, total = write_report(conn, cfg, cases)
    print(f"{len(cases)} cases | cost per decision: " + ", ".join(f"{n} ${t / len(cases):.4f}" for n, t in total.items()))
    print(f"report: {path}")


if __name__ == "__main__":
    main()
