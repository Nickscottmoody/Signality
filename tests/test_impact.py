import json
import sqlite3

from signality import ai, db, impact, telegram
from signality.messages import Message, StoryCard

USER = "telegram:42"
CFG = {"impact_notes": {"enabled": True, "max_words": 45, "digest_max_notes": 2},
       "models": {"high_stakes": "claude-sonnet-5-5"}}


def memory_db(with_profile=True):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.migrate(conn)
    conn.execute("INSERT INTO stories (id, title, first_seen_at, last_seen_at) VALUES (1, 't', 'x', 'x'), "
                 "(2, 't', 'x', 'x'), (3, 't', 'x', 'x')")
    if with_profile:
        conn.execute("INSERT INTO users (id, platform, account_id, created_at) VALUES (1, 'telegram', '42', 'x')")
        conn.execute("INSERT INTO user_profiles VALUES (1, '{}', 'You study finance and want audit work.', 'x', 'x', 'x')")
    return conn


def card(story_id=1, headline="Big Four firm rolls out AI audit tool"):
    return StoryCard(story_id=story_id, headline=headline, summary="S.", why_it_matters="W.", label="reported",
                     label_reason="One outlet.", self_reported=False, partial=False, importance=70,
                     factors=dict(impact=4, breadth=3, urgency=3, novelty=3), topics=["jobs"],
                     sources=[("Reuters", "https://example.com")])


def fake_ai(monkeypatch, reply):
    calls = []

    def ask_json(conn, cfg, **kw):
        calls.append(kw)
        return reply, 0.004
    monkeypatch.setattr(ai, "ask_json", ask_json)
    return calls


def test_relevant_story_gets_a_note_and_is_never_paid_for_twice(monkeypatch):
    calls = fake_ai(monkeypatch, {"reason": "Audit goal.", "relevant": True,
                                  "connects_to": "career goal: audit", "note": "This could change entry-level audit work."})
    conn = memory_db()
    assert impact.for_story(conn, CFG, USER, card()) == "This could change entry-level audit work."
    assert impact.for_story(conn, CFG, USER, card()) == "This could change entry-level audit work."
    assert len(calls) == 1 and "You study finance" in calls[0]["prompt"]


def test_no_real_connection_means_no_note_but_the_skip_is_recorded(monkeypatch):
    calls = fake_ai(monkeypatch, {"reason": "Chip export news; no link to the profile.", "relevant": False,
                                  "connects_to": "", "note": ""})
    conn = memory_db()
    assert impact.for_story(conn, CFG, USER, card()) == ""
    assert impact.for_story(conn, CFG, USER, card()) == "" and len(calls) == 1
    row = conn.execute("SELECT note, reason FROM impact_notes").fetchone()
    assert row["note"] is None and "no link" in row["reason"]


def test_no_profile_or_switched_off_costs_nothing(monkeypatch):
    calls = fake_ai(monkeypatch, {})
    assert impact.for_story(memory_db(with_profile=False), CFG, USER, card()) == ""
    off = {**CFG, "impact_notes": {**CFG["impact_notes"], "enabled": False}}
    assert impact.for_story(memory_db(), off, USER, card()) == ""
    assert calls == []


def test_ai_failure_never_blocks_the_story(monkeypatch):
    def broken(*a, **k):
        raise ai.AIError("reply was not valid JSON")
    monkeypatch.setattr(ai, "ask_json", broken)
    assert impact.for_story(memory_db(), CFG, USER, card()) == ""


def test_digest_makes_one_call_and_keeps_only_valid_picks_up_to_the_cap(monkeypatch):
    calls = fake_ai(monkeypatch, {"notes": [
        {"item": "Story 2", "connects_to": "skills: SQL", "note": "Note for two."},
        {"item": "9", "connects_to": "x", "note": "Not a real item."},
        {"item": "1", "connects_to": "goal", "note": "Note for one."},
        {"item": "3", "connects_to": "goal", "note": "Over the cap of 2."}]})
    conn = memory_db()
    notes = impact.for_digest(conn, CFG, USER, [card(1), card(2), card(3)])
    assert len(calls) == 1 and notes == {2: "Note for two.", 1: "Note for one."}
    assert conn.execute("SELECT COUNT(*) FROM impact_notes WHERE kind = 'digest'").fetchone()[0] == 2


def test_overlong_notes_are_trimmed():
    long = " ".join(["word"] * 100)
    assert len(impact._trim(long, CFG).split()) == 45


def test_note_appears_after_why_it_matters_in_alerts_and_digest():
    c = card()
    c.impact_note = "This could change audit hiring."
    body = telegram.render_card(c, "alert")
    assert body.index("Why it matters") < body.index("🎯 <b>How it affects you:</b>") < body.index("🟡")
    assert "🎯 This could change audit hiring." in telegram.render_digest_item(1, c)
    plain = card()
    assert "🎯" not in telegram.render_card(plain, "alert") and "🎯" not in telegram.render_digest_item(1, plain)


def test_digest_only_asks_about_stories_that_fit_in_the_message(monkeypatch):
    from signality import delivery
    asked = []
    monkeypatch.setattr(impact, "for_digest", lambda conn, cfg, user, cards: asked.extend(cards) or {1: "Note."})
    monkeypatch.setenv("TELEGRAM_USER_ID", "42")
    cards = [card(i, "x" * 300) for i in range(1, 31)]
    message = Message(kind="digest", silent=True, title="Morning digest", text="30 stories.", cards=cards)
    delivery.add_impact_notes(None, CFG, message)
    assert 3 <= len(asked) < 30 and cards[0].impact_note == "Note." and cards[1].impact_note == ""
