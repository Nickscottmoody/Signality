"""Decides what reaches you, when, and how loudly.

  🚨 alert   importance >= alert threshold, Sonnet agrees, under the daily cap
  🔔 silent  importance >= silent threshold (or an alert Sonnet declined / over the cap)
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

from . import ai, alert_check, db, messages, scoring, telegram, validity
from .settings import secret

UNCONFIRMED = ("unverified", "disputed")


def recipient():
    """Who receives messages: platform + account id (one user for now)."""
    return f"telegram:{secret('TELEGRAM_USER_ID')}"


def local_now(cfg):
    return datetime.now(ZoneInfo(cfg["digest"]["timezone"]))


def route(importance, label, cfg):
    """The tier a story is headed for, before the Sonnet check and the daily cap."""
    tier = scoring.tier(importance, cfg)
    if label in UNCONFIRMED and tier in ("alert", "silent"):
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
            if alerts_sent_today(conn, cfg) >= cap:
                tier, note = "silent", f"Alert-level story sent quietly: today's limit of {cap} alerts is reached."
            else:
                verdict = _alert_verdict(conn, cfg, story_id)
                if verdict is None:
                    tier, note = "silent", "Sent quietly: the alert double-check couldn't run."
                elif not verdict["send_as_alert"]:
                    tier = "silent"
                else:
                    note = f"Why this is an alert: {verdict['reason']}"
        card = messages.story_card(conn, story_id)
        message = messages.Message(kind=tier, silent=tier != "alert", image="alert" if tier == "alert" else None,
                                   cards=[card], note=note)
        _send(conn, cfg, message, story_id=story_id, note=note or None)
        sent[tier] += 1
    return sent


def build_digest(conn, cfg):
    """The morning digest: undelivered stories from the lookback window, best first."""
    since = (datetime.now(timezone.utc) - timedelta(hours=cfg["digest"]["lookback_hours"])).isoformat(timespec="seconds")
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
    confirmed, unconfirmed = [], []
    for story_id, _ in rows:
        card = messages.story_card(conn, story_id)
        (unconfirmed if card.label in UNCONFIRMED else confirmed).append(card)
    confirmed = confirmed[: cfg["digest"]["max_items"]]
    today = local_now(cfg)
    text = (f"{len(confirmed)} stories worth knowing, highest first."
            + (f" Plus {len(unconfirmed)} unconfirmed, labeled at the end." if unconfirmed else ""))
    return messages.Message(kind="digest", silent=True, image="normal",
                            title=f"📰 Morning digest · {today:%a, %b} {today.day}", text=text,
                            cards=confirmed, unconfirmed=unconfirmed)


def maybe_send_digest(conn, cfg):
    """Send today's digest once, at or after the configured hour. Returns stories included."""
    now = local_now(cfg)
    key = f"digest_sent_{now.date().isoformat()}"
    if now.hour < cfg["digest"]["send_hour"] or db.get_state(conn, key):
        return 0
    message = build_digest(conn, cfg)
    included = []
    if message.cards or message.unconfirmed:
        sent = telegram.deliver(message, cfg)
        included = sent["story_ids"]  # only the stories that fit in the one message
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
    digest = maybe_send_digest(conn, cfg)
    return {**sent, "digest_items": digest, "budget_notice": notice}
