from signality import fetcher, triage
from signality.settings import load_config

from .test_threads import CFG, _db, ago

REAL = load_config()


def _passes(headline):
    pattern = fetcher.ai_pattern(REAL["ai_filter_keywords"] + REAL["tech_event_keywords"])
    return bool(pattern.search(headline))


def test_major_outage_and_cyber_headlines_now_get_past_the_broad_feed_filter():
    # Real Nov 12-17 headlines the AI-only filter threw away.
    for headline in ("Outages sweep across every industry: Here's what you need to know",
                     "Apple services and Marriott experience outages amid wave of technology mishaps",
                     "Rubio Says Recent US Tech Outages Unrelated, Not Hostile Acts",
                     "Hackers hit 178 companies in coordinated ransomware campaign"):
        assert _passes(headline), headline
    assert not _passes("Fed holds rates steady as inflation cools")
    assert not _passes("Students compete at a weekend hackathon")  # whole words only


def _answer(ai_related, tech_event):
    factor = {"score": 4, "reason": "r"}
    return {"same_event_as": "none", "continues_thread": "none", "whats_new": "",
            "headline": "Ransomware attack disrupts payments at major US banks", "summary": "s",
            "why_it_matters": "w", "topics": ["cyber"], "content_type": "news", "sourcing": "on_record_reporting",
            "attributed_to": "", "self_reported": False, "ai_related": ai_related, "major_tech_event": tech_event,
            "impact": factor, "breadth": factor, "urgency": factor, "novelty": factor, "claims": []}


def _story(conn, sid):
    conn.execute("INSERT INTO stories (id, title, first_seen_at, last_seen_at) VALUES (?, 'x', ?, ?)", (sid, ago(), ago()))
    conn.execute("INSERT INTO articles (id, source_id, story_id, guid, url, title, title_words, snippet, published_at,"
                 " fetched_at) VALUES (?, 'ft', ?, ?, ?, 'Ransomware hits banks', 'ransomware hits banks', 's', ?, ?)",
                 (sid, sid, f"g{sid}", f"https://ft.com/{sid}", ago(), ago()))


def test_major_cyber_event_without_ai_is_scored_and_sendable(monkeypatch):
    conn = _db()
    _story(conn, 1)
    monkeypatch.setattr(triage.ai, "ask_json", lambda *a, **k: (_answer(False, True), 0.001))
    cfg = {**CFG, "topics": {"cyber": 1.1}}
    triage.triage_story(conn, cfg, 1)
    row = conn.execute("SELECT ai_related, tech_event, importance, topic_multiplier FROM story_triage"
                       " WHERE story_id = 1").fetchone()
    assert tuple(row) == (1, 1, 82, 1.1)  # in scope, with the cyber bonus (75 x 1.1, rounded)


def test_small_non_ai_incident_is_stored_only(monkeypatch):
    conn = _db()
    _story(conn, 1)
    monkeypatch.setattr(triage.ai, "ask_json", lambda *a, **k: (_answer(False, False), 0.001))
    triage.triage_story(conn, {**CFG, "topics": {"cyber": 1.1}}, 1)
    assert tuple(conn.execute("SELECT ai_related, importance FROM story_triage").fetchone()) == (0, 0)
