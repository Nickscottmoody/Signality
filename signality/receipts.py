"""🧾 Receipts: telling you when a tracked claim resolves.

A receipt is due for every claim_event that RESOLVED a claim (confirmed, walked
back, delayed, never happened). Each one reaches a recipient once: right away if
it belongs to a saga you got a 🚨 alert about, otherwise in the morning digest.
"""
from . import claims, db, messages

OUTCOMES = ("confirmed", "walked_back", "delayed", "never_happened")


def pending(conn, recipient):
    """Resolution events this recipient hasn't received yet, oldest first."""
    return [r[0] for r in conn.execute(
        f"""
        SELECT e.id FROM claim_events e
        WHERE e.event = 'resolved' AND e.status IN ({','.join('?' * len(OUTCOMES))})
          AND NOT EXISTS (SELECT 1 FROM claim_receipts r WHERE r.claim_event_id = e.id AND r.recipient = ?)
        ORDER BY e.id
        """,
        (*OUTCOMES, recipient),
    )]


def card(conn, event_id):
    e = conn.execute("SELECT * FROM claim_events WHERE id = ?", (event_id,)).fetchone()
    c = conn.execute("SELECT * FROM claims WHERE id = ?", (e["claim_id"],)).fetchone()
    first = claims.history(conn, c["id"])[0]
    link = lambda article_id: conn.execute(
        "SELECT s.name, a.url, a.published_at FROM articles a JOIN sources s ON s.id = a.source_id WHERE a.id = ?",
        (article_id,),
    ).fetchone()
    origin, evidence = link(c["article_id"]), link(e["evidence_article_id"])
    if evidence is None and e["evidence_web_result_id"]:  # evidence a web search found
        evidence = conn.execute(
            "SELECT outlet AS name, url, COALESCE(published_at, ?) AS published_at FROM web_results WHERE id = ?",
            (e["at"], e["evidence_web_result_id"]),
        ).fetchone()
    headline = conn.execute(
        "SELECT headline FROM story_triage WHERE story_id = ? AND purpose = 'live'", (c["story_id"],)
    ).fetchone()
    return messages.ReceiptCard(
        event_id=e["id"], claim_id=c["id"], claim=c["text"], claimant=c["claimant"] or "",
        first_label=first["label"], first_date=origin["published_at"][:10],
        first_source=(origin["name"], origin["url"]), outcome=e["status"],
        outcome_date=(evidence["published_at"] if evidence else e["at"])[:10], reason=e["reason"],
        evidence_source=(evidence["name"], evidence["url"]) if evidence else ("", ""),
        story_headline=headline[0] if headline else "",
    )


def mark_sent(conn, event_ids, recipient, via, message_id=None):
    for event_id in event_ids:
        conn.execute(
            "INSERT OR IGNORE INTO claim_receipts (claim_event_id, recipient, via, sent_at, channel_message_id)"
            " VALUES (?, ?, ?, ?, ?)",
            (event_id, recipient, via, db.utcnow(), str(message_id) if message_id else None),
        )
    conn.commit()
