"""The SQLite database: table layout and small helpers.

Design rules (from the long-term plan):
- Shared news data (sources, stories, articles) is kept apart from per-user
  data, which arrives in Stage 2c. That keeps multiple users possible later.
- Every row keeps its IDs and UTC timestamps, so later features (claim history,
  source track records, accuracy scores) can be added without rebuilding.
- Tables are added through numbered migrations, never by editing old ones.
"""
import sqlite3
from datetime import datetime, timezone

from .settings import ROOT

# Each entry is one migration. To change the database later, ADD a new entry
# at the end. Never edit an old one: existing databases have already run it.
MIGRATIONS = [
    # 1 - Stage 1: sources, stories, articles, and fetch metrics
    """
    -- One row per news source. Rows are never deleted, only marked inactive,
    -- so a source's track record survives even if it's removed from config.
    CREATE TABLE sources (
        id              TEXT PRIMARY KEY,   -- short id from config.yaml, e.g. 'reuters'
        name            TEXT NOT NULL,
        url             TEXT NOT NULL,
        type            TEXT NOT NULL,      -- primary | news | specialist | research
        lean            TEXT,               -- political lean, for the bias audit
        paywalled       INTEGER NOT NULL DEFAULT 0,
        active          INTEGER NOT NULL DEFAULT 1,
        added_at        TEXT NOT NULL,
        last_fetched_at TEXT,
        last_status     TEXT                -- 'ok' or the last error message
    );

    -- One row per real-world news event. Several articles from different
    -- outlets can belong to the same story.
    CREATE TABLE stories (
        id              INTEGER PRIMARY KEY,
        title           TEXT NOT NULL,      -- headline of the first article seen
        first_seen_at   TEXT NOT NULL,
        last_seen_at    TEXT NOT NULL,
        article_count   INTEGER NOT NULL DEFAULT 1
    );

    -- One row per article from one source.
    CREATE TABLE articles (
        id              INTEGER PRIMARY KEY,
        source_id       TEXT NOT NULL REFERENCES sources(id),
        story_id        INTEGER NOT NULL REFERENCES stories(id),
        guid            TEXT NOT NULL,      -- the feed's own id for this item
        url             TEXT NOT NULL,      -- cleaned link (tracking codes removed)
        title           TEXT NOT NULL,
        title_words     TEXT NOT NULL,      -- key words of the title, for duplicate checks
        snippet         TEXT,               -- preview text from the feed
        author          TEXT,
        paywalled       INTEGER NOT NULL DEFAULT 0,
        via             TEXT,               -- 'google_news' if fetched through Google News
        published_at    TEXT NOT NULL,
        fetched_at      TEXT NOT NULL,
        UNIQUE (source_id, guid),
        UNIQUE (url)
    );
    CREATE INDEX idx_articles_story     ON articles(story_id);
    CREATE INDEX idx_articles_fetched   ON articles(fetched_at);

    -- One row per fetch run: the numbers behind the portfolio metrics.
    CREATE TABLE fetch_runs (
        id                  INTEGER PRIMARY KEY,
        started_at          TEXT NOT NULL,
        finished_at         TEXT,
        sources_ok          INTEGER NOT NULL DEFAULT 0,
        sources_failed      INTEGER NOT NULL DEFAULT 0,
        items_seen          INTEGER NOT NULL DEFAULT 0,
        too_old             INTEGER NOT NULL DEFAULT 0,
        filtered_non_ai     INTEGER NOT NULL DEFAULT 0,
        duplicates_removed  INTEGER NOT NULL DEFAULT 0,  -- exact repeats we already had
        new_articles        INTEGER NOT NULL DEFAULT 0,
        new_stories         INTEGER NOT NULL DEFAULT 0,
        grouped_articles    INTEGER NOT NULL DEFAULT 0,  -- new articles joined to an existing story
        errors              TEXT
    );
    """,
    # 2 - Stage 2a: a record of every Claude call (the cost meter), plus a
    #     small key/value store for agent state (e.g., "budget warning sent").
    """
    CREATE TABLE ai_calls (
        id                  INTEGER PRIMARY KEY,
        created_at          TEXT NOT NULL,
        task                TEXT NOT NULL,      -- e.g. 'triage', 'alert_check'
        model               TEXT NOT NULL,
        story_id            INTEGER REFERENCES stories(id),
        input_tokens        INTEGER NOT NULL DEFAULT 0,
        output_tokens       INTEGER NOT NULL DEFAULT 0,
        cache_write_tokens  INTEGER NOT NULL DEFAULT 0,
        cache_read_tokens   INTEGER NOT NULL DEFAULT 0,
        cost_usd            REAL NOT NULL DEFAULT 0,
        ok                  INTEGER NOT NULL,   -- 1 = worked, 0 = failed
        error               TEXT,
        request_id          TEXT                -- Anthropic's id, for support questions
    );
    CREATE INDEX idx_ai_calls_created ON ai_calls(created_at);

    CREATE TABLE app_state (
        key         TEXT PRIMARY KEY,
        value       TEXT,
        updated_at  TEXT NOT NULL
    );
    """,
    # 3 - Stage 2a: triage results. One row per story per model, so the same
    #     story can be scored by Haiku and Sonnet side by side ('comparison').
    """
    ALTER TABLE stories ADD COLUMN status TEXT NOT NULL DEFAULT 'new';
        -- new | triaged | merged | failed | too_old
    ALTER TABLE stories ADD COLUMN merged_into INTEGER REFERENCES stories(id);

    CREATE TABLE story_triage (
        id              INTEGER PRIMARY KEY,
        story_id        INTEGER NOT NULL REFERENCES stories(id),
        article_id      INTEGER NOT NULL REFERENCES articles(id),  -- the article that was read
        purpose         TEXT NOT NULL DEFAULT 'live',              -- live | comparison
        model           TEXT NOT NULL,
        created_at      TEXT NOT NULL,
        text_source     TEXT NOT NULL,      -- full = whole article; snippet = preview only ("partial")
        headline        TEXT NOT NULL,
        summary         TEXT NOT NULL,
        why_it_matters  TEXT NOT NULL,
        topics          TEXT NOT NULL,      -- JSON list, e.g. ["jobs", "policy"]
        content_type    TEXT NOT NULL,      -- news | opinion | analysis | press_release | research_paper
        sourcing        TEXT NOT NULL,      -- what the article's claims rest on (see triage.py)
        attributed_to   TEXT,               -- outlet it repeats, e.g. "Financial Times"
        self_reported   INTEGER NOT NULL,   -- 1 = key claims are a company's own unverified claims
        impact          INTEGER NOT NULL,
        impact_reason   TEXT NOT NULL,
        breadth         INTEGER NOT NULL,
        breadth_reason  TEXT NOT NULL,
        urgency         INTEGER NOT NULL,
        urgency_reason  TEXT NOT NULL,
        novelty         INTEGER NOT NULL,
        novelty_reason  TEXT NOT NULL,
        base_score      REAL NOT NULL,      -- 0-100 from the four factors alone
        topic_multiplier REAL NOT NULL,     -- favored topics (jobs, finance) get a boost
        importance      INTEGER NOT NULL,   -- final 0-100 score
        cost_usd        REAL NOT NULL,
        UNIQUE (story_id, model, purpose)
    );
    CREATE INDEX idx_stories_status ON stories(status);
    """,
    # 4 - Stage 2a: the model's "is this actually about AI?" check
    """
    ALTER TABLE story_triage ADD COLUMN ai_related INTEGER NOT NULL DEFAULT 1;
    """,
    # 5 - Stage 2a: validity labels (a new row each time a story's label changes,
    #     so its full history can be shown) and Sonnet's double-check on alerts.
    """
    CREATE TABLE story_validity (
        id                  INTEGER PRIMARY KEY,
        story_id            INTEGER NOT NULL REFERENCES stories(id),
        label               TEXT NOT NULL,   -- confirmed | likely | reported | unverified | disputed | opinion
        reason              TEXT NOT NULL,
        independent_outlets INTEGER NOT NULL,
        self_reported       INTEGER NOT NULL,
        set_at              TEXT NOT NULL
    );
    CREATE INDEX idx_story_validity_story ON story_validity(story_id, id);

    CREATE TABLE alert_checks (
        id              INTEGER PRIMARY KEY,
        story_id        INTEGER NOT NULL REFERENCES stories(id),
        model           TEXT NOT NULL,
        created_at      TEXT NOT NULL,
        send_as_alert   INTEGER NOT NULL,   -- 1 = Sonnet agrees it deserves a loud alert
        reason          TEXT NOT NULL,
        validity_agrees INTEGER NOT NULL,
        validity_note   TEXT NOT NULL,
        cost_usd        REAL NOT NULL
    );
    """,
    # 6 - Stage 2a: what was sent to whom. 'recipient' is platform + account
    #     (e.g. 'telegram:123'), so other platforms and users can be added later.
    """
    CREATE TABLE deliveries (
        id              INTEGER PRIMARY KEY,
        story_id        INTEGER REFERENCES stories(id),   -- empty for notices
        recipient       TEXT NOT NULL,
        kind            TEXT NOT NULL,      -- alert | silent | digest | notice
        sent_at         TEXT NOT NULL,
        local_date      TEXT NOT NULL,      -- the recipient's calendar day (for the alert cap)
        channel_message_id TEXT,            -- the platform's id for the sent message
        note            TEXT
    );
    CREATE UNIQUE INDEX idx_deliveries_once ON deliveries(story_id, recipient) WHERE story_id IS NOT NULL;
    CREATE INDEX idx_deliveries_day ON deliveries(recipient, local_date, kind);
    """,
    # 7 - Stage 2b: claims (the receipts system). Claims are shared news data, not
    #     per-user. Every change to a claim is a new row in claim_events, so its full
    #     history (dates + evidence) can always be shown.
    """
    CREATE TABLE claims (
        id              INTEGER PRIMARY KEY,
        story_id        INTEGER NOT NULL REFERENCES stories(id),
        article_id      INTEGER NOT NULL REFERENCES articles(id),  -- where it was first seen
        text            TEXT NOT NULL,      -- one sentence, attributed ("OpenAI says...")
        kind            TEXT NOT NULL,      -- event | future | performance
        basis           TEXT NOT NULL,      -- what it rests on (same values as triage sourcing)
        claimant        TEXT,               -- who is making the claim
        due_date        TEXT,               -- future claims: when it should happen (YYYY-MM-DD)
        self_reported   INTEGER NOT NULL,
        label           TEXT NOT NULL,      -- current validity label
        status          TEXT NOT NULL,      -- open | confirmed | walked_back | delayed | never_happened
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL,
        resolved_at     TEXT
    );
    CREATE INDEX idx_claims_status ON claims(status);
    CREATE INDEX idx_claims_story ON claims(story_id);

    CREATE TABLE claim_events (
        id                  INTEGER PRIMARY KEY,
        claim_id            INTEGER NOT NULL REFERENCES claims(id),
        at                  TEXT NOT NULL,
        event               TEXT NOT NULL,  -- created | label_change | resolved
        label               TEXT NOT NULL,
        status              TEXT NOT NULL,
        reason              TEXT NOT NULL,  -- the evidence, in words
        evidence_article_id INTEGER REFERENCES articles(id),
        decided_by          TEXT NOT NULL   -- 'rules' or the model that decided
    );
    CREATE INDEX idx_claim_events_claim ON claim_events(claim_id, id);
    """,
]


