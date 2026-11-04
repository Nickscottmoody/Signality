"""Triage: Claude Haiku reads each new story once and rates it.

For every new story, one short AI call returns:
- a headline, 2-sentence summary, and "why it matters" sentence
- topic tags, content type (news vs. opinion...), and what the claims rest on
- 1-5 ratings for Impact, Breadth, Urgency, Novelty, each with a reason
- whether it's the same event as a story we already have (reworded duplicate)

The importance score itself is calculated in scoring.py, not by the model.

Try it on a few stories (costs a fraction of a cent each):
    ./.venv/bin/python -m signality.triage --limit 5
"""
import argparse
import json
from datetime import datetime, timedelta, timezone

from . import ai, article_text, db, scoring
from .dedup import similarity
from .settings import load_config

SYSTEM = """You are the triage analyst for Signality, a personal AI-news agent whose motto is \
"AI news with receipts." You read one news item at a time and return a short, structured \
assessment. Signality shows the reader your reasons next to every rating, so each reason must be \
specific to this story and checkable against it.

WRITING
- headline: one line, plain language, at most ~90 characters. State what happened.
- summary: exactly two sentences, business-level language. If you use a technical term, explain it \
in a few words. Neutral wording: no hype, no loaded adjectives. If the story is contested, say what \
each side claims instead of adopting either framing.
- why_it_matters: one sentence on the practical consequence for people or businesses.
- Never state predictions as certain. Attribute claims ("OpenAI says...", "according to Reuters...").
- If you only received a preview (not the full article), summarize only what the preview supports.

RATINGS (integers 1-5). Most stories land at 2-3; give 5 only for rare, major events.
- impact: how big the real-world consequences are.
  1 minor update or small product tweak | 3 notable for one industry or a large user base |
  5 major shift for the AI industry, economy, or society (e.g., a frontier model from a top lab, \
a major law taking effect, a very large acquisition).
- breadth: how many people or organizations it touches.
  1 a niche group | 3 a whole industry or many millions of users | 5 most workers, businesses, or people.
- urgency: how time-sensitive it is.
  1 evergreen, no time pressure | 3 relevant this week | 5 matters today (breaking, takes effect \
now, deadline imminent).
- novelty: how new or surprising it is.
  1 rehash, incremental, or widely expected | 3 a new development in an ongoing story | \
5 first of its kind or genuinely surprising.

TOPICS (choose all that clearly apply; use "other" only if none fit)
model_releases, research, companies_funding, policy, tools, jobs (AI's effect on work, hiring, \
careers, skills), finance_analytics (AI in finance, markets, investing, accounting, data analytics), other.

CONTENT TYPE
news | opinion (argues a position) | analysis (explains or interprets) | press_release (an \
organization announcing its own news) | research_paper.

SOURCING - what the article's main claims rest on
- official_source: the organization involved said it itself, or an official document (bill text, \
filing, government release).
- on_record_reporting: the reporter cites named people, documents, or official statements.
- anonymous_sources: unnamed people ("people familiar with the matter").
- rumor_leak_social: rumors, leaks, social-media posts, or unverified claims.
- repeats_other_outlet: mainly repeats another outlet's report ("..., FT says"). Put that outlet's \
name in attributed_to.
- denial_or_correction: the story is about a denial, correction, or retraction.
- not_applicable: opinion or analysis without new factual claims.
attributed_to: the outlet being repeated, otherwise an empty string.
self_reported: true if the key claims are an organization's claims about its own performance \
(benchmarks, revenue, user numbers, "best" or "first") not yet independently verified.

AI RELATED
ai_related: true when AI is a central or significant part of the story, including AI's effect on \
markets, investment, companies, jobs, or policy (for example, AI stocks moving, funds raised for AI \
companies). false only when AI is mentioned in passing or not at all (for example, general election \
or market news that names AI once). Still fill in every other field.

SAME EVENT
You may be given recent stories Signality already has. If this item reports the same specific \
event as one of them (same announcement, deal, ruling, or release; not merely the same company or \
topic), set same_event_as to that story's id. Otherwise set it to "none"."""


def schema(cfg):
    factor = {
        "type": "object",
        "properties": {"reason": {"type": "string"}, "score": {"type": "integer", "enum": [1, 2, 3, 4, 5]}},
        "required": ["reason", "score"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "same_event_as": {"type": "string"},
            "headline": {"type": "string"},
            "summary": {"type": "string"},
            "why_it_matters": {"type": "string"},
            "topics": {"type": "array", "items": {"type": "string", "enum": [*cfg["topics"], "other"]}},
            "content_type": {"type": "string",
                             "enum": ["news", "opinion", "analysis", "press_release", "research_paper"]},
            "sourcing": {"type": "string",
                         "enum": ["official_source", "on_record_reporting", "anonymous_sources",
                                  "rumor_leak_social", "repeats_other_outlet",
                                  "denial_or_correction", "not_applicable"]},
            "attributed_to": {"type": "string"},
            "self_reported": {"type": "boolean"},
            "ai_related": {"type": "boolean"},
            **{f: factor for f in scoring.FACTORS},
        },
        "required": ["same_event_as", "headline", "summary", "why_it_matters", "topics",
                     "content_type", "sourcing", "attributed_to", "self_reported", "ai_related",
                     *scoring.FACTORS],
        "additionalProperties": False,
    }


