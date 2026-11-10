"""Web search (Tavily), with a hard limit so the free plan is never exceeded.

This module only talks to the search service and counts usage. Deciding what the
results mean happens in corroborate.py.

Tavily's free plan gives 1,000 credits a month (a basic search costs 1). Signality
caps itself per day and per month in config.yaml (search.*), counting from the
web_searches table, so it stops on its own well before the plan's limit.
"""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests

from .settings import secret

API_URL = "https://api.tavily.com/search"
PROVIDER = "tavily"
# Two-part country endings, so "bbc.co.uk" stays "bbc.co.uk", not "co.uk".
_SECOND_LEVEL = {"co", "com", "org", "net", "gov", "ac", "edu"}


class SearchError(Exception):
    """The search service couldn't be used (no key, limit reached, network, bad reply)."""


def domain_of(url):
    """'https://www.cnbc.com/2026/11/08/x.html' -> 'cnbc.com'."""
    host = (urlparse(url).hostname or "").lower()
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in _SECOND_LEVEL and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def same_organization(domain, other):
    """True for sister sites of one newsroom, e.g. 'bloomberglaw.com' and 'bloomberg.com'."""
    a, b = domain.split(".")[0], other.split(".")[0]
    if a == b:
        return True
    shorter, longer = sorted((a, b), key=len)
    return len(shorter) >= 3 and longer.startswith(shorter)


def source_domains(conn, cfg):
    """{domain: source name} for the sources we already follow.

    Google News sources (Reuters, AP) use the site named in their feed address; the
    others use the address their articles actually live at.
    """
    found = {}
    for s in cfg["sources"]:
        if s.get("via") == "google_news":
            m = re.search(r"site:([\w.-]+)", s["url"])
            if m:
                found[domain_of("https://" + m.group(1))] = s["name"]
            continue
        row = conn.execute(
            "SELECT url FROM articles WHERE source_id = ? ORDER BY id DESC LIMIT 1", (s["id"],)
        ).fetchone()
        if row:
            found[domain_of(row[0])] = s["name"]
    return found


def usage(conn, cfg):
    """Credits used today (your clock) and this month (UTC, when Tavily resets)."""
    now = datetime.now(ZoneInfo(cfg["digest"]["timezone"]))
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    count = lambda start: conn.execute(
        "SELECT COALESCE(SUM(credits), 0) FROM web_searches WHERE provider = ? AND searched_at >= ?",
        (PROVIDER, start.isoformat(timespec="seconds")),
    ).fetchone()[0]
    return {"today": count(day_start), "month": count(month_start)}


def allowance(conn, cfg):
    """How many more searches are allowed right now (0 = stop)."""
    s = cfg["search"]
    used = usage(conn, cfg)
    return max(0, min(s["max_per_day"] - used["today"], s["monthly_limit"] - used["month"]))


def search(query, cfg, *, start_date=None, exclude_domains=()):
    """Run one news search. Returns a list of {url, domain, title, published_at, snippet}.

    Raises SearchError on any problem, so a failed search never looks like "nothing found".
    """
    key = secret("TAVILY_API_KEY")
    if not key:
        raise SearchError("TAVILY_API_KEY is missing from .env")
    s = cfg["search"]
    body = {
        "query": query[:390],
        "topic": "news",
        "search_depth": "basic",          # 1 credit
        "max_results": s["max_results"],
        "include_answer": False,
        "include_raw_content": False,
    }
    if start_date:
        body["start_date"] = start_date
    skip = set(s.get("skip_domains", []))
    body["exclude_domains"] = sorted(skip | set(exclude_domains))
    try:
        r = requests.post(API_URL, json=body, headers={"Authorization": f"Bearer {key}"},
                          timeout=cfg["polling"]["request_timeout_seconds"])
    except requests.RequestException as e:
        raise SearchError(f"network: {type(e).__name__}") from e
    if r.status_code != 200:
        # 401 bad key · 429 too many requests · 432/433 plan or spending limit reached
        raise SearchError(f"HTTP {r.status_code}: {r.text[:200]}")
    try:
        results = r.json()["results"]
    except (ValueError, KeyError) as e:
        raise SearchError("reply was not the expected JSON") from e
    out = []
    for x in results:
        url = x.get("url") or ""
        if not url or domain_of(url) in skip:
            continue
        out.append({
            "url": url,
            "domain": domain_of(url),
            "title": (x.get("title") or "").strip(),
            "published_at": _iso(x.get("published_date")),
            "snippet": (x.get("content") or "").strip()[: s["snippet_chars"]],
        })
    return out


def _iso(text):
    """Tavily dates look like 'Sun, 08 Nov 2026 21:43:11 GMT'; store ISO, or None."""
    if not text:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            d = datetime.strptime(text, fmt)
            return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).isoformat(timespec="seconds")
        except ValueError:
            continue
    return None


def start_date_for(first_seen_at, days_before):
    """Search window start: a few days before we first saw the story (YYYY-MM-DD)."""
    return (datetime.fromisoformat(first_seen_at) - timedelta(days=days_before)).date().isoformat()
