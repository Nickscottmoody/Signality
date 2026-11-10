"""Web search for open claims: Siggy goes looking for the outcome instead of waiting for it.

Until now a claim only resolved if one of our feeds happened to report the outcome.
Each round, the open claims most due for a look get ONE web search each:

1. Haiku reads the pages found and says what each does to the claim (confirms, contradicts,
   walked back, delayed, did not happen, or just repeats it), and whether it has its own sourcing.
2. A new independent outlet repeating a 🟡/🟠 claim upgrades it to 🟢 by rule.
3. If any page may SETTLE the claim, Sonnet makes the final call (the same strict editor used
   for claim decisions), reading the full page where it's free to read.

Every page is kept (web_results), and a claim change points at the page that caused it, so
its 🧾 receipt links the real evidence.

Try it (uses 1 search credit and a little AI):
    ./.venv/bin/python -m signality.claim_search --list
    ./.venv/bin/python -m signality.claim_search --claim 31
"""
import argparse
import re
from datetime import datetime, timedelta, timezone

from . import ai, article_text, claims, db, resolution, search
from .corroborate import _overrule
from .settings import load_config

SYSTEM = """You help Signality, an AI-news agent, track claims until they're proven. You get ONE \
open claim Signality is tracking (with its history) and pages a web search found. For each page, say \
what it does to the claim. Judge only from the page's title, date, and snippet.

The page must address the claim ITSELF, not its background or the wider story. Example: for \
"Rosen Law Firm is preparing a class action against Nvidia", a page about Nvidia's stock drop is \
related_no_change. Only pages dated after the claim was made can confirm or settle it.

relation (choose one):
- unrelated: about something else.
- related_no_change: same topic, but adds nothing that changes the claim's status.
- supports: reports the same claim again (more corroboration) without settling it.
- confirms: shows the claim is true (e.g., the event happened, the organization confirmed it, an \
official document shows it, or independent testing verified a performance claim).
- contradicts: someone credible disputes it, or evidence points the other way, without settling it.
- walked_back: the claimant retracted, corrected, or denied it.
- delayed: a planned event is now happening later than claimed.
- did_not_happen: a planned event was cancelled or clearly will not happen.

independent: true only if the page has its own sourcing for the claim (its own reporting, the \
organization itself, or an official body), not merely repeating the original report ("..., the FT \
reported" is NOT independent of the FT). Blogs, forums, and content farms are never independent.
reason: one short, specific sentence the reader can check against the page."""

