# Signality — Progress Log

Read this at the start of every session.

## Current state
**Stage 1, Step 1 — done.** Project is live on GitHub (public):
https://github.com/Nickscottmoody/Signality

**Stage 1, Step 2 — done.** 16 sources approved and in `config.yaml`.

Next up: **Step 3 — build the fetcher** (read feeds, filter, remove duplicates, store in SQLite).

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

## Next
- [ ] Step 3: build the fetcher — read feeds, remove duplicates, store in SQLite
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
- **Reason** posts tech stories only every few days, so expect few stories from it.
- Publishing actions (creating public repos, changing visibility) must be run by Nicholas;
  Claude's permission settings block them. Regular `git push` to the existing repo is fine.
