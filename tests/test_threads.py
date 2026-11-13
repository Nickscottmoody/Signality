import sqlite3
from datetime import datetime, timedelta, timezone

from signality import db, delivery, messages, telegram, threads, triage

CFG = {
    "threads": {"enabled": True, "active_days": 7, "candidates": 3, "min_shared_words": 2,
                "update_alerts_per_day": 1},
    "importance": {"thresholds": {"alert": 65, "silent": 50, "digest": 25}, "alert_cap_per_day": 5,
                   "weights": {"impact": 0.35, "breadth": 0.25, "urgency": 0.2, "novelty": 0.2}},
    "delivery": {"max_age_hours": 12, "silent_messages": False},
    "digest": {"timezone": "America/Chicago", "max_lookback_hours": 48, "max_items": 15},
    "topics": {"jobs": 1.1},
    "models": {"bulk": "claude-haiku-5-5"},
    "triage": {"fetch_full_text": False, "dedup_candidates": 8},
    "dedup": {"window_hours": 72},
}


def ago(**d):
    return (datetime.now(timezone.utc) - timedelta(**d)).isoformat(timespec="seconds")


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.migrate(conn)
    conn.execute("INSERT INTO sources (id, name, url, type, added_at) VALUES ('ft','FT','u','news','t')")
    return conn


def _story(conn, sid, headline, importance=50, thread=None, whats_new=None, seen=None):
    seen = seen or ago(hours=1)
    conn.execute("INSERT INTO stories (id, title, first_seen_at, last_seen_at, status, thread_id)"
                 " VALUES (?, ?, ?, ?, 'triaged', ?)", (sid, headline, seen, seen, thread))
    conn.execute("INSERT INTO articles (id, source_id, story_id, guid, url, title, title_words, snippet, published_at,"
                 " fetched_at) VALUES (?, 'ft', ?, ?, ?, ?, '', 'snippet', ?, ?)",
                 (sid, sid, f"g{sid}", f"https://ft.com/{sid}", headline, seen, seen))
    conn.execute(
        "INSERT INTO story_triage (story_id, article_id, model, created_at, text_source, headline, summary,"
        " why_it_matters, topics, content_type, sourcing, self_reported, impact, impact_reason, breadth,"
        " breadth_reason, urgency, urgency_reason, novelty, novelty_reason, base_score, topic_multiplier,"
        " importance, cost_usd, whats_new) VALUES (?, ?, 'm', 't', 'full', ?, 's', 'w', '[]', 'news', 'x', 0,"
        " 3, 'r', 3, 'r', 3, 'r', 3, 'r', 50, 1, ?, 0, ?)", (sid, sid, headline, importance, whats_new))


def _thread(conn, tid, title, last=None):
    conn.execute("INSERT INTO threads (id, title, started_at, last_story_at) VALUES (?, ?, ?, ?)",
                 (tid, title, last or ago(hours=2), last or ago(hours=2)))


# --- finding the developing story a new story might continue ---

def test_candidates_need_shared_words_and_an_active_thread():
    conn = _db()
    _thread(conn, 1, "Nvidia CEO Jensen Huang admits affair")
    _story(conn, 10, "Nvidia CEO Jensen Huang admits affair", thread=1)
    _thread(conn, 2, "Anthropic sets IPO price range")
    _story(conn, 20, "Anthropic sets IPO price range", thread=2)
    _thread(conn, 3, "Jensen Huang keynote at Computex", last=ago(days=30))  # gone quiet
    _story(conn, 30, "Jensen Huang keynote at Computex", thread=3, seen=ago(days=30))
    found = threads.candidates(conn, CFG, "Nvidia names Colette Kress interim CEO after Jensen Huang exit - Reuters")
    assert [t["id"] for t in found] == [1]
    assert found[0]["latest"][0][0] == "Nvidia CEO Jensen Huang admits affair"
    assert threads.candidates(conn, CFG, "Nvidia ships new chips") == []  # one shared word isn't enough


