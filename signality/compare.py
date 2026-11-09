"""Side-by-side model comparison and tuning simulator (Stage 2a task #8).

    ./.venv/bin/python -m signality.compare          # prints the numbers, writes an HTML report

Compares the live triage (Haiku) with comparison runs (Sonnet) on the same
stories, and simulates how many messages per day different topic-bonus and
threshold settings would send, using the real scores.
"""
import html
import json
from datetime import datetime, timedelta, timezone

from . import db, scoring, validity
from .settings import ROOT, load_config


def pairs(conn):
    """[(haiku_row, sonnet_row, articles)] for every story scored by both."""
    out = []
    for live in conn.execute("SELECT * FROM story_triage WHERE purpose = 'live' ORDER BY story_id DESC").fetchall():
        other = conn.execute(
            "SELECT * FROM story_triage WHERE story_id = ? AND purpose = 'comparison'", (live["story_id"],)
        ).fetchone()
        if other:
            out.append((live, other, validity.story_articles(conn, live["story_id"])))
    return out


def stories_per_day(conn):
    """New stories per day, measured from the last 24 hours of fetch rounds."""
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    n = conn.execute("SELECT COALESCE(SUM(new_stories), 0) FROM fetch_runs WHERE started_at >= ?", (since,)).fetchone()[0]
    return n or 100


def final_score(row, cfg, bonus):
    """Importance under a bonus option: ('mult', x) or ('points', n) for favored topics."""
    if not row["ai_related"]:
        return 0
    base = row["base_score"]
    favored = any(cfg["topics"].get(t, 1.0) > 1.0 for t in json.loads(row["topics"]))
    kind, amount = bonus
    if not favored:
        return round(base)
    return min(100, round(base * amount if kind == "mult" else base + amount))


BONUS_OPTIONS = [
    ("Current: ×1.3", ("mult", 1.3)),
    ("×1.15", ("mult", 1.15)),
    ("×1.1", ("mult", 1.1)),
    ("+5 points", ("points", 5)),
    ("No bonus", ("mult", 1.0)),
]


def simulate(rows, cfg, per_day):
    """Messages per day for each bonus option, with and without the 🔔 silent tier."""
    results = []
    n = len(rows)
    for name, bonus in BONUS_OPTIONS:
        tiers = [scoring.tier(final_score(r, cfg, bonus), cfg) for r in rows]
        count = {t: tiers.count(t) for t in ("alert", "silent", "digest", "stored")}
        results.append({
            "name": name,
            "alert_per_day": per_day * count["alert"] / n,
            "silent_per_day": per_day * count["silent"] / n,
            "digest_per_day": per_day * count["digest"] / n,
            "counts": count,
        })
    return results


def summarize(conn, cfg):
    ps = pairs(conn)
    n = len(ps)
    f_exact = {f: sum(h[f] == s[f] for h, s, _ in ps) for f in scoring.FACTORS}
    f_close = {f: sum(abs(h[f] - s[f]) <= 1 for h, s, _ in ps) for f in scoring.FACTORS}
    tier_same = sum(scoring.tier(h["importance"], cfg) == scoring.tier(s["importance"], cfg) for h, s, _ in ps)
    labels = [(validity.decide(h, a)[0], validity.decide(s, a)[0]) for h, s, a in ps]
    per_day = stories_per_day(conn)
    cost_h = sum(h["cost_usd"] for h, _, _ in ps) / n
    cost_s = sum(s["cost_usd"] for _, s, _ in ps) / n
    return {
        "n": n,
        "per_day": per_day,
        "factor_exact": f_exact,
        "factor_within_1": f_close,
        "mean_importance_gap": sum(abs(h["importance"] - s["importance"]) for h, s, _ in ps) / n,
        "tier_same": tier_same,
        "ai_related_same": sum(h["ai_related"] == s["ai_related"] for h, s, _ in ps),
        "label_same": sum(a == b for a, b in labels),
        "self_reported_same": sum(h["self_reported"] == s["self_reported"] for h, s, _ in ps),
        "cost_haiku": cost_h,
        "cost_sonnet": cost_s,
        "monthly_haiku": cost_h * per_day * 30,
        "monthly_sonnet": cost_s * per_day * 30,
        "sim_haiku": simulate([h for h, _, _ in ps], cfg, per_day),
        "sim_sonnet": simulate([s for _, s, _ in ps], cfg, per_day),
        "pairs": ps,
        "labels": labels,
    }


