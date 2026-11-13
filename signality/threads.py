"""Developing stories ("threads"): one saga followed across many articles.

The Nvidia CEO affair produced 70+ different stories in one day. They aren't the
same event (so they aren't merged as duplicates), but they belong together. A
thread links them so Siggy can:
- tell you what's NEW in a story you've already heard about ("🔄 Update: ..."),
- rate how new a story is against what the saga already said,
- reply to your original 🚨 instead of starting over, at most once a day per saga.

How a story joins a thread: during triage (the same Haiku call, no extra cost),
Haiku is shown the few active threads whose headlines share words with the story
and picks the one it continues, or none. Code checks the pick is one it was shown.

Threads are shared news data. Whether a story is an "update" for a particular
person depends on what THEY were already sent, so that is worked out per user.

Give recent stories threads (one-time, after this feature was added):
    ./.venv/bin/python -m signality.threads --backfill 4
"""
import argparse
import re
from datetime import datetime, timedelta, timezone

from . import ai, db
from .dedup import key_words, related, strip_outlet_suffix
from .settings import load_config


def settings(cfg):
    return cfg.get("threads", {})


def enabled(cfg):
    return settings(cfg).get("enabled", False)


def candidates(conn, cfg, title, exclude_story=None):
    """Active threads whose headlines share distinctive words with `title`, best match first.

    Returns [{"id", "title", "latest": [(headline, whats_new, date), ...]}].
    """
    s = settings(cfg)
    since = (datetime.now(timezone.utc) - timedelta(days=s.get("active_days", 7))).isoformat(timespec="seconds")
    words = key_words(strip_outlet_suffix(title))
    rows = conn.execute(
        """
        SELECT th.id AS thread_id, th.title AS thread_title, th.last_story_at, t.headline, t.whats_new,
               st.first_seen_at
        FROM threads th JOIN stories st ON st.thread_id = th.id
        JOIN story_triage t ON t.story_id = st.id AND t.purpose = 'live'
        WHERE th.last_story_at >= ? AND st.id != ?
        ORDER BY st.first_seen_at DESC
        """,
        (since, exclude_story or 0),
    ).fetchall()
    found = {}
    for r in rows:
        shared = len(words & (key_words(r["headline"]) | key_words(r["thread_title"])))
        th = found.setdefault(r["thread_id"], {"id": r["thread_id"], "title": r["thread_title"], "best": 0,
                                               "last": r["last_story_at"], "latest": []})
        th["best"] = max(th["best"], shared)
        if len(th["latest"]) < 3:  # newest first
            th["latest"].append((r["headline"], r["whats_new"] or "", r["first_seen_at"][:10]))
    good = [t for t in found.values() if t["best"] >= s.get("min_shared_words", 2)]
    good.sort(key=lambda t: (t["best"], t["last"]), reverse=True)
    return good[: s.get("candidates", 3)]


def prompt_lines(threads):
    """The part of a triage prompt that shows the candidate threads."""
    lines = ["Developing stories Signality is following (this item may continue one):"]
    for t in threads:
        lines.append(f"  Thread {t['id']}: {t['title']}")
        lines += [f"    {date}: {headline}" for headline, _, date in t["latest"]]
    if not threads:
        lines.append("  none")
    return lines


def picked(answer, threads):
    """The thread id Haiku picked, if it is one it was shown; else None."""
    m = re.search(r"\d+", answer or "")
    if m and int(m.group()) in {t["id"] for t in threads}:
        return int(m.group())
    return None


def assign(conn, story_id, thread_id, headline):
    """Put a story in a thread (an existing one, or a new one when thread_id is None). Returns the id."""
    now = db.utcnow()
    if thread_id is None:
        thread_id = conn.execute(
            "INSERT INTO threads (title, started_at, last_story_at, story_count) VALUES (?, ?, ?, 1)",
            (headline, now, now)).lastrowid
    else:
        conn.execute("UPDATE threads SET last_story_at = ?, story_count = story_count + 1 WHERE id = ?",
                     (now, thread_id))
    conn.execute("UPDATE stories SET thread_id = ? WHERE id = ?", (thread_id, story_id))
    conn.commit()
    return thread_id


