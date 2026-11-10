"""Decides what reaches you, when, and how loudly.

  🚨 alert   importance >= alert threshold, Sonnet agrees, under the daily cap
  🔔 silent  importance >= silent threshold (or an alert Sonnet declined / over the cap);
             with delivery.silent_messages off, these wait for the digest instead
  📰 digest  importance >= digest threshold, sent once each morning
  stored     everything else: saved and searchable, never sent

Safety rules from the brief:
- 🟠 Unverified and 🔴 Disputed stories never go out on their own; they appear
  only in the morning digest, in a clearly labeled "Unconfirmed" section.
- Stories the triage marked "not AI" are never sent.
- Only fresh stories are sent right away; older ones wait for the digest.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import ai, alert_check, db, impact, messages, receipts, scoring, telegram, validity
from .dedup import key_words, related
from .settings import secret

UNCONFIRMED = ("unverified", "disputed")


def recipient():
    """Who receives messages: platform + account id (one user for now)."""
    return f"telegram:{secret('TELEGRAM_USER_ID')}"


def local_now(cfg):
    return datetime.now(ZoneInfo(cfg["digest"]["timezone"]))


def silent_messages_on(cfg):
    return cfg.get("delivery", {}).get("silent_messages", True)


def route(importance, label, cfg):
    """The tier a story is headed for, before the Sonnet check and the daily cap."""
    tier = scoring.tier(importance, cfg)
    if label in UNCONFIRMED and tier in ("alert", "silent"):
        return "digest"
    if tier == "silent" and not silent_messages_on(cfg):
        return "digest"
    return tier


def _send(conn, cfg, message, story_id=None, note=None):
    """Deliver one message and record it. Returns True if sent."""
    message_id = telegram.deliver(message, cfg)["message_id"]
    conn.execute(
        "INSERT INTO deliveries (story_id, recipient, kind, sent_at, local_date, channel_message_id, note)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (story_id, recipient(), message.kind, db.utcnow(), local_now(cfg).date().isoformat(),
         str(message_id), note),
    )
    conn.commit()
    return True


def alerts_sent_today(conn, cfg):
    return conn.execute(
        "SELECT COUNT(*) FROM deliveries WHERE recipient = ? AND kind = 'alert' AND local_date = ?",
        (recipient(), local_now(cfg).date().isoformat()),
    ).fetchone()[0]


def recently_alerted_on_same_saga(conn, headline, hours=24):
    """True if a 🚨 about a related story (same saga) went out in the last `hours`."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    words = key_words(headline)
    for (other,) in conn.execute(
        "SELECT t.headline FROM deliveries d JOIN story_triage t ON t.story_id = d.story_id AND t.purpose = 'live'"
        " WHERE d.kind = 'alert' AND d.recipient = ? AND d.sent_at >= ?", (recipient(), since),
    ):
        if related(words, key_words(other)):
            return True
    return False


def _alert_verdict(conn, cfg, story_id):
    """Sonnet's verdict (reusing an earlier one so we never pay twice). None if it couldn't run."""
    row = conn.execute(
        "SELECT send_as_alert, reason FROM alert_checks WHERE story_id = ? ORDER BY id DESC LIMIT 1", (story_id,)
    ).fetchone()
    if row:
        return {"send_as_alert": bool(row[0]), "reason": row[1]}
    try:
        return alert_check.check(conn, cfg, story_id)
    except (ai.BudgetExceeded, ai.AIError):
        return None


def send_immediate(conn, cfg):
    """Send 🚨 and 🔔 for fresh, undelivered stories. Returns counts."""
    since = (datetime.now(timezone.utc) - timedelta(hours=cfg["delivery"]["max_age_hours"])).isoformat(timespec="seconds")
    rows = conn.execute(
        """
        SELECT t.story_id, t.importance FROM story_triage t JOIN stories s ON s.id = t.story_id
        WHERE t.purpose = 'live' AND s.status = 'triaged' AND t.ai_related = 1 AND s.first_seen_at >= ?
          AND NOT EXISTS (SELECT 1 FROM deliveries d WHERE d.story_id = t.story_id AND d.recipient = ?)
        ORDER BY t.importance DESC
        """,
        (since, recipient()),
    ).fetchall()
    sent = {"alert": 0, "silent": 0}
    cap = cfg["importance"]["alert_cap_per_day"]
    for story_id, importance in rows:
        label = validity.update(conn, story_id)["label"]
        tier = route(importance, label, cfg)
        if tier not in ("alert", "silent"):
            continue
        note = ""
        if tier == "alert":
            headline = conn.execute(
                "SELECT headline FROM story_triage WHERE story_id = ? AND purpose = 'live'", (story_id,)
            ).fetchone()[0]
            if recently_alerted_on_same_saga(conn, headline):
                tier, note = "silent", "Related to an alert you already got today, so sent quietly."
            elif alerts_sent_today(conn, cfg) >= cap:
                tier, note = "silent", f"Alert-level story sent quietly: today's limit of {cap} alerts is reached."
            else:
                verdict = _alert_verdict(conn, cfg, story_id)
                if verdict is None:
                    tier, note = "silent", "Sent quietly: the alert double-check couldn't run."
                elif not verdict["send_as_alert"]:
                    tier = "silent"
                else:
                    note = f"Why this is an alert: {verdict['reason']}"
        if tier == "silent" and not silent_messages_on(cfg):
            continue  # not alert-worthy after all: it waits for the morning digest
        card = messages.story_card(conn, story_id)
        card.impact_note = impact.for_story(conn, cfg, recipient(), card, kind=tier)
        message = messages.Message(kind=tier, silent=tier != "alert", image="alert" if tier == "alert" else None,
                                   cards=[card], note=note)
        _send(conn, cfg, message, story_id=story_id, note=note or None)
        sent[tier] += 1
    return sent


