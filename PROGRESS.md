# Signality — Progress Log

Read this at the start of every session.

## Current state
**Stage 1, Step 1 — done.** Project is live on GitHub (public):
https://github.com/Nickscottmoody/Signality

**Stage 1, Step 3 — done.** The fetcher reads all 16 feeds, filters, removes duplicates,
and stores stories in `data/signality.db`. Run it with `./.venv/bin/python -m signality.fetcher`.

Next up: **Step 4 — create the Telegram bot and send a test message** (needs Nicholas for @BotFather).

## Done
- [x] Saved the project brief as `CLAUDE.md`
- [x] Folders: `signality/` (code), `assets/` (Siggy images), `data/` (database, private), `design/` (design files)
- [x] Renamed Siggy images to `siggy-logo.png`, `siggy-alert.png`, `siggy-thinking.png`
- [x] `config.yaml` — every adjustable setting, with plain-English comments
- [x] `.gitignore` — blocks `.env`, `data/`, and the personal profile from GitHub
- [x] `.env.example` — the template for secrets (real values go in `.env`, never committed)
- [x] Python virtual environment `.venv` with Stage 1 packages installed
- [x] Tested all 11 proposed feeds: 10 live, Anthropic has no public RSS (swapped for Simon Willison's blog)
- [x] Installed GitHub CLI (`gh` 2.103.3, checksum verified against GitHub's published value)
- [x] Logged in to GitHub as Nickscottmoody; created public repo and pushed first commit
- [x] Source list approved: 16 sources (6 primary, 5 top-tier news, 4 AI specialists, Reason for
      viewpoint balance). Tested 30 candidates for freshness and AI focus; all 16 chosen are live.
- [x] Added `ai_filter_keywords` to config: free keyword filter for broad feeds (WSJ, Bloomberg,
      The Information, Reason) before any paid AI step
- [x] Database (`signality/db.py`): sources, stories, articles, fetch_runs; numbered migrations so
      later stages add tables without rebuilding. Removed sources are marked inactive, not deleted.
- [x] Duplicate helpers (`signality/dedup.py`) + 7 passing tests (`tests/test_dedup.py`)
- [x] Fetcher (`signality/fetcher.py`). First run: 16/16 sources ok, 345 read, 124 too old,
      26 not AI, 195 saved (193 stories, 2 grouped). Second run: 195 duplicates removed, 0 saved.

## Next
- [ ] Step 4: create the Telegram bot, send a test message (**needs Nicholas for @BotFather**)
- [ ] Step 5: run on a 15-minute schedule

## Open issues
- **Python HTTPS certificates:** this Mac's Python 3.12 cannot verify certificates on its own, so
  feeds must be fetched with `requests` (which carries its own certificate bundle), not
  `feedparser.parse(url)` directly. Already accounted for.
- **VentureBeat** returns "too many requests" unless we send a browser-style User-Agent.
  Set in `config.yaml` under `polling.user_agent`.
- **Anthropic** publishes no RSS feed. Revisit in Stage 3 when search/corroboration is added.
- **Dropped feeds:** VentureBeat (newest story 68 days old), The Verge, arXiv (~300 papers/day),
  Simon Willison. Old WSJ feed address was dead; WSJ moved to feeds.content.dowjones.io.
- **Reuters and AP** have no public feeds; we use Google News searches limited to their sites.
  Their links go through Google first, so the fetcher must follow them to the real article.
- **Paywalled** (WSJ, Bloomberg, FT, The Information): headline + preview only → mark "partial".
- **Political lean values in config.yaml are placeholders.** Replace with ratings from a public
  bias-rating site (e.g., AllSides) in Stage 2b.
- **Reason** posts AI stories only every week or two (first run: its 5 AI stories were 14-27 days
  old, past the 7-day cutoff, so 0 saved). Mostly opinion pieces → tag "opinion" in Stage 2b.
- **Free headline matching misses reworded duplicates.** Example: "Gemini 4 Carbon" from DeepMind vs.
  Ars Technica (similarity 0.38, threshold 0.6). Haiku duplicate detection in Stage 2a covers this.
  Kept threshold high on purpose: wrongly merging two stories is worse than missing a group.
- **Attribution chains:** Bloomberg ran "Nvidia tells clients to trim China business, FT says" —
  Bloomberg repeating FT, not independent confirmation. Stage 2b must detect "X says/reports" so
  these count as one source.
- **Google News links** for Reuters/AP still point to news.google.com, not the real article.
  Resolve them in Stage 2a when we need article text.
- Publishing actions (creating public repos, changing visibility) must be run by Nicholas;
  Claude's permission settings block them. Regular `git push` to the existing repo is fine.
