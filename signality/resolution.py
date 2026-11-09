"""Resolving claims: does new reporting settle an open claim?

Every round, each new article is compared with open claims, cheapest first:
1. Free: only claims sharing two or more distinctive words with the article.
2. Haiku: what does the article do to each claim? (supports, confirms, contradicts...)
3. Sonnet: only when Haiku thinks a claim may be settled, it makes the final call.

A new INDEPENDENT outlet supporting a 🟡/🟠 claim upgrades it to 🟢 by rule.
Every change is written to claim_events with the evidence and who decided.
"""
from datetime import datetime, timedelta, timezone

from . import ai, claims, db
from .dedup import key_words

# Attribution words appear in many claims ("according to the New York Times...")
# and say nothing about the subject, so they don't count toward a match.
ATTRIBUTION = {"according", "reports", "reported", "report", "says", "said", "york", "times", "bloomberg",
               "reuters", "information", "journal", "street", "wall", "financial", "unnamed", "sources",
               "people", "familiar", "matter", "memo", "told"}

MATCH_SYSTEM = """You help Signality, an AI-news agent, track claims until they're proven. You get \
ONE new news item and a few OPEN claims Signality is tracking. For each claim, say what the new item \
does to it. Judge only from what the new item actually says; a preview may be thin.

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

claim_id: the claim's number only (for "Claim 24", write "24").
independent: true only if the new item has its own sourcing for the claim, not merely repeating the \
original report ("..., the FT reported" is NOT independent of the FT).
reason: one short, specific sentence the reader can check against the new item."""

MATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "assessments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string"},  # the claim's number
                    "reason": {"type": "string"},
                    "relation": {"type": "string", "enum": [
                        "unrelated", "related_no_change", "supports", "confirms", "contradicts",
                        "walked_back", "delayed", "did_not_happen"]},
                    "independent": {"type": "boolean"},
                },
                "required": ["claim_id", "reason", "relation", "independent"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["assessments"],
    "additionalProperties": False,
}

DECIDE_SYSTEM = """You are the senior editor for Signality's receipts system: "AI news with receipts." \
A cheaper model thinks a new news item may settle an open claim. Make the final decision. The reader \
will see your reason next to the claim's full history, so it must be specific and checkable.

decision (choose one):
- confirmed: the evidence shows the claim is true.
- walked_back: the claimant retracted, corrected, or denied it.
- delayed: the planned event is happening later than claimed.
- never_happened: the planned event was cancelled or clearly will not happen.
- disputed: credible evidence or a credible party contradicts it, but it is not settled.
- no_change: the evidence is not strong enough to change anything.

Be strict. Confirm only on solid evidence: an official statement or document, the event plainly \
occurring, an admission, or independent verification. A denial by an interested party makes a claim \
disputed, not walked back, unless the original claimant retracts. Thin previews usually mean no_change.
Never present a prediction as settled. If unsure, choose no_change."""

DECIDE_SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {"type": "string"},
        "decision": {"type": "string", "enum": [
            "confirmed", "walked_back", "delayed", "never_happened", "disputed", "no_change"]},
    },
    "required": ["reason", "decision"],
    "additionalProperties": False,
}

SETTLING = {"confirms", "contradicts", "walked_back", "delayed", "did_not_happen"}
UPGRADABLE = {"reported", "unverified"}


def subject_words(text, claimant=""):
    """The words that say what a claim is ABOUT (not who reported it)."""
    return key_words(text) - ATTRIBUTION - key_words(claimant or "")