def utcnow():
    """The current time in UTC, as text like '2026-11-03T14:05:00+00:00'."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path):
    """Open the database (creating it if needed) and bring it up to date."""
    path = ROOT / db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)  # wait if another run is writing
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


def migrate(conn):
    """Run any migrations this database hasn't run yet."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    done = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    for version, sql in enumerate(MIGRATIONS, start=1):
        if version in done:
            continue
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, utcnow()),
        )
        conn.commit()


def sync_sources(conn, sources):
    """Make the sources table match config.yaml.

    New sources are added, existing ones updated, and ones removed from config
    are marked inactive (not deleted) so their history is kept.
    """
    now = utcnow()
    for s in sources:
        conn.execute(
            """
            INSERT INTO sources (id, name, url, type, lean, paywalled, active, added_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name, url = excluded.url, type = excluded.type,
                lean = excluded.lean, paywalled = excluded.paywalled, active = 1
            """,
            (s["id"], s["name"], s["url"], s["type"], s.get("lean"),
             int(s.get("paywalled", False)), now),
        )
    ids = [s["id"] for s in sources]
    conn.execute(
        f"UPDATE sources SET active = 0 WHERE id NOT IN ({','.join('?' * len(ids))})",
        ids,
    )
    conn.commit()


def get_state(conn, key, default=None):
    """Read one saved value from app_state."""
    row = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_state(conn, key, value):
    """Save one value to app_state (insert or overwrite)."""
    conn.execute(
        "INSERT INTO app_state (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, value, utcnow()),
    )
    conn.commit()