TIER_NAME = {"alert": "🚨 Alert", "silent": "🔔 Silent", "digest": "📰 Digest", "stored": "Stored"}

CSS = """
:root{--bg:#fbfaf7;--card:#fff;--ink:#1d1d1b;--muted:#6b6a65;--line:#e6e3dc;--accent:#c98a00;
--good:#2f7d4f;--warn:#b5651d;--chip:#f2efe8}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--card:#1f1f1c;--ink:#ecebe6;--muted:#a19f97;
--line:#33322e;--accent:#e8b33a;--good:#6cc08f;--warn:#e39a5b;--chip:#2a2926}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:1040px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:28px;margin:0 0 4px}h2{font-size:19px;margin:40px 0 12px}
.sub{color:var(--muted);margin:0 0 24px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.stat b{display:block;font-size:24px}.stat span{color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line);font-size:14px}
th{color:var(--muted);font-weight:600}td.n{font-variant-numeric:tabular-nums;text-align:right}
tr.pick td{background:color-mix(in srgb,var(--accent) 12%,transparent)}
.story{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:12px 0}
.story.diff{border-left:4px solid var(--warn)}
.story h3{margin:0 0 4px;font-size:16px}.meta{color:var(--muted);font-size:13px;margin-bottom:10px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:700px){.cols{grid-template-columns:1fr}}
.who{font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--muted)}
.score{font-size:20px;font-weight:700}.chip{display:inline-block;background:var(--chip);border-radius:999px;
padding:1px 9px;font-size:12px;margin-left:6px}
ul.f{padding-left:18px;margin:8px 0}ul.f li{font-size:13px;margin:2px 0}
p.sum{font-size:14px;margin:6px 0}.note{color:var(--muted);font-size:13px}
"""


def _e(text):
    return html.escape(str(text or ""))


def _side(row, cfg, who):
    tier = scoring.tier(row["importance"], cfg)
    factors = "".join(
        f"<li><b>{f.title()} {row[f]}</b> — {_e(row[f + '_reason'])}</li>" for f in scoring.FACTORS
    )
    not_ai = '<span class="chip">not AI → stored</span>' if not row["ai_related"] else ""
    return (f'<div><div class="who">{who}</div><div><span class="score">{row["importance"]}</span>'
            f'<span class="chip">{TIER_NAME[tier]}</span>{not_ai}</div>'
            f'<p class="sum"><b>{_e(row["headline"])}</b><br>{_e(row["summary"])}</p>'
            f'<ul class="f">{factors}</ul></div>')