def thread_of(conn, story_id):
    row = conn.execute("SELECT thread_id FROM stories WHERE id = ?", (story_id,)).fetchone()
    return row[0] if row else None


# --- Per user: what counts as an update for THIS person ------------------------

def seen_before(conn, recipient, story_id, before=None):
    """True if this person was already sent another story from the same thread (before `before`)."""
    thread_id = thread_of(conn, story_id)
    if thread_id is None:
        return False
    sql = ("SELECT 1 FROM deliveries d JOIN stories s ON s.id = d.story_id"
           " WHERE s.thread_id = ? AND d.story_id != ? AND d.recipient = ?")
    args = [thread_id, story_id, recipient]
    if before:
        sql, args = sql + " AND d.sent_at < ?", args + [before]
    return conn.execute(sql + " LIMIT 1", args).fetchone() is not None


def update_line(conn, recipient, story_id, before=None):
    """"What's new" for a story in a saga this person already heard about; "" otherwise."""
    if not seen_before(conn, recipient, story_id, before):
        return ""
    row = conn.execute("SELECT whats_new FROM story_triage WHERE story_id = ? AND purpose = 'live'",
                       (story_id,)).fetchone()
    return (row[0] or "") if row else ""


ALERT_SQL = ("SELECT d.id, d.channel_message_id, d.sent_at, t.headline, s.thread_id FROM deliveries d"
             " JOIN stories s ON s.id = d.story_id JOIN story_triage t ON t.story_id = d.story_id AND t.purpose = 'live'"
             " WHERE d.recipient = ? AND d.kind = 'alert' AND d.update_of IS NULL AND d.story_id != ?")


def first_alert(conn, recipient, story_id, related_hours=24):
    """The original 🚨 this story would be an update to, or None.

    That's the first alert on the story's own thread. Failing that, a recent alert whose headline shares
    distinctive words with it: one big saga can split into side threads (market reaction, succession,
    export rules), and those should still count as updates, not fresh alerts.
    """
    thread_id = thread_of(conn, story_id)
    if thread_id is not None:
        row = conn.execute(ALERT_SQL + " AND s.thread_id = ? ORDER BY d.sent_at LIMIT 1",
                           (recipient, story_id, thread_id)).fetchone()
        if row:
            return row
    headline = conn.execute("SELECT headline FROM story_triage WHERE story_id = ? AND purpose = 'live'",
                            (story_id,)).fetchone()
    if not headline:
        return None
    since = (datetime.now(timezone.utc) - timedelta(hours=related_hours)).isoformat(timespec="seconds")
    words = key_words(headline[0])
    return next((r for r in conn.execute(ALERT_SQL + " AND d.sent_at >= ? ORDER BY d.sent_at",
                                         (recipient, story_id, since))
                 if related(words, key_words(r["headline"]))), None)


def update_alerts_on(conn, recipient, original_id, local_date):
    """How many 🚨 updates replying to the original alert `original_id` this person got on `local_date`."""
    return conn.execute(
        "SELECT COUNT(*) FROM deliveries WHERE recipient = ? AND kind = 'alert' AND update_of = ? AND local_date = ?",
        (recipient, original_id, local_date),
    ).fetchone()[0]


# --- One-time backfill for stories triaged before threads existed --------------

BACKFILL_SYSTEM = """You sort AI news stories into developing stories (sagas). You get one story and \
the developing stories it might continue, each with its latest headlines.

continues_thread: the id of the developing story this one adds to (e.g. "Thread 12"): the same saga, \
meaning the same people, company, deal, or event, even from a new angle (reaction, analysis, \
fallout). "none" if it is a different story that merely mentions the same company or topic, or \
only shares a broad trend (AI demand, the AI market, AI stocks): a saga is one specific chain of events.
whats_new: if it continues a thread, one short sentence saying what this story adds that the \
thread's latest headlines don't already say; if it adds no new facts (analysis, reaction, recap), \
say so plainly, e.g. "No new facts: analysis of what the ouster means for AI chip sales." Empty \
when continues_thread is "none"."""

