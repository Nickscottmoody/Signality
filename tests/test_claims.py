from signality.claims import initial_label


def claim(basis="on_record_reporting", kind="event", self_reported=False, claimant="Reuters"):
    return {"basis": basis, "kind": kind, "self_reported": self_reported, "claimant": claimant}


def test_official_event_is_confirmed_and_closed():
    assert initial_label(claim("official_source", claimant="OpenAI"), 1)[:2] == ("confirmed", "confirmed")


def test_official_plan_stays_open_until_it_happens():
    assert initial_label(claim("official_source", kind="future", claimant="OpenAI"), 1)[:2] == ("confirmed", "open")


def test_company_bragging_is_self_reported_and_open():
    label, status, reason = initial_label(claim("official_source", "performance", True, "OpenAI"), 3)
    assert (label, status) == ("self_reported", "open") and "OpenAI" in reason


def test_two_independent_outlets_make_a_claim_likely():
    assert initial_label(claim("anonymous_sources"), 2)[:2] == ("likely", "open")


def test_rumor_is_unverified_and_one_outlet_is_reported():
    assert initial_label(claim("rumor_leak_social"), 1)[0] == "unverified"
    assert initial_label(claim("anonymous_sources"), 1)[0] == "reported"


def test_denial_is_disputed():
    assert initial_label(claim("denial_or_correction"), 1)[0] == "disputed"


def test_routine_fact_not_in_doubt_is_labeled_but_not_tracked():
    c = {**claim("on_record_reporting"), "in_doubt": False}
    label, status, _ = initial_label(c, 1, "Reuters")
    assert (label, status) == ("reported", "not_tracked")


def test_plans_and_bragging_are_tracked_even_if_marked_not_in_doubt():
    assert initial_label({**claim("official_source", "future", claimant="Meta"), "in_doubt": False}, 1)[1] == "open"
    assert initial_label({**claim("official_source", "performance", True, "Meta"), "in_doubt": False}, 1)[1] == "open"


def test_outlet_citing_its_own_analysis_is_not_a_relay():
    c = claim("repeats_other_outlet", claimant="The Information")
    assert "Relayed" not in initial_label(c, 1, "The Information")[2]


import sqlite3

from signality import claims as claims_mod
from signality import db as db_mod


def _claims_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db_mod.migrate(conn)
    conn.execute("INSERT INTO sources (id, name, url, type, added_at) VALUES ('ft','FT','u','news','t')")
    conn.execute("INSERT INTO stories (id, title, first_seen_at, last_seen_at) VALUES (1,'x','t','t'),(2,'y','t','t')")
    for i in (1, 2):
        conn.execute("INSERT INTO articles (id, source_id, story_id, guid, url, title, title_words, published_at,"
                     " fetched_at) VALUES (?, 'ft', ?, ?, ?, 't', '', 't', 't')", (i, i, f"g{i}", f"u{i}"))
    return conn


def _add(conn, cid, story, label, status, created):
    conn.execute("INSERT INTO claims (id, story_id, article_id, text, kind, basis, self_reported, label, status,"
                 " created_at, updated_at) VALUES (?, ?, ?, 'Huang admitted an affair', 'event', 'official_source',"
                 " 0, ?, ?, ?, ?)", (cid, story, story, label, status, created, created))
    conn.execute("INSERT INTO claim_events (claim_id, at, event, label, status, reason, decided_by)"
                 " VALUES (?, ?, 'created', ?, ?, 'r', 'rules')", (cid, created, label, status))


def test_merge_keeps_earliest_and_takes_strongest_evidence():
    conn = _claims_db()
    _add(conn, 1, 1, "reported", "open", "2026-11-07")
    _add(conn, 2, 2, "confirmed", "confirmed", "2026-11-08")
    keeper, copies = claims_mod.merge_group(conn, [2, 1])
    k = conn.execute("SELECT label, status FROM claims WHERE id = 1").fetchone()
    d = conn.execute("SELECT status, duplicate_of FROM claims WHERE id = 2").fetchone()
    assert (keeper, copies) == (1, [2])
    assert tuple(k) == ("confirmed", "confirmed") and tuple(d) == ("duplicate", 1)


def test_repeated_claim_is_not_saved_twice():
    conn = _claims_db()
    _add(conn, 1, 1, "reported", "open", "2026-11-07")
    new = {"text": "Jensen Huang acknowledged having an affair", "kind": "event", "basis": "on_record_reporting",
           "claimant": "Bloomberg", "due_date": "", "self_reported": False, "in_doubt": True, "same_as": "Claim 1"}
    out = claims_mod.record(conn, 2, 2, [new], 1, "Bloomberg", known_ids=[1])
    assert out[0]["status"] == "repeat"
    assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 1
    assert conn.execute("SELECT event FROM claim_events ORDER BY id DESC LIMIT 1").fetchone()[0] == "repeated"


def test_same_as_pointing_at_an_unknown_claim_is_ignored():
    conn = _claims_db()
    new = {"text": "Something new", "kind": "event", "basis": "on_record_reporting", "claimant": "FT",
           "due_date": "", "self_reported": False, "in_doubt": True, "same_as": "99"}
    assert claims_mod.record(conn, 2, 2, [new], 1, "FT", known_ids=[1])[0]["status"] == "open"