def pick_article(conn, story_id):
    """The best article to read for a story: primary source first, then free-to-read, then any."""
    return conn.execute(
        """
        SELECT a.*, s.name AS source_name, s.type AS source_type
        FROM articles a JOIN sources s ON s.id = a.source_id
        WHERE a.story_id = ?
        ORDER BY (s.type = 'primary') DESC, a.paywalled ASC, (a.via IS NULL) DESC, a.id ASC
        LIMIT 1
        """,
        (story_id,),
    ).fetchone()


def candidates(conn, story_id, words, cfg):
    """Recent triaged stories whose headlines share words with this one (possible same event)."""
    since = (datetime.now(timezone.utc) - timedelta(hours=cfg["dedup"]["window_hours"])).isoformat(timespec="seconds")
    rows = conn.execute(
        """
        SELECT a.story_id, a.title, a.title_words, s.name AS source_name
        FROM articles a JOIN stories st ON st.id = a.story_id JOIN sources s ON s.id = a.source_id
        WHERE st.status = 'triaged' AND a.story_id != ? AND a.fetched_at >= ?
        """,
        (story_id, since),
    ).fetchall()
    scored = {}
    for r in rows:
        other = set(r["title_words"].split())
        if len(words & other) >= 2:
            score = similarity(words, other)
            if score > scored.get(r["story_id"], (0,))[0]:
                scored[r["story_id"]] = (score, r["title"], r["source_name"])
    best = sorted(scored.items(), key=lambda kv: -kv[1][0])[: cfg["triage"]["dedup_candidates"]]
    return [(sid, title, source) for sid, (_, title, source) in best]


def build_prompt(article, text, text_source, nearby):
    lines = [
        f"Today's date: {datetime.now(timezone.utc):%Y-%m-%d}",
        f"Source: {article['source_name']} (type: {article['source_type']})",
        f"Published: {article['published_at'][:10]}",
        f"Original headline: {article['title']}",
        "",
        "Text (full article):" if text_source == "full"
        else "Text (preview only - the full article is paywalled or unavailable):",
        text or "(no preview available; headline only)",
        "",
        "Recent stories Signality already has (possible same event):",
    ]
    lines += [f"  {sid}: {title} ({source})" for sid, title, source in nearby] or ["  none"]
    return "\n".join(lines)


def merge(conn, story_id, into_id):
    """Fold a duplicate story into an existing one (articles move; the old row is kept as history)."""
    moved = conn.execute("UPDATE articles SET story_id = ? WHERE story_id = ?", (into_id, story_id)).rowcount
    conn.execute(
        "UPDATE stories SET article_count = article_count + ?, last_seen_at = ? WHERE id = ?",
        (moved, db.utcnow(), into_id),
    )
    conn.execute("UPDATE stories SET status = 'merged', merged_into = ?, article_count = 0 WHERE id = ?",
                 (into_id, story_id))
    conn.commit()


