""""🎯 How it affects you": a 1-2 sentence personal note on a story, from the reader's profile.

- 🚨 alerts (and 🔔 if switched on): one Sonnet call per story, skipped when there's no real connection.
- Digest: ONE Sonnet call looks at all the day's stories and writes notes only for the few
  that are strongly relevant (most days: few or none).
- Every decision is stored per user (impact_notes), skips included, so nothing is paid for
  twice and the notes can be reviewed.
- Notes are personal: they're never shown in a public channel.

Preview on recent stories without sending anything (Nicholas's task #10):
    ./.venv/bin/python -m signality.impact --preview 10
"""
import sys
from datetime import datetime, timedelta, timezone

from . import ai, db, messages, profile, users
from .dedup import key_words, related

RULES = """Rules for every note:
- The bar is high. Write a note only if this story touches something SPECIFIC in the profile \
(their field, job, a named career goal, a named skill or tool, a target industry's own work, their \
location, or a worry or hope they named) in a way that would not be true for most other readers. \
Ask: would this reader see their own situation differently because of this story?
- These do NOT qualify on their own: stock or valuation moves, "the market fell so hiring might \
slow", "big tech is investing in AI", or any link that would fit almost anyone who wants a tech job. \
When in doubt, skip: an empty note is better than a stretch.
- Only explain impact in the areas the reader asked for (career, money, daily life, learning).
- Never touch anything the profile marks off-limits.
- One or two sentences, no more. Name the part of the profile it connects to, and why.
- Lay out possibilities and trade-offs. Never tell the reader what to do (no "you should", \
"make sure to", "consider doing").
- Show uncertainty inside the sentence ("could", "might", "if this holds"). Don't add a separate \
sentence about sourcing: the story's validity label already shows that.
- Don't repeat the summary. Neutral, factual tone. Address the reader as "you"."""

SYSTEM_ONE = f"""You write the "🎯 How it affects you" note for Signality, a personal AI-news agent \
whose motto is "AI news with receipts": it gives evidence and the reader makes the decisions.

You get the reader's private profile and one news story. Decide whether the story has a real, \
specific connection to this reader. If yes, write 1-2 sentences. If not, set relevant to false \
and leave note empty.

{RULES}

reason: one short sentence on why you wrote or skipped the note (for the reader's review).
connects_to: the part of the profile it connects to (e.g. "career goal: audit at a Big Four firm"), \
or empty when skipped."""

SYSTEM_DIGEST = f"""You write "🎯 How it affects you" notes for Signality's morning digest, a \
personal AI-news agent whose motto is "AI news with receipts": it gives evidence and the reader \
makes the decisions.

You get the reader's private profile and the day's numbered stories. Pick ONLY the stories that \
are strongly and specifically relevant to this reader, up to the maximum given, and write a 1-2 \
sentence note for each. Most days only one or two stories qualify, sometimes none: return an \
empty list rather than stretch. If several stories make the same point, note only the best one. \
At most one note may end with a short question for the reader to think about.

{RULES}

For each note give: item (the story's number, as text), connects_to (the part of the profile), and note."""

SCHEMA_ONE = {
    "type": "object",
    "properties": {
        "reason": {"type": "string"},
        "relevant": {"type": "boolean"},
        "connects_to": {"type": "string"},
        "note": {"type": "string"},
    },
    "required": ["reason", "relevant", "connects_to", "note"],
    "additionalProperties": False,
}

