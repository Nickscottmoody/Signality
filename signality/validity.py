"""Validity labels: how well-supported a story is, with the reason shown to the reader.

The label comes from rules in code, not from the model's opinion:
- what the triaged article's claims rest on (from triage)
- whether the organization itself published it (a primary source)
- how many INDEPENDENT outlets have reported it. An outlet repeating another
  outlet's report ("..., FT says") counts as one source, not two.

  ✅ confirmed   a primary source: the organization itself, or an official document
  🟢 likely      two or more independent outlets
  🟡 reported    one credible outlet
  🟠 unverified  rumor, leak, or social media, not yet confirmed
  🔴 disputed    denied or corrected
  💬 opinion     opinion/analysis: no factual label applies

Company claims about their own performance carry a separate "self-reported" flag.
"""
import re
from datetime import datetime, timedelta, timezone

from . import db

LABELS = {
    "confirmed": "✅ Confirmed",
    "likely": "🟢 Likely",
    "reported": "🟡 Reported",
    "unverified": "🟠 Unverified",
    "disputed": "🔴 Disputed",
    "opinion": "💬 Opinion",
}

# "Nvidia tells clients to trim China business, FT says" -> repeats the FT.
REPEAT_PATTERN = re.compile(
    r"([,:\-–—]\s*[A-Z][\w&.' ]{1,40}\s+(says|said|reports|reported)\s*$)"
    r"|\b(report says|reports say|according to (a |the )?report)\b",
    re.IGNORECASE,
)


def repeats_another_outlet(title):
    return bool(REPEAT_PATTERN.search(title))


def _names(names):
    return ", ".join(names[:-1]) + f" and {names[-1]}" if len(names) > 1 else names[0]


def decide(triage, articles):
    """Pick the label for one story.

    triage:   the story's triage row (content_type, sourcing, attributed_to, self_reported, article_id)
    articles: every article in the story, each with source_id, source_name, source_type, title, id
    Returns (label, reason, independent_outlet_count).
    """
    # Independent outlets: news/specialist sources that aren't just repeating someone else.
    independent = {}
    for a in articles:
        if a["source_type"] == "primary" or repeats_another_outlet(a["title"]):
            continue
        if (a["id"] == triage["article_id"] and triage["sourcing"] == "repeats_other_outlet"
                and (triage["attributed_to"] or "").strip().lower() not in a["source_name"].lower()):
            continue
        independent.setdefault(a["source_id"], a["source_name"])
    outlets = list(independent.values())
    primary = [a["source_name"] for a in articles if a["source_type"] == "primary"]
    read_from = next(a["source_name"] for a in articles if a["id"] == triage["article_id"])

    if triage["content_type"] == "opinion" or triage["sourcing"] == "not_applicable":
        return "opinion", "Opinion or analysis piece; no factual label applies.", len(outlets)
    if triage["sourcing"] == "denial_or_correction":
        return "disputed", f"The story concerns a denial or correction ({read_from}).", len(outlets)
    if primary:
        return "confirmed", f"Published by {primary[0]} itself.", len(outlets)
    if triage["sourcing"] == "official_source":
        return "confirmed", f"Based on an official statement or document, per {read_from}.", len(outlets)
    if len(outlets) >= 2:
        return "likely", f"Reported independently by {len(outlets)} outlets: {_names(outlets)}.", len(outlets)
    if triage["sourcing"] == "rumor_leak_social":
        return ("unverified", f"Based on a rumor, leak, or social-media post ({read_from}); not yet confirmed.",
                len(outlets))
    original = (triage["attributed_to"] or "").strip()
    cites_itself = original and (original.lower() in read_from.lower() or read_from.lower() in original.lower())
    if triage["sourcing"] == "repeats_other_outlet" and not cites_itself:
        return ("reported", f"{read_from} is relaying reporting from {original or 'another outlet'}; "
                            "counts as one source.", max(len(outlets), 1))
    if triage["sourcing"] == "anonymous_sources":
        return "reported", f"One outlet so far ({read_from}), citing unnamed sources.", len(outlets)
    return "reported", f"One outlet so far ({read_from}).", len(outlets)


def story_articles(conn, story_id):
    return conn.execute(
        """
        SELECT a.id, a.title, a.source_id, s.name AS source_name, s.type AS source_type
        FROM articles a JOIN sources s ON s.id = a.source_id WHERE a.story_id = ?
        """,
        (story_id,),
    ).fetchall()


def current(conn, story_id):
    """The story's latest label row, or None."""
    return conn.execute(
        "SELECT * FROM story_validity WHERE story_id = ? ORDER BY id DESC LIMIT 1", (story_id,)
    ).fetchone()


def update(conn, story_id):
    """Recompute a story's label; save a new history row only if it changed. Returns the label row."""
    triage = conn.execute(
        "SELECT * FROM story_triage WHERE story_id = ? AND purpose = 'live'", (story_id,)
    ).fetchone()
    if triage is None:
        return None
    label, reason, count = decide(triage, story_articles(conn, story_id))
    latest = current(conn, story_id)
    if latest is None or (latest["label"], latest["reason"]) != (label, reason):
        conn.execute(
            "INSERT INTO story_validity (story_id, label, reason, independent_outlets, self_reported, set_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (story_id, label, reason, count, triage["self_reported"], db.utcnow()),
        )
        conn.commit()
    return current(conn, story_id)


def refresh_recent(conn, cfg):
    """Re-label stories that gained articles recently (new outlets can upgrade a label)."""
    since = (datetime.now(timezone.utc) - timedelta(hours=cfg["dedup"]["window_hours"])).isoformat(timespec="seconds")
    rows = conn.execute(
        """
        SELECT DISTINCT a.story_id FROM articles a JOIN stories s ON s.id = a.story_id
        WHERE s.status = 'triaged' AND a.fetched_at >= ?
        """,
        (since,),
    ).fetchall()
    changed = 0
    for (story_id,) in rows:
        before = current(conn, story_id)
        after = update(conn, story_id)
        if before is None or after["id"] != before["id"]:
            changed += 1
    return changed
