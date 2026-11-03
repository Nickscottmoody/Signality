"""Stage 1 fetcher: read every feed, filter, remove duplicates, store new stories.

Run it once from the project folder:
    ./.venv/bin/python -m signality.fetcher
"""
import calendar
import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from . import db
from .dedup import clean_url, similarity, strip_outlet_suffix, title_words
from .settings import load_config

TAG = re.compile(r"<[^>]+>")


def download(source, cfg):
    """Fetch one feed. Returns (source, entries, error_message)."""
    polling = cfg["polling"]
    try:
        # requests carries its own HTTPS certificates, which this Mac's
        # Python lacks, so we download with it and hand the text to feedparser.
        response = requests.get(
            source["url"],
            headers={"User-Agent": polling["user_agent"]},
            timeout=polling["request_timeout_seconds"],
        )
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        if not feed.entries:
            return source, [], "feed returned no stories"
        return source, feed.entries[: polling["max_articles_per_feed"]], None
    except requests.RequestException as e:
        return source, [], f"{type(e).__name__}: {e}"[:300]


def ai_pattern(keywords):
    """A pattern that matches any keyword as a whole word ('AI' but not 'said')."""
    alternatives = "|".join(re.escape(k) for k in keywords)
    return re.compile(rf"(?<!\w)({alternatives})(?!\w)", re.IGNORECASE)


def published_time(entry, fallback):
    """The story's publish time in UTC, or the fallback if the feed omits it."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return fallback
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)


def plain_text(raw, limit):
    """Strip HTML tags and extra spaces from a feed's preview text."""
    text = html.unescape(TAG.sub(" ", raw or ""))
    return " ".join(text.split())[:limit]


def to_article(entry, source, cfg, now):
    """Turn one feed item into a clean article dictionary (or None if unusable)."""
    link = entry.get("link")
    title = " ".join((entry.get("title") or "").split())
    if not link or not title:
        return None
    if source.get("via") == "google_news":
        title = strip_outlet_suffix(title)
    return {
        "source_id": source["id"],
        "guid": entry.get("id") or link,
        "url": clean_url(link),
        "title": title,
        "words": title_words(title),
        "snippet": plain_text(entry.get("summary"), cfg["polling"]["snippet_char_cap"]),
        "author": entry.get("author"),
        "paywalled": int(source.get("paywalled", False)),
        "via": source.get("via"),
        "published": published_time(entry, now),
    }


def already_stored(conn, article):
    """True if we've saved this exact article before (same link or same feed id)."""
    row = conn.execute(
        "SELECT 1 FROM articles WHERE url = ? OR (source_id = ? AND guid = ?)",
        (article["url"], article["source_id"], article["guid"]),
    ).fetchone()
    return row is not None


def recent_titles(conn, window_hours):
    """(story_id, title words) for every article seen in the comparison window."""
    since = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT story_id, title_words FROM articles WHERE fetched_at >= ?", (since,)
    )
    return [(r["story_id"], set(r["title_words"].split())) for r in rows]


def matching_story(words, recent, dedup_cfg):
    """The id of an existing story with a near-identical headline, or None."""
    if len(words) < dedup_cfg["min_title_words"]:
        return None
    best_id, best_score = None, 0.0
    for story_id, other in recent:
        if len(other) < dedup_cfg["min_title_words"]:
            continue
        score = similarity(words, other)
        if score > best_score:
            best_id, best_score = story_id, score
    return best_id if best_score >= dedup_cfg["title_similarity"] else None


def save(conn, article, story_id, now_text):
    """Insert the article, creating a new story or joining an existing one."""
    if story_id is None:
        story_id = conn.execute(
            "INSERT INTO stories (title, first_seen_at, last_seen_at) VALUES (?, ?, ?)",
            (article["title"], now_text, now_text),
        ).lastrowid
    else:
        conn.execute(
            "UPDATE stories SET last_seen_at = ?, article_count = article_count + 1 WHERE id = ?",
            (now_text, story_id),
        )
    conn.execute(
        """
        INSERT INTO articles (source_id, story_id, guid, url, title, title_words, snippet,
                              author, paywalled, via, published_at, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (article["source_id"], story_id, article["guid"], article["url"], article["title"],
         " ".join(sorted(article["words"])), article["snippet"], article["author"],
         article["paywalled"], article["via"],
         article["published"].isoformat(timespec="seconds"), now_text),
    )
    return story_id


def run_once(cfg=None):
    """Check every source once. Returns the numbers for this run."""
    cfg = cfg or load_config()
    conn = db.connect(cfg["storage"]["db_path"])
    db.sync_sources(conn, cfg["sources"])

    now = datetime.now(timezone.utc)
    now_text = now.isoformat(timespec="seconds")
    oldest_allowed = now - timedelta(days=cfg["polling"]["max_article_age_days"])
    is_ai = ai_pattern(cfg["ai_filter_keywords"])
    recent = recent_titles(conn, cfg["dedup"]["window_hours"])

    stats = dict(sources_ok=0, sources_failed=0, items_seen=0, too_old=0,
                 filtered_non_ai=0, duplicates_removed=0, new_articles=0,
                 new_stories=0, grouped_articles=0)
    errors = []
    run_id = conn.execute("INSERT INTO fetch_runs (started_at) VALUES (?)", (now_text,)).lastrowid

    # Download all feeds at the same time (much faster than one by one).
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda s: download(s, cfg), cfg["sources"]))

    for source, entries, error in results:
        conn.execute(
            "UPDATE sources SET last_fetched_at = ?, last_status = ? WHERE id = ?",
            (now_text, error or "ok", source["id"]),
        )
        if error:
            stats["sources_failed"] += 1
            errors.append(f"{source['id']}: {error}")
            continue
        stats["sources_ok"] += 1

        for entry in entries:
            stats["items_seen"] += 1
            article = to_article(entry, source, cfg, now)
            if article is None:
                continue
            if article["published"] < oldest_allowed:
                stats["too_old"] += 1
                continue
            if source.get("ai_filter") and not is_ai.search(f"{article['title']} {article['snippet']}"):
                stats["filtered_non_ai"] += 1
                continue
            if already_stored(conn, article):
                stats["duplicates_removed"] += 1
                continue

            story_id = matching_story(article["words"], recent, cfg["dedup"])
            if story_id is None:
                stats["new_stories"] += 1
            else:
                stats["grouped_articles"] += 1
            story_id = save(conn, article, story_id, now_text)
            recent.append((story_id, article["words"]))
            stats["new_articles"] += 1

    conn.execute(
        f"UPDATE fetch_runs SET finished_at = ?, errors = ?, "
        f"{', '.join(f'{k} = ?' for k in stats)} WHERE id = ?",
        (db.utcnow(), "\n".join(errors) or None, *stats.values(), run_id),
    )
    conn.commit()
    conn.close()
    stats["errors"] = errors
    return stats


def main():
    s = run_once()
    print("Signality fetch complete")
    print(f"  sources checked     {s['sources_ok']} ok, {s['sources_failed']} failed")
    print(f"  items read          {s['items_seen']}")
    print(f"  too old (skipped)   {s['too_old']}")
    print(f"  not about AI        {s['filtered_non_ai']}")
    print(f"  duplicates removed  {s['duplicates_removed']}")
    print(f"  new articles saved  {s['new_articles']}")
    print(f"    new stories       {s['new_stories']}")
    print(f"    joined a story    {s['grouped_articles']}  (same event, another outlet)")
    for e in s["errors"]:
        print(f"  ! {e}")


if __name__ == "__main__":
    main()