def candidates(conn, cfg, article):
    """Open claims this article might affect: shares 2+ subject words, newer than the claim's source."""
    since = (datetime.now(timezone.utc) - timedelta(days=cfg["claims"]["match_window_days"])).isoformat(timespec="seconds")
    words = subject_words(f"{article['title']} {article['snippet'] or ''}")
    rows = conn.execute(
        """
        SELECT c.*, a.published_at AS source_published, a.source_id AS claim_source_id
        FROM claims c JOIN articles a ON a.id = c.article_id
        WHERE c.status IN ('open', 'delayed') AND c.created_at >= ? AND c.article_id != ?
        """,
        (since, article["id"]),
    ).fetchall()
    scored = []
    for c in rows:
        if article["published_at"] <= c["source_published"]:
            continue  # evidence must come after the claim was made
        overlap = len(words & subject_words(c["text"], c["claimant"]))
        if overlap >= 2:
            scored.append((overlap, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[: cfg["claims"]["candidates_per_article"]]]


def _event(conn, claim_id, event, label, status, reason, article_id, decided_by):
    now = db.utcnow()
    conn.execute(
        "INSERT INTO claim_events (claim_id, at, event, label, status, reason, evidence_article_id, decided_by)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (claim_id, now, event, label, status, reason, article_id, decided_by),
    )
    resolved = status not in ("open", "not_tracked")
    conn.execute(
        "UPDATE claims SET label = ?, status = ?, updated_at = ?, resolved_at = CASE WHEN ? THEN ? ELSE resolved_at END"
        " WHERE id = ?",
        (label, status, now, int(resolved), now, claim_id),
    )
    conn.commit()


def apply_decision(claim, decision):
    """(new label, new status) for a Sonnet decision, or None for no change."""
    return {
        "confirmed": ("confirmed", "confirmed"),
        "walked_back": ("disputed", "walked_back"),
        "delayed": (claim["label"], "delayed"),
        "never_happened": (claim["label"], "never_happened"),
        "disputed": ("disputed", "open"),
    }.get(decision)


def evidence_text(conn, article):
    t = conn.execute(
        "SELECT summary FROM story_triage WHERE article_id = ? AND purpose = 'live'", (article["id"],)
    ).fetchone()
    body = t["summary"] if t else (article["snippet"] or "")
    return (f"Source: {article['source_name']} (type: {article['source_type']})\n"
            f"Published: {article['published_at'][:10]}\nHeadline: {article['title']}\n{body}")


def claim_brief(conn, c):
    lines = [f"Claim {c['id']}: {c['text']}",
             f"  label: {claims.LABELS[c['label']]} | status: {c['status']} | made: {c['source_published'][:10]}"
             + (f" | due: {c['due_date']}" if c["due_date"] else "")]
    for e in claims.history(conn, c["id"]):
        lines.append(f"  history {e['at'][:10]}: {e['event']} -> {e['label']}/{e['status']}: {e['reason']}")
    return "\n".join(lines)


def claim_number(raw):
    """'Claim 24', '24', '#24' -> 24 (None if there's no number)."""
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    return int(digits) if digits else None


def check_article(conn, cfg, article, budget):
    """Compare one new article with matching open claims. Returns the changes made."""
    found = candidates(conn, cfg, article)
    if not found or budget["haiku"] <= 0:
        return []
    budget["haiku"] -= 1
    prompt = (f"NEW ITEM\n{evidence_text(conn, article)}\n\nOPEN CLAIMS\n"
              + "\n\n".join(claim_brief(conn, c) for c in found))
    data, _ = ai.ask_json(conn, cfg, task="claim_match", role="bulk", system=MATCH_SYSTEM,
                          prompt=prompt, schema=MATCH_SCHEMA, story_id=article["story_id"])
    by_id = {c["id"]: c for c in found}
    changes = []
    for a in data["assessments"]:
        c = by_id.get(claim_number(a["claim_id"]))
        if c is None:
            continue
        rel = a["relation"]
        new_outlet = article["source_id"] != c["claim_source_id"]
        if rel == "supports" and a["independent"] and new_outlet and c["label"] in UPGRADABLE:
            reason = f"Independently reported by {article['source_name']}: {a['reason']}"
            _event(conn, c["id"], "label_change", "likely", c["status"], reason, article["id"], "haiku+rules")
            changes.append({"claim": c["text"], "change": "🟢 likely", "reason": reason})
        elif rel in SETTLING and budget["sonnet"] > 0:
            budget["sonnet"] -= 1
            verdict, _ = ai.ask_json(
                conn, cfg, task="claim_resolve", role="high_stakes", system=DECIDE_SYSTEM,
                prompt=(f"CLAIM AND HISTORY\n{claim_brief(conn, c)}\n\nNEW EVIDENCE\n{evidence_text(conn, article)}\n\n"
                        f"First-pass assessment: {rel} - {a['reason']}"),
                schema=DECIDE_SCHEMA, story_id=article["story_id"],
            )
            outcome = apply_decision(c, verdict["decision"])
            if outcome is None:  # still worth showing: the claim was checked against this evidence
                _event(conn, c["id"], "checked", c["label"], c["status"],
                       f"Checked against {article['source_name']}, no change: {verdict['reason']}",
                       article["id"], cfg["models"]["high_stakes"])
            if outcome:
                label, status = outcome
                event = "resolved" if status != "open" else "label_change"
                _event(conn, c["id"], event, label, status, verdict["reason"], article["id"], cfg["models"]["high_stakes"])
                changes.append({"claim": c["text"], "change": f"{status} / {label}", "reason": verdict["reason"],
                                "claim_id": c["id"]})
    return changes


def run(conn, cfg, after_id=None):
    """Check articles saved since the last run against open claims. Returns counts and changes.

    Progress is remembered by article id, so a round that hits its cost cap picks up
    exactly where it stopped next time.
    """
    key = "claims_checked_through_id"
    if after_id is None:
        saved = db.get_state(conn, key)
        if saved is None:  # first run: start from now, don't re-check history
            latest = conn.execute("SELECT COALESCE(MAX(id), 0) FROM articles").fetchone()[0]
            db.set_state(conn, key, str(latest))
            return {"articles": 0, "checked": 0, "changes": []}
        after_id = int(saved)
    budget = {"haiku": cfg["claims"]["max_haiku_checks_per_round"],
              "sonnet": cfg["claims"]["max_sonnet_checks_per_round"]}
    articles = conn.execute(
        """
        SELECT a.*, s.name AS source_name, s.type AS source_type FROM articles a
        JOIN sources s ON s.id = a.source_id WHERE a.id > ? ORDER BY a.id
        """,
        (after_id,),
    ).fetchall()
    changes, checked = [], 0
    for article in articles:
        if budget["haiku"] <= 0:
            break  # the rest wait for next round
        before = budget["haiku"]
        changes += check_article(conn, cfg, article, budget)
        checked += before - budget["haiku"]
        db.set_state(conn, key, str(article["id"]))
    return {"articles": len(articles), "checked": checked, "changes": changes}
