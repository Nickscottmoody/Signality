"""Corroboration: when only one outlet has a story, search the web for others.

Each round, the most important single-source stories (🟡 Reported, 🟠 Unverified) get ONE
web search. Haiku then reads the results and says, for each page, whether it reports the
same event and on what basis: the outlet's own reporting, a repeat of someone else's
report, the organization's own page, an on-record confirmation, or a denial.

Code (validity.py), not the model, turns those verdicts into a label:
- 2+ independent outlets          -> 🟢 Likely
- the organization's own page     -> ✅ Confirmed
- a denial or correction          -> 🔴 Disputed
- nothing independent             -> label stays, reason says "web search found no
                                     independent confirmation yet"

Alert-level stories are searched right away, before the 🚨 decision ("investigate first").
Others wait a little (search.wait_hours) so our own feeds can pick up other outlets for free.

Try it without sending anything (uses search credits and a little AI):
    ./.venv/bin/python -m signality.corroborate --story 123
"""
import argparse
from datetime import datetime, timedelta, timezone

from . import ai, db, search, validity
from .settings import load_config

SYSTEM = """You check web search results for Signality, a personal AI-news agent whose motto is \
"AI news with receipts." One outlet has reported a story. A web search found other pages. For \
each page, decide whether it independently backs up the SAME story. Code turns your verdicts \
into a public validity label, so be strict: when unsure, choose "unclear".

First write key_fact: the ONE specific thing the story's headline reports happened (who did \
what), in at most 15 words. Background and causes are not the key fact. Example: for "Law firms \
race to file suits against Nvidia after CEO probe and stock drop", the key fact is "law firms are \
filing securities lawsuits against Nvidia", not the probe or the stock drop.

Then, for each page:
- reports_key_fact: true only if the page itself reports key_fact (not just its background).
- basis: pick one:
- not_same_event: about a different event, an older/newer development, or only the same company \
or topic. The story's specific news (what its headline says happened) must be reported, not \
just its background. Example: if the story is "bettors put the odds of the Marvell-Lumentum \
deal near a coin flip", a page about the deal itself is not_same_event.
- own_reporting: a professional newsroom or recognized trade publication reports the same event \
on its own authority (its own sources, interviews, documents, or a statement it obtained). \
Quoting the organization's public statement counts. Wire services (AP, Reuters, AFP) reporting \
under their own name count as own_reporting.
- repeats_other: it credits another outlet's report ("according to Bloomberg", "first reported \
by", "X reported"), or it is a syndicated or aggregated copy (a wire story republished by \
another site, Yahoo/MSN copies, a Reuters or AP byline/dateline on someone else's site), or it belongs to the same news organization as an outlet in \
"Already reported by" (a sister site such as Bloomberg Law for Bloomberg). Put the outlet it \
repeats in original_outlet.
- primary: the page is ON the website of the organization the story is about (its newsroom, \
blog, filing) or of a government, court, or regulator, AND it states key_fact itself. A news site quoting or linking to the \
organization's post is own_reporting, not primary.
- official_confirmation: a newsroom reports that the organization itself confirmed the event \
on the record. "Says it is investigating reports" or "declined to comment" is NOT confirmation.
- denial: the organization or a named party involved denies it, or the original outlet \
corrected or retracted it.
- low_quality: same event, but the page is a blog, forum, social post, press-release \
distribution site, SEO/content farm, or unknown site that adds no reporting.
- unclear: you can't tell from the title and snippet.

why: at most 12 words, naming the fact on the page that matches (or doesn't match) the story.
original_outlet: only for repeats_other; otherwise an empty string."""

