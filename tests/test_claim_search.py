import sqlite3
from datetime import datetime, timedelta, timezone

from signality import claim_search, db, receipts, search

CFG = {
    "search": {"enabled": True, "aggregator_domains": ["yahoo.com"], "max_per_day": 30, "monthly_limit": 950,
               "claims_per_day": 10, "claims_per_round": 2, "claim_min_age_hours": 12, "claim_recheck_days": 3,
               "claim_slow_recheck_days": 14, "claim_sonnet_per_round": 2, "evidence_char_cap": 2500,
               "max_failed_attempts": 2},
    "claims": {"match_window_days": 120, "resolve_enabled": True},
    "models": {"high_stakes": "claude-sonnet-5-5"},
    "digest": {"timezone": "America/Chicago"},
    "sources": [{"id": "ft", "name": "FT", "url": "u", "type": "news"}],
}


def ago(**d):
    return (datetime.now(timezone.utc) - timedelta(**d)).isoformat(timespec="seconds")


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.migrate(conn)
    conn.execute("INSERT INTO sources (id, name, url, type, added_at) VALUES ('ft','FT','u','news','t')")
    return conn


def _claim(conn, cid, text="Acme will launch Widget 2 in March", kind="future", label="reported",
           published=None, due=None):
    published = published or ago(days=2)
    conn.execute("INSERT OR IGNORE INTO stories (id, title, first_seen_at, last_seen_at) VALUES (1, 'x', 't', 't')")
    conn.execute("INSERT INTO articles (id, source_id, story_id, guid, url, title, title_words, snippet, published_at,"
                 " fetched_at) VALUES (?, 'ft', 1, ?, ?, 't', '', '', ?, ?)",
                 (cid, f"g{cid}", f"https://www.ft.com/{cid}", published, published))
    conn.execute("INSERT INTO claims (id, story_id, article_id, text, kind, basis, claimant, due_date, self_reported,"
                 " label, status, created_at, updated_at) VALUES (?, 1, ?, ?, ?, 'anonymous_sources', 'FT', ?, 0, ?,"
                 " 'open', ?, ?)", (cid, cid, text, kind, due, label, ago(hours=1), ago(hours=1)))
    conn.execute("INSERT INTO claim_events (claim_id, at, event, label, status, reason, decided_by)"
                 " VALUES (?, ?, 'created', ?, 'open', 'One outlet so far.', 'rules')", (cid, ago(hours=1), label))


def _searched(conn, cid, when):
    conn.execute("INSERT INTO web_searches (subject_type, subject_id, provider, query, searched_at, credits, ok)"
                 " VALUES ('claim', ?, 'tavily', 'q', ?, 1, 1)", (cid, when))


def test_query_drops_who_reported_it():
    assert claim_search.search_query("According to The Information, Meta plans a $60B program") == "Meta plans a $60B program"
    assert claim_search.search_query("Bloomberg reports that Apple explores an AI Siri") == "Apple explores an AI Siri"
    assert claim_search.search_query("The woman is a suspected spy.") == "The woman is a suspected spy."


def test_candidates_order_and_recheck_timing():
    conn = _db()
    _claim(conn, 1)                                             # never searched
    _claim(conn, 2, kind="event"); _searched(conn, 2, ago(days=4))   # due again (3-day recheck)
    _claim(conn, 3, kind="event"); _searched(conn, 3, ago(days=1))   # searched yesterday: wait
    _claim(conn, 4, due="2099-01-01"); _searched(conn, 4, ago(days=4))  # plan not due yet: slow recheck
    _claim(conn, 5, published=ago(hours=2))                     # too new to search yet
    assert [c["id"] for c in claim_search.candidates(conn, CFG)] == [1, 2]


def test_evidence_from_before_the_claim_cannot_settle_it():
    pages = [{"domain": "bbc.com", "relation": "confirms", "independent": True, "why": "w",
              "published_at": "2026-11-01T00:00:00+00:00"},
             {"domain": "yahoo.com", "relation": "supports", "independent": True, "why": "w", "published_at": None}]
    claim_search.apply_rules(pages, CFG, "2026-11-05T00:00:00+00:00")
    assert pages[0]["relation"] == "related_no_change"
    assert pages[1]["independent"] is False  # aggregators never count


def test_claims_keep_their_share_of_searches():
    conn = _db()
    for i in range(20):
        conn.execute("INSERT INTO web_searches (subject_type, subject_id, provider, query, searched_at, credits, ok)"
                     " VALUES ('story', ?, 'tavily', 'q', ?, 1, 1)", (i, db.utcnow()))
    assert search.allowance(conn, CFG, "story") == 0
    assert search.allowance(conn, CFG, "claim") == 10


def test_page_that_settles_a_claim_becomes_its_receipt_evidence(monkeypatch):
    conn = _db()
    _claim(conn, 1)
    monkeypatch.setattr(search, "search", lambda *a, **k: [
        {"url": "https://www.ft.com/again", "domain": "ft.com", "title": "t", "published_at": ago(hours=3), "snippet": "s"},
        {"url": "https://news.acme.com/widget2", "domain": "acme.com", "title": "Widget 2 is here",
         "published_at": ago(hours=3), "snippet": "Acme launched Widget 2 today."}])
    monkeypatch.setattr(search, "source_domains", lambda conn, cfg: {"ft.com": "FT"})
    monkeypatch.setattr(claim_search.article_text, "fetch", lambda url, cfg: None)
    replies = iter([
        ({"pages": [{"id": "R1", "relation": "confirms", "independent": True, "reason": "Acme's own launch post"}]}, 0.0005),
        ({"reason": "Acme announced it.", "decision": "confirmed", "receipt_line": "Acme announced the launch.",
          "evidence_id": "R1"}, 0.004),
    ])
    monkeypatch.setattr(claim_search.ai, "ask_json", lambda *a, **k: next(replies))
    c = claim_search.candidates(conn, CFG)[0]
    r = claim_search.investigate(conn, CFG, c, {"sonnet": 1})
    assert [p["domain"] for p in r["pages"]] == ["acme.com"]  # the claim's own outlet (FT) was skipped
    assert tuple(conn.execute("SELECT status, label FROM claims WHERE id = 1").fetchone()) == ("confirmed", "confirmed")
    event = conn.execute("SELECT id FROM claim_events WHERE event = 'resolved'").fetchone()[0]
    card = receipts.card(conn, event)
    assert card.evidence_source == ("acme.com", "https://news.acme.com/widget2")
    assert card.outcome == "confirmed" and card.reason == "Acme announced the launch."
