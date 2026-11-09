import sqlite3

from signality import db, resolution

CFG = {"claims": {"match_window_days": 120, "candidates_per_article": 5}}


def test_attribution_words_dont_count_as_subject():
    words = resolution.subject_words("According to the New York Times, China recruited Alice Huang to spy on Nvidia")
    assert {"china", "recruited", "alice", "huang", "nvidia"} <= words
    assert not words & {"according", "york", "times"}


def test_decisions_map_to_label_and_status():
    claim = {"label": "reported"}
    assert resolution.apply_decision(claim, "confirmed") == ("confirmed", "confirmed")
    assert resolution.apply_decision(claim, "walked_back") == ("disputed", "walked_back")
    assert resolution.apply_decision(claim, "disputed") == ("disputed", "open")
    assert resolution.apply_decision(claim, "delayed") == ("reported", "delayed")
    assert resolution.apply_decision(claim, "no_change") is None


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.migrate(conn)
    conn.execute("INSERT INTO sources (id, name, url, type, added_at) VALUES ('ft','FT','u','news','t'),('ap','AP','u','news','t')")
    conn.execute("INSERT INTO stories (id, title, first_seen_at, last_seen_at) VALUES (1,'x','t','t')")
    for i, (src, title, pub) in enumerate([
        ("ft", "China recruited Alice Huang to spy on Nvidia chief", "2026-11-07T10:00:00+00:00"),
        ("ap", "Nvidia chief Jensen Huang admits affair with Alice Huang", "2026-11-08T10:00:00+00:00"),
        ("ap", "Older Nvidia Alice Huang item", "2026-11-06T10:00:00+00:00"),
    ], start=1):
        conn.execute(
            "INSERT INTO articles (id, source_id, story_id, guid, url, title, title_words, snippet, published_at, fetched_at)"
            " VALUES (?, ?, 1, ?, ?, ?, '', '', ?, ?)", (i, src, f"g{i}", f"u{i}", title, pub, pub))
    now = db.utcnow()
    conn.execute(
        "INSERT INTO claims (id, story_id, article_id, text, kind, basis, claimant, self_reported, label, status,"
        " created_at, updated_at) VALUES (1, 1, 1, 'According to the FT, China recruited Alice Huang to spy on Nvidia CEO Jensen Huang',"
        " 'event', 'anonymous_sources', 'Financial Times', 0, 'reported', 'open', ?, ?)", (now, now))
    return conn


def _article(conn, i):
    return conn.execute("SELECT a.*, s.name AS source_name, s.type AS source_type FROM articles a"
                        " JOIN sources s ON s.id = a.source_id WHERE a.id = ?", (i,)).fetchone()


def test_later_article_on_same_subject_is_a_candidate():
    conn = _db()
    assert [c["id"] for c in resolution.candidates(conn, CFG, _article(conn, 2))] == [1]


def test_article_older_than_the_claim_is_not_evidence():
    conn = _db()
    assert resolution.candidates(conn, CFG, _article(conn, 3)) == []


def test_claim_number_parsing():
    assert [resolution.claim_number(x) for x in ("Claim 24", "24", "#24", " claim 7 ")] == [24, 24, 24, 7]
    assert resolution.claim_number("none") is None