def write_report(r, cfg):
    """A readable HTML report of the comparison. Returns its path (inside data/, never uploaded)."""
    n = r["n"]
    within = sum(r["factor_within_1"].values())
    stats = [
        (f"${r['monthly_haiku']:.2f}", "Haiku per month for triage"),
        (f"${r['monthly_sonnet']:.2f}", "Sonnet per month for triage"),
        (f"{within}/{n * 4}", "factor ratings within 1 point"),
        (f"{r['label_same']}/{n}", "same validity label"),
        (f"{r['tier_same']}/{n}", "landed in the same tier"),
        (f"{r['mean_importance_gap']:.0f} pts", "average importance gap"),
    ]
    stat_html = "".join(f'<div class="stat"><b>{v}</b><span>{k}</span></div>' for v, k in stats)
    rows = "".join(
        f'<tr{" class=pick" if o["name"] == "×1.1" else ""}><td>{_e(o["name"])}</td>'
        f'<td class="n">{o["alert_per_day"]:.1f}</td><td class="n">{o["silent_per_day"]:.1f}</td>'
        f'<td class="n">{o["digest_per_day"]:.0f}</td></tr>'
        for o in r["sim_haiku"]
    )
    stories = []
    for (h, s, arts), (lh, ls) in zip(r["pairs"], r["labels"]):
        differs = scoring.tier(h["importance"], cfg) != scoring.tier(s["importance"], cfg) or h["ai_related"] != s["ai_related"]
        sources = ", ".join(sorted({a["source_name"] for a in arts}))
        stories.append(
            f'<div class="story{" diff" if differs else ""}"><h3>{_e(h["headline"])}</h3>'
            f'<div class="meta">{_e(sources)} · {validity.LABELS[lh]}'
            f'{" (Sonnet: " + validity.LABELS[ls] + ")" if lh != ls else ""}'
            f'{" · 📄 partial" if h["text_source"] == "snippet" else ""}'
            f'{" · ⚠️ models disagree on the tier" if differs else ""}</div>'
            f'<div class="cols">{_side(h, cfg, "Haiku (cheap)")}{_side(s, cfg, "Sonnet (careful)")}</div></div>'
        )
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Haiku vs Sonnet</title>
<style>{CSS}</style></head><body><main>
<h1>Haiku vs. Sonnet: story triage</h1>
<p class="sub">{n} real stories scored by both models · about {r['per_day']} new stories a day ·
generated {datetime.now():%b %d, %Y %I:%M %p}</p>
<div class="grid">{stat_html}</div>
<h2>Messages per day under each topic-bonus option</h2>
<p class="note">Using Haiku's real scores. The digest arrives once a morning and shows the top ~12 of these;
🔔 silent messages arrive through the day without sound. Small sample from one (election) day, so treat
these as rough.</p>
<table><tr><th>Bonus for jobs &amp; finance stories</th><th class="n">🚨 per day</th>
<th class="n">🔔 per day</th><th class="n">📰 eligible for digest</th></tr>{rows}</table>
<h2>Story by story</h2>
<p class="note">Orange edge = the two models put the story in different tiers. Each rating shows the model's reason.</p>
{''.join(stories)}
</main></body></html>"""
    path = ROOT / "data" / "reports" / f"haiku-vs-sonnet-{datetime.now():%Y-%m-%d}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return path


def main():
    cfg = load_config()
    conn = db.connect(cfg["storage"]["db_path"])
    r = summarize(conn, cfg)
    n = r["n"]
    print(f"{n} stories scored by both | ~{r['per_day']} new stories/day")
    print(f"cost/story: Haiku ${r['cost_haiku']:.5f}  Sonnet ${r['cost_sonnet']:.5f}"
          f"  ({r['cost_sonnet'] / r['cost_haiku']:.0f}x)  ->  monthly: Haiku ${r['monthly_haiku']:.2f}, Sonnet ${r['monthly_sonnet']:.2f}")
    for f in scoring.FACTORS:
        print(f"  {f:<8} exact {r['factor_exact'][f]}/{n}  within 1 point {r['factor_within_1'][f]}/{n}")
    print(f"  importance gap avg {r['mean_importance_gap']:.1f} | same tier {r['tier_same']}/{n} | same 'is AI' {r['ai_related_same']}/{n}"
          f" | same validity label {r['label_same']}/{n} | same self-reported {r['self_reported_same']}/{n}")
    for who in ("haiku", "sonnet"):
        print(f"\nmessages/day using {who.title()}'s scores:")
        for o in r[f"sim_{who}"]:
            print(f"  {o['name']:<14} 🚨 {o['alert_per_day']:4.1f}   🔔 {o['silent_per_day']:5.1f}   📰 {o['digest_per_day']:5.1f}")
    print("\nper story (Haiku -> Sonnet importance, label):")
    for (h, s, _), (lh, ls) in zip(r["pairs"], r["labels"]):
        flag = " *" if scoring.tier(h["importance"], cfg) != scoring.tier(s["importance"], cfg) or lh != ls else ""
        print(f"  #{h['story_id']:<4}{h['importance']:>3} -> {s['importance']:>3}  {lh:>10} -> {ls:<10} {h['headline'][:55]}{flag}")
    print(f"\nreport: {write_report(r, cfg)}")


if __name__ == "__main__":
    main()
