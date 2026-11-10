import sqlite3
from datetime import datetime, timedelta, timezone

from signality import corroborate, db, search, validity
from signality.validity import decide

CFG = {
    "search": {"aggregator_domains": ["yahoo.com", "msn.com"], "max_per_day": 30, "monthly_limit": 950,
               "min_importance": 40, "wait_hours": 2, "max_story_age_hours": 36, "max_failed_attempts": 2},
    "importance": {"thresholds": {"alert": 65}},
    "digest": {"timezone": "America/Chicago"},
}


def tri(sourcing="on_record_reporting"):
    return {"sourcing": sourcing, "content_type": "news", "article_id": 1, "attributed_to": None, "self_reported": 0}


BLOOMBERG = [{"id": 1, "source_id": "bloomberg", "source_name": "Bloomberg", "source_type": "news", "title": "x"}]


def web(*pairs):
    return {"results": [{"outlet": o, "basis": b, "url": f"https://{o}/a"} for o, b in pairs]}


# --- validity rules with web evidence ---

def test_never_searched_keeps_old_reason():
    label, reason, _ = decide(tri(), BLOOMBERG, None)
    assert label == "reported" and "web search" not in reason


def test_searched_but_nothing_found_says_so():
    label, reason, _ = decide(tri(), BLOOMBERG, web())
    assert label == "reported" and "Web search found no independent confirmation yet" in reason


def test_one_independent_web_outlet_makes_likely_and_names_it():
    label, reason, n = decide(tri(), BLOOMBERG, web(("bbc.com", "own_reporting")))
    assert (label, n) == ("likely", 2)
    assert "bbc.com found by web search" in reason


def test_web_outlet_we_already_have_counts_once():
    label, _, _ = decide(tri(), BLOOMBERG, web(("Bloomberg", "own_reporting")))
    assert label == "reported"


def test_organizations_own_page_confirms():
    label, reason, _ = decide(tri(), BLOOMBERG, web(("NVIDIA Blog", "primary")))
    assert label == "confirmed" and "NVIDIA Blog" in reason


def test_denial_found_by_search_disputes():
    label, _, _ = decide(tri(), BLOOMBERG, web(("cnbc.com", "denial"), ("bbc.com", "own_reporting")))
    assert label == "disputed"


def test_rumor_stays_unverified_without_independent_outlets():
    label, reason, _ = decide(tri("rumor_leak_social"), BLOOMBERG, web())
    assert label == "unverified" and "no independent confirmation" in reason


# --- code rules that overrule the model ---

def res(domain, basis):
    return {"domain": domain, "basis": basis, "why": "w"}


def test_aggregator_never_counts():
    r = corroborate.apply_rules([res("yahoo.com", "own_reporting")], CFG, "story", set())
    assert r[0]["basis"] == "repeats_other" and "aggregator" in r[0]["why"]


def test_news_site_quoting_a_blog_post_is_not_primary():
    r = corroborate.apply_rules([res("timesnownews.com", "primary")], CFG, "Meta expands age checks", set())
    assert r[0]["basis"] == "own_reporting"


def test_organizations_own_site_stays_primary():
    r = corroborate.apply_rules([res("nvidia.com", "primary"), res("sec.gov", "primary")], CFG,
                                "Nvidia board opens probe", set())
    assert [x["basis"] for x in r] == ["primary", "primary"]


def test_site_with_mixed_verdicts_gets_no_credit():
    r = corroborate.apply_rules([res("kitco.com", "own_reporting"), res("kitco.com", "repeats_other")],
                                CFG, "story", set())
    assert {x["basis"] for x in r} == {"repeats_other"}


# --- search helpers ---

def test_domain_of():
    assert search.domain_of("https://www.cnbc.com/2026/x.html") == "cnbc.com"
    assert search.domain_of("https://nvidianews.nvidia.com/news/x") == "nvidia.com"
    assert search.domain_of("https://www.bbc.co.uk/news/x") == "bbc.co.uk"


def test_sister_sites_are_one_organization():
    assert search.same_organization("bloomberglaw.com", "bloomberg.com")
    assert not search.same_organization("cnbc.com", "cnn.com")
    assert not search.same_organization("ft.com", "ftc.gov")  # too short to guess


def test_tavily_dates_become_iso():
    assert search._iso("Sun, 08 Nov 2026 21:43:11 GMT") == "2026-11-08T21:43:11+00:00"
    assert search._iso(None) is None and search._iso("soon") is None


# --- which stories get searched ---

def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.migrate(conn)
    conn.execute("INSERT INTO sources (id, name, url, type, added_at) VALUES ('bb','Bloomberg','u','news','t')")
    return conn