def digest_since(conn, cfg):
    """Start of the digest window: the previous digest, or at most max_lookback_hours ago.

    Covering "since the last digest" means nothing slips through after a skipped day
    or a day the computer was off.
    """
    earliest = (datetime.now(timezone.utc) - timedelta(hours=cfg["digest"]["max_lookback_hours"])).isoformat(timespec="seconds")
    last = conn.execute(
        "SELECT MAX(sent_at) FROM deliveries WHERE kind = 'digest' AND recipient = ?", (recipient(),)
    ).fetchone()[0]
    return max(earliest, last) if last else earliest


def _alerts(conn, days=30):
    """Recent 🚨 alerts, newest first: (story_id, headline, message id, note)."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    return conn.execute(
        "SELECT d.story_id, t.headline, d.channel_message_id, d.note FROM deliveries d JOIN story_triage t"
        " ON t.story_id = d.story_id AND t.purpose = 'live' WHERE d.kind = 'alert' AND d.recipient = ?"
        " AND d.sent_at >= ? ORDER BY d.sent_at DESC",
        (recipient(), since),
    ).fetchall()


def attach_receipts_to_alerts(conn, cfg):
    """Receipts never arrive as a message of their own (Nicholas, Nov 10).

    A receipt for a saga you got a 🚨 about is added to that alert by EDITING it, which makes no
    notification. It's still listed in the next morning digest. Returns how many were attached.
    """
    alerts = _alerts(conn)
    if not alerts:
        return 0
    attached, touched = 0, {}
    for event_id in receipts.pending(conn, recipient()):
        if conn.execute("SELECT 1 FROM receipt_attachments WHERE claim_event_id = ? AND recipient = ?",
                        (event_id, recipient())).fetchone():
            continue
        r = receipts.card(conn, event_id)
        story_id = conn.execute("SELECT story_id FROM claims WHERE id = ?", (r.claim_id,)).fetchone()[0]
        words = key_words(r.story_headline or r.claim)
        alert = next((a for a in alerts if a["story_id"] == story_id or related(words, key_words(a["headline"]))), None)
        if alert is None:
            continue  # nothing to add it to: the digest carries it
        conn.execute(
            "INSERT INTO receipt_attachments (claim_event_id, recipient, story_id, channel_message_id, attached_at, edited)"
            " VALUES (?, ?, ?, ?, ?, 0)", (event_id, recipient(), alert["story_id"], alert["channel_message_id"], db.utcnow()))
        conn.commit()
        touched[alert["story_id"]] = alert
        attached += 1
    for story_id, alert in touched.items():  # one edit per alert, showing all its receipts so far
        events = [row[0] for row in conn.execute(
            "SELECT claim_event_id FROM receipt_attachments WHERE recipient = ? AND story_id = ? ORDER BY id",
            (recipient(), story_id))]
        card = messages.story_card(conn, story_id)
        card.impact_note = impact.stored_note(conn, recipient(), story_id, "alert")
        message = messages.Message(kind="alert", silent=True, image="alert", cards=[card], note=alert["note"] or "",
                                   receipts=[receipts.card(conn, e) for e in events])
        try:
            ok = telegram.update_delivered(message, alert["channel_message_id"], cfg)
        except Exception:
            ok = False  # the digest still carries every receipt
        conn.execute("UPDATE receipt_attachments SET edited = ? WHERE recipient = ? AND story_id = ?",
                     (int(ok), recipient(), story_id))
        conn.commit()
    return attached


def build_digest(conn, cfg):
    """The morning digest: undelivered stories since the last digest, best first."""
    since = digest_since(conn, cfg)
    rows = conn.execute(
        """
        SELECT t.story_id, t.importance FROM story_triage t JOIN stories s ON s.id = t.story_id
        WHERE t.purpose = 'live' AND s.status = 'triaged' AND t.ai_related = 1 AND s.first_seen_at >= ?
          AND t.importance >= ?
          AND NOT EXISTS (SELECT 1 FROM deliveries d WHERE d.story_id = t.story_id AND d.recipient = ?)
        ORDER BY t.importance DESC
        """,
        (since, cfg["importance"]["thresholds"]["digest"], recipient()),
    ).fetchall()
    confirmed, unconfirmed, picked = [], [], []
    for story_id, _ in rows:  # highest score first
        card = messages.story_card(conn, story_id)
        words = key_words(card.headline)
        lead = next((c for c, w in picked if related(words, w)), None)
        if lead is not None:  # same saga as a higher-ranked story: fold it in, don't repeat it
            lead.related_ids.append(story_id)
            continue
        picked.append((card, words))
        (unconfirmed if card.label in UNCONFIRMED else confirmed).append(card)
    confirmed = confirmed[: cfg["digest"]["max_items"]]
    today = local_now(cfg)
    text = (f"{len(confirmed)} stories worth knowing, highest first."
            + (f" Plus {len(unconfirmed)} unconfirmed, labeled at the end." if unconfirmed else ""))
    pending_receipts = [receipts.card(conn, e) for e in receipts.pending(conn, recipient())]
    if pending_receipts:
        text += f" {len(pending_receipts)} 🧾 receipt{'s' if len(pending_receipts) != 1 else ''}."
    return messages.Message(kind="digest", silent=True, image="normal",
                            title=f"📰 Morning digest · {today:%a, %b} {today.day}", text=text,
                            cards=confirmed, unconfirmed=unconfirmed, receipts=pending_receipts)


def add_impact_notes(conn, cfg, message):
    """"🎯 How it affects you" on the strongly relevant digest stories.

    Only stories that will fit in the one message are considered (no paying for notes nobody
    sees), and only confirmed ones: a rumor is never personalized.
    """
    _, shown, _ = telegram.fit_digest(message)
    notes = impact.for_digest(conn, cfg, recipient(), shown)
    for card in message.cards:
        card.impact_note = notes.get(card.story_id, "")


def maybe_send_digest(conn, cfg):
    """Send today's digest once, at or after the configured hour. Returns stories included."""
    now = local_now(cfg)
    key = f"digest_sent_{now.date().isoformat()}"
    if now.hour < cfg["digest"]["send_hour"] or db.get_state(conn, key):
        return 0
    message = build_digest(conn, cfg)
    add_impact_notes(conn, cfg, message)
    included = []
    if message.cards or message.unconfirmed or message.receipts:
        sent = telegram.deliver(message, cfg)
        included = sent["story_ids"]  # only the stories that fit in the one message
        receipts.mark_sent(conn, sent["receipt_event_ids"], recipient(), "digest", sent["message_id"])
        for story_id in included:
            conn.execute(
                "INSERT INTO deliveries (story_id, recipient, kind, sent_at, local_date, channel_message_id)"
                " VALUES (?, ?, 'digest', ?, ?, ?)",
                (story_id, recipient(), db.utcnow(), now.date().isoformat(), str(sent["message_id"])),
            )
        conn.commit()
    db.set_state(conn, key, db.utcnow())
    return len(included)