def test_only_a_thread_haiku_was_shown_can_be_picked():
    shown = [{"id": 12}]
    assert threads.picked("Thread 12", shown) == 12
    assert threads.picked("none", shown) is None
    assert threads.picked("Thread 99", shown) is None


def test_triage_puts_story_in_its_thread_with_whats_new(monkeypatch):
    conn = _db()
    _thread(conn, 1, "Nvidia CEO Jensen Huang admits affair")
    _story(conn, 10, "Nvidia CEO Jensen Huang admits affair", thread=1)
    conn.execute("INSERT INTO stories (id, title, first_seen_at, last_seen_at) VALUES (11, 'x', ?, ?)", (ago(), ago()))
    conn.execute("INSERT INTO articles (id, source_id, story_id, guid, url, title, title_words, snippet, published_at,"
                 " fetched_at) VALUES (11, 'ft', 11, 'g11', 'https://ft.com/11',"
                 " 'Nvidia board ousts CEO Jensen Huang', 'nvidia board ousts ceo jensen huang', 's', ?, ?)",
                 (ago(), ago()))
    prompts = []
    factor = {"score": 4, "reason": "r"}
    answer = {"same_event_as": "none", "continues_thread": "Thread 1",
              "whats_new": "The board removed Huang as CEO.", "headline": "Nvidia board ousts Jensen Huang",
              "summary": "s", "why_it_matters": "w", "topics": [], "content_type": "news",
              "sourcing": "on_record_reporting", "attributed_to": "", "self_reported": False, "ai_related": True,
              "impact": factor, "breadth": factor, "urgency": factor, "novelty": factor, "claims": []}
    monkeypatch.setattr(triage.ai, "ask_json", lambda *a, **k: prompts.append(k["prompt"]) or (answer, 0.001))
    triage.triage_story(conn, CFG, 11)
    assert "Thread 1: Nvidia CEO Jensen Huang admits affair" in prompts[0]
    assert threads.thread_of(conn, 11) == 1
    assert conn.execute("SELECT whats_new FROM story_triage WHERE story_id = 11").fetchone()[0] == \
        "The board removed Huang as CEO."
    assert conn.execute("SELECT story_count FROM threads WHERE id = 1").fetchone()[0] == 2


# --- what reaches the reader ---

def _card(conn, sid):
    t = conn.execute("SELECT headline, importance FROM story_triage WHERE story_id = ?", (sid,)).fetchone()
    return messages.StoryCard(story_id=sid, headline=t[0], summary="s", why_it_matters="w", label="reported",
                              label_reason="r", self_reported=False, partial=False, importance=t[1],
                              factors={"impact": 4, "breadth": 3, "urgency": 4, "novelty": 3}, topics=[],
                              sources=[("FT", "https://ft.com")])


def _wire(monkeypatch, conn, sent, updates_seen):
    monkeypatch.setattr(delivery, "recipient", lambda: "telegram:1")
    monkeypatch.setattr(delivery.validity, "update", lambda conn, sid: {"label": "reported"})
    monkeypatch.setattr(delivery.messages, "story_card", lambda conn, sid: _card(conn, sid))
    monkeypatch.setattr(delivery.impact, "for_story", lambda *a, **k: "")
    monkeypatch.setattr(delivery.alert_check, "check",
                        lambda conn, cfg, sid, update=None: updates_seen.append(update) or
                        {"send_as_alert": True, "reason": "big"})
    monkeypatch.setattr(delivery.telegram, "deliver",
                        lambda m, cfg: sent.append(m) or {"message_id": 100 + len(sent), "story_ids": []})


