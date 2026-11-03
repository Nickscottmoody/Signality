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