SCHEMA = {
    "type": "object",
    "properties": {
        "pages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},  # "R3"
                    "relation": {"type": "string", "enum": [
                        "unrelated", "related_no_change", "supports", "confirms", "contradicts",
                        "walked_back", "delayed", "did_not_happen"]},
                    "independent": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "relation", "independent", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["pages"],
    "additionalProperties": False,
}

DECIDE_SYSTEM = resolution.DECIDE_SYSTEM + """

The new evidence here is one or more web pages (R1, R2...). evidence_id: the page your decision \
rests on, e.g. "R2" (an empty string for no_change)."""

DECIDE_SCHEMA = {
    **resolution.DECIDE_SCHEMA,
    "properties": {**resolution.DECIDE_SCHEMA["properties"], "evidence_id": {"type": "string"}},
    "required": resolution.DECIDE_SCHEMA["required"] + ["evidence_id"],
}

# Strongest first: which settling page Sonnet sees first.
SETTLE_ORDER = ["walked_back", "did_not_happen", "delayed", "confirms", "contradicts"]


ATTRIBUTION = re.compile(r"^\s*(according to [^,]{1,60},\s*|[\w .&'-]{2,40}? (reports|reported|says|said) that\s+)",
                         re.IGNORECASE)


def search_query(claim_text):
    """The claim without "According to X," / "X reports that" (who reported it isn't the subject)."""
    return ATTRIBUTION.sub("", claim_text, count=1).strip()


def _iso_ago(**delta):
    return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat(timespec="seconds")


def _slow(c, today):
    """Plans not yet due and companies' own performance claims change slowly: look less often."""
    not_due = c["kind"] == "future" and c["due_date"] and c["due_date"] > today
    return bool(not_due or c["label"] == "self_reported")


def candidates(conn, cfg):
    """Open claims due for a web search, most deserving first."""
    s = cfg["search"]
    rows = conn.execute(
        """
        SELECT c.*, a.published_at AS source_published, a.url AS source_url,
               COALESCE(t.importance, 0) AS importance,
               (SELECT MAX(w.searched_at) FROM web_searches w WHERE w.subject_type = 'claim'
                AND w.subject_id = c.id AND w.ok = 1) AS last_searched,
               (SELECT COUNT(*) FROM web_searches w WHERE w.subject_type = 'claim'
                AND w.subject_id = c.id AND w.ok = 0 AND w.searched_at >= ?) AS recent_failures
        FROM claims c JOIN articles a ON a.id = c.article_id
        LEFT JOIN story_triage t ON t.story_id = c.story_id AND t.purpose = 'live'
        WHERE c.status IN ('open', 'delayed') AND c.created_at >= ? AND a.published_at <= ?
        """,
        (_iso_ago(days=1), _iso_ago(days=cfg["claims"]["match_window_days"]),
         _iso_ago(hours=s["claim_min_age_hours"])),
    ).fetchall()
    today = datetime.now(timezone.utc).date().isoformat()
    due = []
    for c in rows:
        if c["recent_failures"] >= s["max_failed_attempts"]:
            continue
        days = s["claim_slow_recheck_days"] if _slow(c, today) else s["claim_recheck_days"]
        if c["last_searched"] and c["last_searched"] > _iso_ago(days=days):
            continue
        overdue = bool(c["due_date"] and c["due_date"] <= today)
        # never searched first, then plans past their due date, then by how important the story was
        due.append(((c["last_searched"] is not None, not overdue, -c["importance"], c["id"]), c))
    due.sort(key=lambda x: x[0])
    return [c for _, c in due]


def _seen_urls(conn, claim_id):
    """Pages already judged for this claim in earlier searches (never paid for twice)."""
    return {r[0] for r in conn.execute(
        "SELECT r.url FROM web_results r JOIN web_searches w ON w.id = r.search_id"
        " WHERE w.subject_type = 'claim' AND w.subject_id = ?", (claim_id,))}


def page_text(i, r):
    return (f"R{i} · {r['outlet']} ({r['domain']}) · published {(r['published_at'] or 'date unknown')[:10]}\n"
            f"Title: {r['title']}\n{r.get('full_text') or r['snippet']}")


def judge(conn, cfg, c, pages):
    """Haiku: what each page does to the claim. Fills relation/independent/reason. Returns cost."""
    prompt = (f"OPEN CLAIM\n{resolution.claim_brief(conn, c)}\n  claimant: {c['claimant'] or 'unknown'}\n\n"
              "WEB PAGES\n" + "\n\n".join(page_text(i, r) for i, r in enumerate(pages, start=1)))
    data, cost = ai.ask_json(conn, cfg, task="claim_search_match", role="bulk", system=SYSTEM,
                             prompt=prompt, schema=SCHEMA, story_id=c["story_id"])
    verdicts = {resolution.claim_number(v["id"]): v for v in data["pages"]}
    for i, r in enumerate(pages, start=1):
        v = verdicts.get(i) or {"relation": "related_no_change", "independent": False, "reason": "no verdict returned"}
        r.update(relation=v["relation"], independent=bool(v["independent"]), why=v["reason"])
    return cost


def apply_rules(pages, cfg, claim_made):
    """Code beats prompts: aggregators never count, and evidence must come after the claim."""
    aggregators = set(cfg["search"].get("aggregator_domains", []))
    for r in pages:
        r["basis"] = r["relation"]
        if r["domain"] in aggregators and r["independent"]:
            r["independent"] = False
            r["why"] += " [rule: aggregator site]"
        if (r["relation"] in resolution.SETTLING and r["published_at"]
                and r["published_at"][:10] < claim_made[:10]):
            _overrule(r, "related_no_change", "published before the claim was made")
            r["relation"] = "related_no_change"
    return pages


def investigate(conn, cfg, c, budget):
    """One search for one claim: judge the pages, apply rules, maybe ask Sonnet. Returns a summary."""
    query = search_query(c["text"])
    claim_made = c["source_published"]
    known = search.source_domains(conn, cfg)
    source_name = conn.execute(
        "SELECT s.name FROM articles a JOIN sources s ON s.id = a.source_id WHERE a.id = ?", (c["article_id"],)
    ).fetchone()[0]
    # The outlet the claim came from (Google News links hide it, so use the source's real site too).
    origins = {d for d, name in known.items() if name == source_name} | {search.domain_of(c["source_url"])}
    origins.discard("news.google.com")

    def record(ok, credits, error=None, count=0, cost=0.0):
        cur = conn.execute(
            "INSERT INTO web_searches (subject_type, subject_id, provider, query, searched_at, credits, ok, error,"
            " result_count, check_cost_usd) VALUES ('claim', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (c["id"], search.PROVIDER, query, db.utcnow(), credits, int(ok), error, count, cost),
        )
        conn.commit()
        return cur.lastrowid

    try:
        found = search.search(query, cfg, start_date=claim_made[:10], exclude_domains=origins)
    except search.SearchError as e:
        record(False, 0 if "missing" in str(e) or "HTTP 4" in str(e) else 1, error=str(e)[:300])
        raise

    aggregators = set(cfg["search"].get("aggregator_domains", []))
    seen = _seen_urls(conn, c["id"])
    pages = [{**r, "outlet": known.get(r["domain"], r["domain"])} for r in found
             if r["url"] not in seen and r["domain"] not in aggregators
             and not any(search.same_organization(r["domain"], o) for o in origins)]

    cost = 0.0
    if pages:
        cost += judge(conn, cfg, c, pages)
        apply_rules(pages, cfg, claim_made)
    search_id = record(True, 1, count=len(pages), cost=cost)
    for r in pages:
        r["id"] = conn.execute(
            "INSERT INTO web_results (search_id, url, domain, outlet, title, published_at, snippet, basis,"
            " original_outlet, why, independent) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
            (search_id, r["url"], r["domain"], r["outlet"], r["title"], r["published_at"], r["snippet"],
             r["basis"], r["why"], int(r["independent"])),
        ).lastrowid
    conn.commit()

    change = None
    settling = sorted((r for r in pages if r["relation"] in resolution.SETTLING),
                      key=lambda r: (SETTLE_ORDER.index(r["relation"]), not r["independent"]))[:3]
    if settling and budget["sonnet"] > 0:
        budget["sonnet"] -= 1
        change, decide_cost = decide(conn, cfg, c, settling)
        cost += decide_cost
    if change is None and c["label"] in resolution.UPGRADABLE:  # not settled, but maybe better supported
        backer = independent_backer(conn, c["id"], origins)
        if backer:
            reason = f"Independently reported by {backer['outlet']} (found by web search): {backer['why']}"
            _event(conn, c, "label_change", "likely", c["status"], reason, backer["id"], "haiku+rules")
            change = {"claim_id": c["id"], "claim": c["text"], "change": "🟢 likely", "reason": reason}
    return {"claim_id": c["id"], "claim": c["text"], "pages": pages, "cost_usd": cost, "change": change}


def independent_backer(conn, claim_id, origins):
    """A page from ANY search for this claim that independently reports it (not from its own outlet)."""
    for r in conn.execute(
        "SELECT r.id, r.outlet, r.domain, r.why FROM web_results r JOIN web_searches w ON w.id = r.search_id"
        " WHERE w.subject_type = 'claim' AND w.subject_id = ? AND r.basis = 'supports' AND r.independent = 1"
        " ORDER BY r.id", (claim_id,),
    ):
        if not any(search.same_organization(r["domain"], o) for o in origins):
            return dict(r)
    return None


def _event(conn, c, event, label, status, reason, web_result_id, decided_by, detail=None):
    """Record a claim change whose evidence is a web page (mirrors resolution._event)."""
    now = db.utcnow()
    conn.execute(
        "INSERT INTO claim_events (claim_id, at, event, label, status, reason, evidence_web_result_id, decided_by,"
        " detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (c["id"], now, event, label, status, reason, web_result_id, decided_by, detail),
    )
    resolved = status not in ("open", "not_tracked")
    conn.execute(
        "UPDATE claims SET label = ?, status = ?, updated_at = ?, resolved_at = CASE WHEN ? THEN ? ELSE resolved_at END"
        " WHERE id = ?",
        (label, status, now, int(resolved), now, c["id"]),
    )
    conn.commit()


def decide(conn, cfg, c, settling):
    """Sonnet's final call on the pages that may settle the claim. Returns (change or None, cost)."""
    for r in settling:  # read the real page where it's free; the snippet otherwise
        text = article_text.fetch(r["url"], cfg)
        r["full_text"] = text[: cfg["search"]["evidence_char_cap"]] if text else None
    evidence = "\n\n".join(page_text(i, r) for i, r in enumerate(settling, start=1))
    hints = "; ".join(f"R{i}: {r['relation']} - {r['why']}" for i, r in enumerate(settling, start=1))
    verdict, cost = ai.ask_json(
        conn, cfg, task="claim_resolve_web", role="high_stakes", system=DECIDE_SYSTEM, schema=DECIDE_SCHEMA,
        prompt=f"CLAIM AND HISTORY\n{resolution.claim_brief(conn, c)}\n\nNEW EVIDENCE (web pages)\n{evidence}\n\n"
               f"First-pass assessment: {hints}",
        story_id=c["story_id"],
    )
    n = resolution.claim_number(verdict["evidence_id"])
    page = settling[n - 1] if n and 1 <= n <= len(settling) else settling[0]
    model = cfg["models"]["high_stakes"]
    outcome = resolution.apply_decision(c, verdict["decision"])
    if outcome is None:  # still shown in the claim's history: it was checked against this evidence
        line = verdict["receipt_line"].strip()
        _event(conn, c, "checked", c["label"], c["status"],
               f"Checked against {page['outlet']} (found by web search), no change" + (f": {line}" if line else "."),
               page["id"], model, detail=verdict["reason"])
        return None, cost
    label, status = outcome
    event = "resolved" if status != "open" else "label_change"
    _event(conn, c, event, label, status, verdict["receipt_line"], page["id"], model, detail=verdict["reason"])
    return {"claim_id": c["id"], "claim": c["text"], "change": f"{status} / {label}",
            "reason": verdict["receipt_line"]}, cost


def run(conn, cfg):
    """One round: search for the open claims most due for a look, within the limits."""
    summary = {"searched": 0, "failed": 0, "cost_usd": 0.0, "changes": [], "stopped": None}
    if not cfg["search"]["enabled"]:
        return summary
    room = min(search.allowance(conn, cfg, "claim"), cfg["search"]["claims_per_round"])
    if room <= 0:
        return summary
    budget = {"sonnet": cfg["search"]["claim_sonnet_per_round"]}
    for c in candidates(conn, cfg)[:room]:
        try:
            r = investigate(conn, cfg, c, budget)
        except search.SearchError as e:
            summary["failed"] += 1
            summary["stopped"] = str(e)[:120]
            break
        summary["searched"] += 1
        summary["cost_usd"] += r["cost_usd"]
        if r["change"]:
            summary["changes"].append(r["change"])
    return summary


def main():
    parser = argparse.ArgumentParser(description="Search the web for evidence on open claims.")
    parser.add_argument("--claim", type=int, help="claim id to investigate now")
    parser.add_argument("--list", action="store_true", help="show which claims would be searched next")
    args = parser.parse_args()
    cfg = load_config()
    conn = db.connect(cfg["storage"]["db_path"])
    if args.list or not args.claim:
        used = search.usage(conn, cfg, "claim")
        print(f"claim searches used: {used['today']} today (limit {cfg['search']['claims_per_day']})")
        for c in candidates(conn, cfg)[:20]:
            last = (c["last_searched"] or "never")[:10]
            print(f"  claim {c['id']:<4} {claims.LABELS[c['label']]:<16} last searched {last:<10} {c['text'][:80]}")
        return
    rows = [c for c in candidates(conn, cfg) if c["id"] == args.claim] or conn.execute(
        "SELECT c.*, a.published_at AS source_published, a.url AS source_url FROM claims c"
        " JOIN articles a ON a.id = c.article_id WHERE c.id = ?", (args.claim,)).fetchall()
    r = investigate(conn, cfg, rows[0], {"sonnet": 1})
    print(f"claim {r['claim_id']}: {r['claim']}\n  AI cost ${r['cost_usd']:.4f}")
    for p in r["pages"]:
        print(f"  - {p['relation']:<18} {'indep' if p['independent'] else '     '} {p['outlet']:<26} {p['why'][:90]}")
    print(f"  change: {r['change'] or 'none'}")


if __name__ == "__main__":
    main()