def triage_story(conn, cfg, story_id, model=None, purpose="live"):
    """Triage one story. Returns the saved result dict, or {'merged_into': id}."""
    article = pick_article(conn, story_id)
    text, text_source = None, "snippet"
    if cfg["triage"]["fetch_full_text"] and not article["paywalled"] and article["via"] is None:
        text = article_text.fetch(article["url"], cfg)
        if text:
            text_source = "full"
    if text is None:
        text = article["snippet"]

    nearby = candidates(conn, story_id, set(article["title_words"].split()), cfg) if purpose == "live" else []
    data, cost = ai.ask_json(
        conn, cfg, task="triage", role="bulk", model=model, story_id=story_id,
        system=SYSTEM, prompt=build_prompt(article, text, text_source, nearby), schema=schema(cfg),
    )

    same = data["same_event_as"].strip()
    if purpose == "live" and same.isdigit() and int(same) in {sid for sid, _, _ in nearby}:
        merge(conn, story_id, int(same))
        return {"merged_into": int(same), "cost_usd": cost, "title": article["title"]}

    ratings = {f: data[f]["score"] for f in scoring.FACTORS}
    topics = [t for t in data["topics"] if t in cfg["topics"] or t == "other"]
    base, mult, final = scoring.importance(ratings, topics, cfg)
    if not data["ai_related"]:
        final = 0  # not AI news: store it, never send it
    row = {
        "story_id": story_id, "article_id": article["id"], "purpose": purpose,
        "model": model or cfg["models"]["bulk"], "created_at": db.utcnow(), "text_source": text_source,
        "headline": data["headline"], "summary": data["summary"], "why_it_matters": data["why_it_matters"],
        "topics": json.dumps(topics), "content_type": data["content_type"], "sourcing": data["sourcing"],
        "attributed_to": data["attributed_to"] or None, "self_reported": int(data["self_reported"]),
        "ai_related": int(data["ai_related"]),
        **{f: data[f]["score"] for f in scoring.FACTORS},
        **{f"{f}_reason": data[f]["reason"] for f in scoring.FACTORS},
        "base_score": round(base, 1), "topic_multiplier": mult, "importance": final, "cost_usd": cost,
    }
    cols = ", ".join(row)
    conn.execute(
        f"INSERT OR REPLACE INTO story_triage ({cols}) VALUES ({', '.join('?' * len(row))})",
        list(row.values()),
    )
    if purpose == "live":
        conn.execute("UPDATE stories SET status = 'triaged' WHERE id = ?", (story_id,))
    conn.commit()
    return {**row, "source": article["source_name"], "original_title": article["title"]}


def run(conn, cfg, limit=None, story_ids=None):
    """Triage new stories (newest first). Returns counts plus each result."""
    stats = {"triaged": 0, "merged": 0, "failed": 0, "too_old": 0, "cost_usd": 0.0, "results": []}
    if story_ids:
        ids = list(story_ids)
    else:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=cfg["triage"]["max_story_age_hours"])).isoformat(timespec="seconds")
        stats["too_old"] = conn.execute(
            "UPDATE stories SET status = 'too_old' WHERE status = 'new' AND first_seen_at < ?", (cutoff,)
        ).rowcount
        conn.commit()
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM stories WHERE status = 'new' ORDER BY first_seen_at DESC, id DESC LIMIT ?",
            (limit or cfg["triage"]["max_per_round"],),
        )]
    for story_id in ids:
        try:
            result = triage_story(conn, cfg, story_id)
        except ai.BudgetExceeded:
            raise
        except ai.AIError as e:
            conn.execute("UPDATE stories SET status = 'failed' WHERE id = ?", (story_id,))
            conn.commit()
            stats["failed"] += 1
            stats["results"].append({"story_id": story_id, "error": str(e)})
            continue
        stats["cost_usd"] += result["cost_usd"]
        stats["merged" if "merged_into" in result else "triaged"] += 1
        stats["results"].append(result)
    return stats


def show(result):
    if "error" in result:
        print(f"\n#{result['story_id']}  FAILED: {result['error']}")
        return
    if "merged_into" in result:
        print(f"\n↪ merged into story #{result['merged_into']}: {result['title']}")
        return
    partial = "  [partial: preview only]" if result["text_source"] == "snippet" else ""
    print(f"\n#{result['story_id']}  [{result['source']}]  importance {result['importance']}"
          f"  ({result['base_score']} x {result['topic_multiplier']})  ${result['cost_usd']:.5f}{partial}")
    print(f"  {result['headline']}")
    print(f"  {result['summary']}")
    print(f"  Why it matters: {result['why_it_matters']}")
    print(f"  topics={json.loads(result['topics'])}  type={result['content_type']}  "
          f"sourcing={result['sourcing']}{' (' + result['attributed_to'] + ')' if result['attributed_to'] else ''}"
          f"{'  SELF-REPORTED' if result['self_reported'] else ''}"
          f"{'  NOT AI -> stored only' if not result['ai_related'] else ''}")
    for f in scoring.FACTORS:
        print(f"  {f:<8}{result[f]}  {result[f + '_reason']}")


def main():
    parser = argparse.ArgumentParser(description="Triage new stories with Claude Haiku.")
    parser.add_argument("--limit", type=int, help="how many new stories to triage")
    parser.add_argument("--ids", help="comma-separated story ids to triage instead")
    args = parser.parse_args()
    cfg = load_config()
    conn = db.connect(cfg["storage"]["db_path"])
    ids = [int(x) for x in args.ids.split(",")] if args.ids else None
    stats = run(conn, cfg, limit=args.limit, story_ids=ids)
    for result in stats["results"]:
        show(result)
    done = stats["triaged"] + stats["merged"]
    print(f"\n{stats['triaged']} triaged, {stats['merged']} merged as duplicates, {stats['failed']} failed"
          f" | total ${stats['cost_usd']:.4f}" + (f" (${stats['cost_usd'] / done:.5f} per story)" if done else ""))


if __name__ == "__main__":
    main()