def _story(conn, sid, importance, hours_ago):
    seen = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    conn.execute("INSERT INTO stories (id, title, first_seen_at, last_seen_at, status) VALUES (?, 'x', ?, ?, 'triaged')",
                 (sid, seen, seen))
    conn.execute("INSERT INTO articles (id, source_id, story_id, guid, url, title, title_words, snippet, published_at,"
                 " fetched_at) VALUES (?, 'bb', ?, ?, ?, 'x', '', '', ?, ?)",
                 (sid, sid, f"g{sid}", f"https://www.bloomberg.com/{sid}", seen, seen))
    conn.execute(
        "INSERT INTO story_triage (story_id, article_id, model, created_at, text_source, headline, summary,"
        " why_it_matters, topics, content_type, sourcing, self_reported, impact, impact_reason, breadth,"
        " breadth_reason, urgency, urgency_reason, novelty, novelty_reason, base_score, topic_multiplier,"
        " importance, cost_usd) VALUES (?, ?, 'm', 't', 'full', 'h', 's', 'w', '[]', 'news',"
        " 'on_record_reporting', 0, 3, 'r', 3, 'r', 3, 'r', 3, 'r', 50, 1, ?, 0)",
        (sid, sid, importance))


def test_candidates_wait_skip_and_prioritize():
    conn = _db()
    _story(conn, 1, 45, hours_ago=5)    # eligible
    _story(conn, 2, 45, hours_ago=1)    # too fresh: our feeds may still find other outlets
    _story(conn, 3, 70, hours_ago=0.5)  # alert-level: searched right away
    _story(conn, 4, 30, hours_ago=5)    # not important enough
    _story(conn, 5, 50, hours_ago=48)   # too old
    _story(conn, 6, 60, hours_ago=5)    # already searched
    conn.execute("INSERT INTO web_searches (subject_type, subject_id, provider, query, searched_at, credits, ok)"
                 " VALUES ('story', 6, 'tavily', 'q', ?, 1, 1)", (db.utcnow(),))
    assert [c["story_id"] for c in corroborate.candidates(conn, CFG)] == [3, 1]


def test_allowance_respects_daily_cap():
    conn = _db()
    for i in range(30):
        conn.execute("INSERT INTO web_searches (subject_type, subject_id, provider, query, searched_at, credits, ok)"
                     " VALUES ('story', ?, 'tavily', 'q', ?, 1, 1)", (i, db.utcnow()))
    assert search.allowance(conn, CFG) == 0


def test_web_evidence_reads_latest_search_counted_results_only():
    conn = _db()
    _story(conn, 1, 50, hours_ago=5)
    conn.execute("INSERT INTO web_searches (id, subject_type, subject_id, provider, query, searched_at, credits, ok)"
                 " VALUES (1, 'story', 1, 'tavily', 'q', 't', 1, 1)")
    conn.executemany("INSERT INTO web_results (search_id, url, domain, outlet, basis) VALUES (1, ?, ?, ?, ?)",
                     [("https://bbc.com/a", "bbc.com", "bbc.com", "own_reporting"),
                      ("https://yahoo.com/a", "yahoo.com", "yahoo.com", "repeats_other")])
    assert validity.web_evidence(conn, 1)["results"] == [
        {"outlet": "bbc.com", "basis": "own_reporting", "url": "https://bbc.com/a"}]
    assert validity.update(conn, 1)["label"] == "likely"


def test_page_that_misses_the_key_fact_never_counts(monkeypatch):
    # The model calls Nvidia's page "primary" but says it doesn't report the key fact (the lawsuits).
    reply = {"key_fact": "law firms are suing Nvidia", "results": [
        {"id": "R1", "reports_key_fact": False, "basis": "primary", "original_outlet": "", "why": "probe only"},
        {"id": "R2", "reports_key_fact": True, "basis": "own_reporting", "original_outlet": "", "why": "suits"}]}
    monkeypatch.setattr(corroborate.ai, "ask_json", lambda *a, **k: (reply, 0.0005))
    pages = [{"outlet": "NVIDIA Blog", "domain": "nvidia.com", "published_at": None, "title": "t", "snippet": "s"},
             {"outlet": "reuters.com", "domain": "reuters.com", "published_at": None, "title": "t", "snippet": "s"}]
    t = {"headline": "Law firms sue Nvidia", "summary": "s"}
    results, cost, key_fact = corroborate.judge(None, CFG, 1, t, ["Bloomberg"], "2026-11-09T00:00:00+00:00", pages)
    assert [r["basis"] for r in results] == ["not_same_event", "own_reporting"]
    assert key_fact == "law firms are suing Nvidia"
