# Signality — Progress Log

Read this at the start of every session.

## Current state
**Stage 1, Step 1 — done.** Project is live on GitHub (public):
https://github.com/Nickscottmoody/Signality

**Stage 1 — complete.** Signality runs in the background on Nicholas's Mac (launchd service
`com.signality.agent`), checks 16 sources every 15 minutes, filters, de-duplicates, and stores
stories in `data/signality.db`. Telegram bot @Signalitynewsbot delivers messages.

Next up: **Stage 2a — summaries, importance + validity scoring, alert tiers, Siggy's images per
message type, and the Haiku vs. Sonnet comparison.**

## How to run / operate
| Do this | Command (from the project folder) |
|---|---|
| Check the news once | `./.venv/bin/python -m signality.fetcher` |
| Send a Telegram test message | `./.venv/bin/python -m signality.telegram` |
| Run the agent in the foreground | `./.venv/bin/python -m signality.agent` |
| Start / **restart** background service | `./scripts/install_mac_service.sh` (Nicholas runs this) |
| Stop background service | `./scripts/uninstall_mac_service.sh` |
| See what the agent did | `tail -20 data/signality.log` |
| Service startup errors | `~/Library/Logs/signality-launchd.log` |
| Run tests | `./.venv/bin/python -m pytest -q` |

**After changing any code, restart the service** — a running program keeps using the old code.
`config.yaml` changes do NOT need a restart; the agent rereads it every round.

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
- [x] `.env` filled: Telegram token, user ID, Anthropic key. All three verified with free API calls
      (Telegram getMe; Anthropic model list). Exposed codes from an earlier chat were revoked/replaced.
- [x] Telegram sender (`signality/telegram.py`): send_message / send_photo; test message via
      `./.venv/bin/python -m signality.telegram`. Siggy image paths in `config.yaml` under `siggy.images`.
- [x] Confirmed Anthropic account has claude-haiku-5-5, claude-sonnet-5-5, claude-opus-5-5 (the
      strings in config.yaml).
- [x] Agent loop (`signality/agent.py`): one fetch round every `polling.interval_minutes`, rereads
      config each round, a crashed round is logged and retried next round, never stops the loop.
      Logs to `data/signality.log` (rotating, ~3 MB max).
- [x] Background service: `scripts/install_mac_service.sh` / `uninstall_mac_service.sh` (launchd,
      starts at login, restarts on crash). Installed by Nicholas; verified running with no
      Desktop-permission errors and rounds completing on schedule.

## Next
- [ ] Stage 2a: add `anthropic` package; summaries (Haiku), 4-factor importance ratings, validity
      labels, alert tiers (🚨/🔔/📰/stored), Siggy image per message type, alert cap, morning digest
- [ ] Stage 2a: resolve Google News links; Haiku duplicate detection for reworded headlines
- [ ] Stage 2a: Haiku vs. Sonnet side-by-side on ~20 stories (**Nicholas reviews**, task #8)

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
- **Anthropic key format** starts with `sk-ant-usr` rather than the older `sk-ant-api`; verified
  working, so this is just the current format.
- **Telegram sender uses `requests`** (simple, synchronous). Two-way commands (/settings, /profile, …)
  will need `python-telegram-bot`, already in requirements.txt.
- **No checks while the Mac sleeps** (lid closed). The agent resumes on wake. Moving to a cloud
  server later (task #13) removes this gap.
- **Installing/starting the background service is blocked for Claude** by permission settings —
  Nicholas runs `scripts/install_mac_service.sh` (also needed to restart after code changes).
- **Google News links** for Reuters/AP still point to news.google.com, not the real article.
  Resolve them in Stage 2a when we need article text.
- Publishing actions (creating public repos, changing visibility) must be run by Nicholas;
  Claude's permission settings block them. Regular `git push` to the existing repo is fine.