SCHEMA_DIGEST = {
    "type": "object",
    "properties": {
        "notes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item": {"type": "string"},
                    "connects_to": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["item", "connects_to", "note"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["notes"],
    "additionalProperties": False,
}


def _story_text(card):
    return (f"Headline: {card.headline}\nSummary: {card.summary}\nWhy it matters: {card.why_it_matters}\n"
            f"Topics: {', '.join(card.topics)}\nValidity: {card.label_text}")


def _stored(conn, user_id, story_id, kind):
    return conn.execute("SELECT note FROM impact_notes WHERE user_id = ? AND story_id = ? AND kind = ?",
                        (user_id, story_id, kind)).fetchone()


def stored_note(conn, user_key, story_id, kind="alert"):
    """The note already written for this story ('' if none). Never calls the AI."""
    row = _stored(conn, users.get_or_create(conn, user_key), story_id, kind)
    return (row[0] or "") if row else ""


def _store(conn, cfg, user_id, story_id, kind, note, connects_to, reason):
    conn.execute(
        "INSERT INTO impact_notes (user_id, story_id, kind, note, connects_to, reason, model, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(user_id, story_id, kind) DO UPDATE SET"
        " note = excluded.note, connects_to = excluded.connects_to, reason = excluded.reason,"
        " model = excluded.model, created_at = excluded.created_at",
        (user_id, story_id, kind, note or None, connects_to or None, reason or None,
         cfg["models"]["high_stakes"], db.utcnow()),
    )
    conn.commit()


def _trim(note, cfg):
    """Keep a note to about max_words (a safety net; the prompt already asks for 1-2 sentences)."""
    words = note.split()
    limit = cfg["impact_notes"]["max_words"]
    return note.strip() if len(words) <= limit * 1.3 else " ".join(words[:limit]).rstrip(",;:") + "…"


def _profile_text(conn, user_key):
    row = profile.get(conn, user_key)
    return row["summary"] if row else None


def for_story(conn, cfg, user_key, card, kind="alert"):
    """The note for one 🚨/🔔 story, or '' (no profile, no real connection, or AI unavailable)."""
    if not cfg.get("impact_notes", {}).get("enabled"):
        return ""
    summary = _profile_text(conn, user_key)
    if not summary:
        return ""
    user_id = users.get_or_create(conn, user_key)
    done = _stored(conn, user_id, card.story_id, kind)
    if done is not None:
        return done[0] or ""
    # "Sometimes end with a question": about one note in three may, decided here so it really is "sometimes".
    question = ("You may end with one short question for the reader to think about." if card.story_id % 3 == 0
                else "Do not end with a question.")
    prompt = (f"Note length: at most {cfg['impact_notes']['max_words']} words. {question}\n\n"
              f"Reader's profile:\n{summary}\n\nStory:\n{_story_text(card)}")
    try:
        data, _cost = ai.ask_json(conn, cfg, task="impact_note", role="high_stakes", system=SYSTEM_ONE,
                                  prompt=prompt, schema=SCHEMA_ONE, story_id=card.story_id)
    except (ai.AIError, ai.BudgetExceeded):
        return ""  # never hold up a story for its personal note
    note = _trim(data["note"], cfg) if data["relevant"] and data["note"].strip() else ""
    _store(conn, cfg, user_id, card.story_id, kind, note, data["connects_to"] if note else "", data["reason"])
    return note


def for_digest(conn, cfg, user_key, cards):
    """Notes for the strongly relevant digest stories: {story_id: note}. One AI call for the batch."""
    if not cfg.get("impact_notes", {}).get("enabled") or not cards:
        return {}
    summary = _profile_text(conn, user_key)
    if not summary:
        return {}
    user_id = users.get_or_create(conn, user_key)
    numbered = "\n\n".join(f"Story {i}:\n{_story_text(c)}" for i, c in enumerate(cards, 1))
    limit = cfg["impact_notes"]
    prompt = (f"Maximum notes: {limit['digest_max_notes']}. Each note at most {limit['max_words']} words.\n\n"
              f"Reader's profile:\n{summary}\n\nToday's stories:\n\n{numbered}")
    try:
        data, _cost = ai.ask_json(conn, cfg, task="impact_digest", role="high_stakes", system=SYSTEM_DIGEST,
                                  prompt=prompt, schema=SCHEMA_DIGEST)
    except (ai.AIError, ai.BudgetExceeded):
        return {}
    notes = {}
    for item in data["notes"]:
        if len(notes) == limit["digest_max_notes"]:
            break
        digits = "".join(ch for ch in item["item"] if ch.isdigit())  # "Story 3" -> 3
        if not digits or not 1 <= int(digits) <= len(cards) or not item["note"].strip():
            continue
        card = cards[int(digits) - 1]
        if card.story_id in notes:
            continue
        notes[card.story_id] = _trim(item["note"], cfg)
        _store(conn, cfg, user_id, card.story_id, "digest", notes[card.story_id], item["connects_to"],
               "picked as strongly relevant in the digest")
    return notes


def preview(conn, cfg, user_key, count=10):
    """Write notes for recent top stories without sending anything. Returns [(card, note, reason)].

    Uses stories first seen more than 12 hours ago, so nothing here could become a live alert.
    """
    now = datetime.now(timezone.utc)
    rows = conn.execute(
        """
        SELECT t.story_id FROM story_triage t JOIN stories s ON s.id = t.story_id
        WHERE t.purpose = 'live' AND s.status = 'triaged' AND t.ai_related = 1
          AND s.first_seen_at BETWEEN ? AND ?
        ORDER BY t.importance DESC LIMIT ?
        """,
        ((now - timedelta(days=3)).isoformat(timespec="seconds"),
         (now - timedelta(hours=12)).isoformat(timespec="seconds"), count * 3),
    ).fetchall()
    picked, seen = [], []
    for (story_id,) in rows:  # one story per saga, so the preview covers different news
        card = messages.story_card(conn, story_id)
        words = key_words(card.headline)
        if any(related(words, w) for w in seen):
            continue
        seen.append(words)
        picked.append(card)
        if len(picked) == count:
            break
    out = []
    user_id = users.get_or_create(conn, user_key)
    for card in picked:
        note = for_story(conn, cfg, user_key, card, kind="preview")
        reason = conn.execute("SELECT reason FROM impact_notes WHERE user_id = ? AND story_id = ? AND kind = 'preview'",
                              (user_id, card.story_id)).fetchone()
        out.append((card, note, reason[0] if reason else ""))
    return out


def main():
    from .settings import load_config, secret
    cfg = load_config()
    conn = db.connect(cfg["storage"]["db_path"])
    count = int(sys.argv[sys.argv.index("--preview") + 1]) if "--preview" in sys.argv else 10
    user_key = f"telegram:{secret('TELEGRAM_USER_ID')}"
    if profile.get(conn, user_key) is None:
        print("No profile yet. Do /profile in Telegram first.")
        return
    spent_before = ai.month_spend(conn)
    results = preview(conn, cfg, user_key, count)
    for i, (card, note, reason) in enumerate(results, 1):
        print(f"{i}. [{card.importance}] {card.headline}")
        print(f"   🎯 {note}" if note else "   (skipped)")
        print(f"   why: {reason}\n")
    written = sum(1 for _, n, _ in results if n)
    print(f"{written} of {len(results)} stories got a note · cost ${ai.month_spend(conn) - spent_before:.4f}")


if __name__ == "__main__":
    main()
