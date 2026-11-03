# Signality — Progress Log

Read this at the start of every session.

## Current state
**Stage 1, Step 1 — project set up (local).** Not yet on GitHub.

## Done
- [x] Saved the project brief as `CLAUDE.md`
- [x] Folders: `signality/` (code), `assets/` (Siggy images), `data/` (database, private), `design/` (design files)
- [x] Renamed Siggy images to `siggy-logo.png`, `siggy-alert.png`, `siggy-thinking.png`
- [x] `config.yaml` — every adjustable setting, with plain-English comments
- [x] `.gitignore` — blocks `.env`, `data/`, and the personal profile from GitHub
- [x] `.env.example` — the template for secrets (real values go in `.env`, never committed)
- [x] Python virtual environment `.venv` with Stage 1 packages installed
- [x] Tested all 11 proposed feeds: 10 live, Anthropic has no public RSS (swapped for Simon Willison's blog)

## Next
- [ ] Step 1b: GitHub account + login, then create the repo and first commit (**needs Nicholas**)
- [ ] Step 2: approve the starter source list in `config.yaml` (**needs Nicholas**)
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
- `gh` (the GitHub command-line tool) is not installed on this Mac yet.