def test_update_alert_replies_to_first_alert_and_only_once_a_day(monkeypatch):
    conn = _db()
    sent, updates_seen = [], []
    _wire(monkeypatch, conn, sent, updates_seen)
    _thread(conn, 1, "Nvidia CEO Jensen Huang admits affair")
    _story(conn, 10, "Nvidia CEO Jensen Huang admits affair", importance=70, thread=1)
    conn.execute("INSERT INTO deliveries (story_id, recipient, kind, sent_at, local_date, channel_message_id)"
                 " VALUES (10, 'telegram:1', 'alert', ?, '2026-11-12', '55')", (ago(hours=1),))
    _story(conn, 11, "Nvidia board ousts Jensen Huang", importance=80, thread=1,
           whats_new="The board removed Huang as CEO.")
    _story(conn, 12, "Analysis: what Huang's exit means for Nvidia", importance=75, thread=1,
           whats_new="No new facts: analysis.")
    counts = delivery.send_immediate(conn, CFG)
    assert counts["alert"] == 1 and len(sent) == 1  # the second update waits for the digest
    alert = sent[0]
    assert alert.reply_to == "55" and alert.cards[0].update_line == "The board removed Huang as CEO."
    assert updates_seen[0]["headline"] == "Nvidia CEO Jensen Huang admits affair"  # Sonnet knows it's an update
    assert conn.execute("SELECT update_of FROM deliveries WHERE story_id = 11").fetchone()[0] is not None
    assert "Update:</b> The board removed" in telegram.render_card(alert.cards[0], "alert")


def test_first_alert_on_a_saga_is_not_an_update(monkeypatch):
    conn = _db()
    sent, updates_seen = [], []
    _wire(monkeypatch, conn, sent, updates_seen)
    _thread(conn, 2, "Anthropic sets IPO price range")
    _story(conn, 20, "Anthropic sets IPO price range", importance=80, thread=2)
    delivery.send_immediate(conn, CFG)
    assert sent[0].reply_to is None and sent[0].cards[0].update_line == "" and updates_seen == [None]


def test_digest_groups_a_saga_and_marks_it_as_an_update(monkeypatch):
    conn = _db()
    sent, updates_seen = [], []
    _wire(monkeypatch, conn, sent, updates_seen)
    monkeypatch.setattr(delivery.messages, "story_card", lambda conn, sid: _card(conn, sid))
    _thread(conn, 1, "Nvidia CEO Jensen Huang admits affair")
    _story(conn, 10, "Nvidia CEO Jensen Huang admits affair", importance=70, thread=1)
    conn.execute("INSERT INTO deliveries (story_id, recipient, kind, sent_at, local_date, channel_message_id)"
                 " VALUES (10, 'telegram:1', 'alert', ?, '2026-11-12', '55')", (ago(hours=3),))
    _story(conn, 11, "Kress named interim chief", importance=60, thread=1, whats_new="Kress is interim CEO.")
    _story(conn, 12, "Markets weigh the shake-up", importance=40, thread=1, whats_new="No new facts.")
    _thread(conn, 2, "Anthropic sets IPO price range")
    _story(conn, 20, "Anthropic sets IPO price range", importance=55, thread=2)
    m = delivery.build_digest(conn, CFG)
    lead = next(c for c in m.cards if c.story_id == 11)
    assert lead.related_ids == [12] and lead.update_line == "Kress is interim CEO."
    assert next(c for c in m.cards if c.story_id == 20).update_line == ""  # a saga you haven't heard about
    item = telegram.render_digest_item(1, lead)
    assert "🔄 <b>Update:</b> Kress is interim CEO." in item and "➕ 1 more article on this story" in item


def test_side_thread_of_a_big_saga_still_counts_as_an_update(monkeypatch):
    conn = _db()
    sent, updates_seen = [], []
    _wire(monkeypatch, conn, sent, updates_seen)
    _thread(conn, 1, "Nvidia CEO Jensen Huang admits affair")
    _story(conn, 10, "Nvidia CEO Jensen Huang admits affair", importance=70, thread=1)
    conn.execute("INSERT INTO deliveries (story_id, recipient, kind, sent_at, local_date, channel_message_id)"
                 " VALUES (10, 'telegram:1', 'alert', ?, '2026-11-12', '55')", (ago(hours=1),))
    _thread(conn, 2, "Who could succeed Jensen Huang at Nvidia")  # Haiku split this off as its own thread
    _story(conn, 20, "Nvidia names Jensen Huang successor", importance=80, thread=2)
    delivery.send_immediate(conn, CFG)
    assert sent[0].reply_to == "55" and updates_seen[0]["headline"].startswith("Nvidia CEO")