BACKFILL_SCHEMA = {
    "type": "object",
    "properties": {"continues_thread": {"type": "string"}, "whats_new": {"type": "string"}},
    "required": ["continues_thread", "whats_new"],
    "additionalProperties": False,
}


def backfill(conn, cfg, days=4, dry_run=False):
    """Give threads to recent stories that have none, oldest first. Returns counts and cost."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    rows = conn.execute(
        """
        SELECT s.id, t.headline, t.summary, s.first_seen_at FROM stories s
        JOIN story_triage t ON t.story_id = s.id AND t.purpose = 'live'
        WHERE s.status = 'triaged' AND t.ai_related = 1 AND s.thread_id IS NULL AND s.first_seen_at >= ?
        ORDER BY s.first_seen_at
        """,
        (since,),
    ).fetchall()
    stats = {"stories": len(rows), "joined": 0, "new": 0, "asked": 0, "cost_usd": 0.0}
    for r in rows:
        options = candidates(conn, cfg, r["headline"], exclude_story=r["id"])
        thread_id, whats_new = None, ""
        if options:
            prompt = "\n".join([f"Story ({r['first_seen_at'][:10]}): {r['headline']}", r["summary"], "",
                                *prompt_lines(options)])
            if dry_run:
                print(prompt, "\n")
                continue
            data, cost = ai.ask_json(conn, cfg, task="thread_backfill", role="bulk", story_id=r["id"],
                                     system=BACKFILL_SYSTEM, prompt=prompt, schema=BACKFILL_SCHEMA)
            stats["asked"] += 1
            stats["cost_usd"] += cost
            thread_id = picked(data["continues_thread"], options)
            whats_new = data["whats_new"].strip() if thread_id else ""
        if dry_run:
            continue
        assign(conn, r["id"], thread_id, r["headline"])
        if thread_id:  # backfilled stories keep their first-seen time, not "now"
            conn.execute("UPDATE threads SET last_story_at = ? WHERE id = ?", (r["first_seen_at"], thread_id))
        else:
            conn.execute("UPDATE threads SET started_at = ?, last_story_at = ? WHERE id = ?",
                         (r["first_seen_at"], r["first_seen_at"], thread_of(conn, r["id"])))
        conn.execute("UPDATE story_triage SET whats_new = ? WHERE story_id = ? AND purpose = 'live'",
                     (whats_new or None, r["id"]))
        conn.commit()
        stats["joined" if thread_id else "new"] += 1
    return stats


def main():
    p = argparse.ArgumentParser(description="Developing stories (threads).")
    p.add_argument("--backfill", type=int, metavar="DAYS", help="give threads to stories from the last DAYS days")
    p.add_argument("--dry-run", action="store_true", help="show what would be asked, change nothing")
    p.add_argument("--show", type=int, metavar="N", default=0, help="list the N busiest active threads")
    args = p.parse_args()
    cfg = load_config()
    conn = db.connect(cfg["storage"]["db_path"])
    if args.backfill:
        print(backfill(conn, cfg, args.backfill, args.dry_run))
    if args.show:
        for th in conn.execute("SELECT id, title, story_count, last_story_at FROM threads"
                               " ORDER BY story_count DESC LIMIT ?", (args.show,)):
            print(f"Thread {th['id']} · {th['story_count']} stories · last {th['last_story_at'][:16]} · {th['title']}")
            for s in conn.execute("SELECT t.headline, t.whats_new FROM stories s JOIN story_triage t"
                                  " ON t.story_id = s.id AND t.purpose = 'live' WHERE s.thread_id = ?"
                                  " ORDER BY s.first_seen_at DESC LIMIT 5", (th["id"],)):
                print(f"    - {s['headline']}" + (f"\n      🔄 {s['whats_new']}" if s["whats_new"] else ""))


if __name__ == "__main__":
    main()