SCHEMA = {
    "type": "object",
    "properties": {
        "key_fact": {"type": "string"},
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "reports_key_fact": {"type": "boolean"},
                    "basis": {"type": "string", "enum": [
                        "not_same_event", "own_reporting", "repeats_other", "primary",
                        "official_confirmation", "denial", "low_quality", "unclear"]},
                    "original_outlet": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["id", "reports_key_fact", "basis", "original_outlet", "why"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["key_fact", "results"],
    "additionalProperties": False,
}


def _ago(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")


def candidates(conn, cfg):
    """Single-source stories worth one search, most important first."""
    s = cfg["search"]
    alert_at = cfg["importance"]["thresholds"]["alert"]
    rows = conn.execute(
        """
        SELECT t.story_id, t.importance, st.first_seen_at FROM story_triage t
        JOIN stories st ON st.id = t.story_id
        WHERE t.purpose = 'live' AND st.status = 'triaged' AND t.ai_related = 1
          AND t.importance >= ? AND st.first_seen_at >= ?
          AND (st.first_seen_at <= ? OR t.importance >= ?)
          AND NOT EXISTS (SELECT 1 FROM web_searches w WHERE w.subject_type = 'story'
                          AND w.subject_id = t.story_id AND w.ok = 1)
          AND (SELECT COUNT(*) FROM web_searches w WHERE w.subject_type = 'story'
               AND w.subject_id = t.story_id AND w.ok = 0) < ?
        ORDER BY t.importance DESC, st.first_seen_at DESC
        """,
        (s["min_importance"], _ago(s["max_story_age_hours"]), _ago(s["wait_hours"]), alert_at,
         s["max_failed_attempts"]),
    ).fetchall()
    out = []
    for story_id, importance, first_seen in rows:
        label = validity.update(conn, story_id)
        if label and label["label"] in ("reported", "unverified"):
            out.append({"story_id": story_id, "importance": importance, "first_seen_at": first_seen})
    return out


def _feed_domains(conn, story_id, known):
    """Domains of the outlets already in the story (no point finding them again)."""
    names = {r[0] for r in conn.execute(
        "SELECT s.name FROM articles a JOIN sources s ON s.id = a.source_id WHERE a.story_id = ?", (story_id,))}
    domains = {d for d, name in known.items() if name in names}
    domains |= {search.domain_of(r[0]) for r in conn.execute("SELECT url FROM articles WHERE story_id = ?", (story_id,))}
    domains.discard("news.google.com")
    return domains


def build_prompt(t, story_outlets, first_seen, results):
    lines = [
        f"Story: {t['headline']}",
        f"Summary: {t['summary']}",
        f"First seen: {first_seen[:10]}",
        f"Already reported by: {', '.join(story_outlets)}",
        "",
        "Search results:",
    ]
    for i, r in enumerate(results, start=1):
        lines += [
            f"R{i} · {r['outlet']} ({r['domain']}) · {(r['published_at'] or 'date unknown')[:10]}",
            f"Title: {r['title']}",
            f"Snippet: {r['snippet']}",
            "",
        ]
    return "\n".join(lines)


def judge(conn, cfg, story_id, t, story_outlets, first_seen, results):
    """Haiku's verdict on each result. Returns (results with basis/why/original_outlet, cost)."""
    data, cost = ai.ask_json(
        conn, cfg, task="corroborate", role="bulk", story_id=story_id, system=SYSTEM,
        prompt=build_prompt(t, story_outlets, first_seen, results), schema=SCHEMA,
    )
    verdicts = {}
    for v in data["results"]:
        digits = "".join(ch for ch in v["id"] if ch.isdigit())  # "R3" -> 3
        if digits:
            verdicts[int(digits)] = v
    for i, r in enumerate(results, start=1):
        v = verdicts.get(i, {"basis": "unclear", "why": "no verdict returned", "original_outlet": "",
                             "reports_key_fact": False})
        r.update(basis=v["basis"], why=v["why"], original_outlet=v["original_outlet"] or None)
        if not v["reports_key_fact"] and r["basis"] in COUNTED:
            _overrule(r, "not_same_event", "page doesn't report the key fact")
    return results, cost, data["key_fact"]


COUNTED = ("own_reporting", "primary", "official_confirmation", "denial")


def _overrule(r, basis, why):
    r["why"] = f"{r['why']} [rule: {why}]"
    r["basis"] = basis


def apply_rules(results, cfg, story_text, primary_domains):
    """Fixed rules that overrule the model where it's known to slip (code beats prompts).

    - Aggregators (Yahoo, MSN...) only republish: never independent.
    - "primary" must really be the organization's own site (its name in the story, a known
      primary source, or a government site); a news site quoting a blog post is not.
    - An outlet the model judged as BOTH its own reporting and a copy of someone else's
      gets no credit (mixed signals -> not independent).
    """
    aggregators = set(cfg["search"].get("aggregator_domains", []))
    text = " " + "".join(ch if ch.isalnum() else " " for ch in story_text.lower()) + " "
    for r in results:
        if r["domain"] in aggregators and r["basis"] in COUNTED:
            _overrule(r, "repeats_other", "aggregator site")
        elif r["basis"] == "primary":
            name = r["domain"].split(".")[0]
            government = any(r["domain"].endswith(t) or f"{t}." in r["domain"] for t in (".gov", ".mil", "europa.eu"))
            if not (government or r["domain"] in primary_domains or (len(name) >= 3 and f" {name} " in text)):
                _overrule(r, "own_reporting", "not the organization's own site")
    copies = {r["domain"] for r in results if r["basis"] == "repeats_other"}
    for r in results:
        if r["basis"] == "own_reporting" and r["domain"] in copies:
            _overrule(r, "repeats_other", "same site also carries copies of other outlets' reports")
    return results


def investigate(conn, cfg, story_id, known=None):
    """Search once for one story, judge the results, save them, update the label.

    Returns a summary dict. Raises search.SearchError if the search itself failed
    (that attempt is recorded so a broken story isn't retried forever).
    """
    known = known if known is not None else search.source_domains(conn, cfg)
    t = conn.execute("SELECT * FROM story_triage WHERE story_id = ? AND purpose = 'live'", (story_id,)).fetchone()
    first_seen = conn.execute("SELECT first_seen_at FROM stories WHERE id = ?", (story_id,)).fetchone()[0]
    story_outlets = sorted({r[0] for r in conn.execute(
        "SELECT s.name FROM articles a JOIN sources s ON s.id = a.source_id WHERE a.story_id = ?", (story_id,))})
    before = validity.current(conn, story_id)
    query = t["headline"]

    def record(ok, credits, error=None, count=0, cost=0.0, key_fact=None):
        cur = conn.execute(
            "INSERT INTO web_searches (subject_type, subject_id, provider, query, searched_at, credits, ok, error,"
            " result_count, check_cost_usd, key_fact) VALUES ('story', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (story_id, search.PROVIDER, query, db.utcnow(), credits, int(ok), error, count, cost, key_fact),
        )
        conn.commit()
        return cur.lastrowid

    try:
        found = search.search(
            query, cfg, start_date=search.start_date_for(first_seen, cfg["search"]["days_before"]),
            exclude_domains=_feed_domains(conn, story_id, known),
        )
    except search.SearchError as e:
        # A missing key or used-up plan costs nothing; anything else may have used a credit.
        record(False, 0 if "missing" in str(e) or "HTTP 4" in str(e) else 1, error=str(e)[:300])
        raise

    feed_domains = _feed_domains(conn, story_id, known)
    results = []
    for r in found:
        if any(search.same_organization(r["domain"], d) for d in feed_domains):
            continue  # an outlet we already have, or its sister site (Bloomberg Law for Bloomberg)
        results.append({**r, "outlet": known.get(r["domain"], r["domain"])})

    cost, key_fact = 0.0, None
    if results:
        results, cost, key_fact = judge(conn, cfg, story_id, t, story_outlets, first_seen, results)
        primary_domains = {d for d, name in known.items()
                           if any(src["name"] == name and src["type"] == "primary" for src in cfg["sources"])}
        results = apply_rules(results, cfg, f"{t['headline']} {t['summary']}", primary_domains)
    search_id = record(True, 1, count=len(results), cost=cost, key_fact=key_fact)
    for r in results:
        conn.execute(
            "INSERT INTO web_results (search_id, url, domain, outlet, title, published_at, snippet, basis,"
            " original_outlet, why) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (search_id, r["url"], r["domain"], r["outlet"], r["title"], r["published_at"], r["snippet"],
             r["basis"], r["original_outlet"], r["why"]),
        )
    conn.commit()
    after = validity.update(conn, story_id)
    return {
        "story_id": story_id, "headline": t["headline"], "results": results, "cost_usd": cost, "key_fact": key_fact,
        "before": before["label"] if before else None, "after": after["label"], "reason": after["reason"],
    }


def run(conn, cfg):
    """One round: search for the most important single-source stories, within the limits."""
    summary = {"searched": 0, "upgraded": 0, "failed": 0, "cost_usd": 0.0, "changes": [], "stopped": None}
    if not cfg["search"]["enabled"]:
        return summary
    room = min(search.allowance(conn, cfg), cfg["search"]["max_per_round"])
    if room <= 0:
        summary["stopped"] = "daily or monthly search limit reached"
        return summary
    known = search.source_domains(conn, cfg)
    for c in candidates(conn, cfg)[:room]:
        try:
            r = investigate(conn, cfg, c["story_id"], known)
        except search.SearchError as e:
            summary["failed"] += 1
            summary["stopped"] = str(e)[:120]
            break  # likely the network or the plan: try again next round
        summary["searched"] += 1
        summary["cost_usd"] += r["cost_usd"]
        if r["after"] != r["before"]:
            summary["upgraded"] += 1
            summary["changes"].append(r)
    return summary


def main():
    parser = argparse.ArgumentParser(description="Search the web to corroborate one story (or list candidates).")
    parser.add_argument("--story", type=int, help="story id to investigate now")
    parser.add_argument("--list", action="store_true", help="show which stories would be searched next")
    args = parser.parse_args()
    cfg = load_config()
    conn = db.connect(cfg["storage"]["db_path"])
    if args.list or not args.story:
        used = search.usage(conn, cfg)
        print(f"searches used: {used['today']} today, {used['month']} this month "
              f"(limits {cfg['search']['max_per_day']}/day, {cfg['search']['monthly_limit']}/month)")
        for c in candidates(conn, cfg)[:20]:
            t = conn.execute("SELECT headline FROM story_triage WHERE story_id = ? AND purpose = 'live'",
                             (c["story_id"],)).fetchone()[0]
            print(f"  #{c['story_id']}  {c['importance']}  {t}")
        return
    r = investigate(conn, cfg, args.story)
    print(f"#{r['story_id']} {r['headline']}\n  key fact: {r['key_fact']}\n"
          f"  {r['before']} -> {r['after']}: {r['reason']}\n  AI cost ${r['cost_usd']:.4f}")
    for x in r["results"]:
        print(f"  - {x['basis']:<22} {x['outlet']:<28} {x['why']}")


if __name__ == "__main__":
    main()