def budget_notices(conn, cfg):
    """Tell you once a month at 80% of the AI budget, and once if AI work pauses at 100%."""
    status = ai.budget_status(conn, cfg)
    month = local_now(cfg).strftime("%Y-%m")
    for level, needed, text in (
        ("over", status["over"],
         f"I've reached this month's AI budget (${status['cap']}), so I've paused summarizing and scoring "
         "until next month. I'm still collecting stories, so nothing will be missed."),
        ("warn", status["warn"],
         f"Heads up: I've used ${status['spent']:.2f} of this month's ${status['cap']} AI budget "
         f"({status['percent']:.0f}%). I'll keep going, and I'll pause automatically if I reach the cap."),
    ):
        key = f"budget_{level}_{month}"
        if needed and not db.get_state(conn, key):
            _send(conn, cfg, messages.Message(kind="notice", silent=False, image="normal",
                                              title="💵 Budget check", text=text))
            db.set_state(conn, key, db.utcnow())
            if level == "over":  # the 80% warning would be old news now
                db.set_state(conn, f"budget_warn_{month}", db.utcnow())
            return level
        if needed:
            return None  # already told you this month
    return None


def run(conn, cfg):
    """One delivery round: budget notices, immediate messages, then the digest if it's time."""
    notice = budget_notices(conn, cfg)
    sent = send_immediate(conn, cfg)
    attached = attach_receipts_to_alerts(conn, cfg)
    digest = maybe_send_digest(conn, cfg)
    return {**sent, "receipts": attached, "digest_items": digest, "budget_notice": notice}
