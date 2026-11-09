# Signality — Progress Log

Read this at the start of every session.

## Current state
**Stage 1, Step 1 — done.** Project is live on GitHub (public):
https://github.com/Nickscottmoody/Signality

**Stage 1 — complete.** Signality runs in the background on Nicholas's Mac (launchd service
`com.signality.agent`), checks 16 sources every 15 minutes, filters, de-duplicates, and stores
stories in `data/signality.db`. Telegram bot @Signalitynewsbot delivers messages.

**Stage 2a, Step 1 — done.** Claude connected through `signality/ai.py` with a cost meter
(`ai_calls` table) and budget guard (warns at 80%, hard stop at $10/month).

**Stage 2a, Step 2 — done.** Haiku triages each new story (summary, topics, sourcing, 4 factor
ratings with reasons, same-event check); code computes importance. Built but **switched off**
(`triage.enabled: false`) until the cost is approved in step 6.

**Stage 2a, Step 3 — done.** Validity labels from rules in code (`validity.py`), with label history;
Sonnet double-check before any 🚨 (`alert_check.py`). Not yet wired into delivery (step 4).

**Stage 2a, Step 4 — done.** Delivery built (`delivery.py`, `messages.py`, Telegram renderer):
🚨/🔔/📰 tiers, 3/day alert cap, Sonnet gate, 8am Central digest, budget notices. **Switched off**
(`delivery.enabled: false`). Preview messages of all three formats sent to Nicholas's phone.

**Stage 2a, Step 5 — in progress.** Haiku vs. Sonnet compared on 21 stories (`signality/compare.py`,
report in `data/reports/`). **Decision: Haiku stays for triage** (≈$1/mo vs ≈$20.50/mo for Sonnet;
all 84 factor ratings within 1 point; same validity label 21/21). Sonnet stays for 🚨 alert checks.
Nicholas's tuning decisions: **topic bonus ×1.1** (jobs, finance_analytics), and **🔔 silent messages
folded into the digest** (`delivery.silent_messages: false`). Phone gets only the 8am digest plus rare 🚨.

**Stage 2a, Step 5 — done.**

**Stage 2a, Step 6 — in progress.** `triage.enabled` and `delivery.enabled` are **true**. Backlog: 138
recent stories scored once by hand ($0.056; 28 reworded duplicates merged), 617 older marked too_old.
Today's (Nov 9) digest skipped on purpose (switched on after 8am) → first real digest Nov 10, 8am CT.
Service restarted on new code (13:38 CT; first round logged `triage:`). Install script fixed: it now
waits for the old copy to stop (first attempt failed with "Bootstrap failed: 5").
Digest window changed from a fixed 24h to "since the last digest, max 48h" so skipped days (like
today) and days the Mac was off don't drop stories. Restarted again 13:39 CT on this code; clean.

**Stage 2a — built and live.** ✅ First real 🚨 alert delivered Nov 9, 1:55pm CT ("Nvidia CEO Jensen
Huang admits infidelity amid probe…", 69, 🟢 Likely); Nicholas confirmed it arrived. Sonnet declined
the other candidate ("OpenAI and Anthropic valuations fall", 70) for thin, preview-only sourcing.
Not yet observed: the first real digest (Nov 10, 8am CT) and a full day of costs.

**Stage 2b, Step 1 — done (code), not yet live.** Haiku's triage call now also returns up to 4
checkable claims per story (`claims.py`, migration 7: `claims` + `claim_events` history). Labels come
from rules; only claims genuinely **in doubt** stay open (allegations, leaks, anonymous/unconfirmed
reports, plans, self-reported results). Routine facts are labeled but `not_tracked` — Nicholas's brief
says every Reported claim stays open; this narrows it to claims that could turn out wrong.
Test on 18 stories: 19 claims, 9 open (e.g. NYT memo "China recruited Alice Huang" 🟡 open;
Anthropic "Fable 5.2 30% faster" 🏷️ open; Meta $60B program due 2027-03-31). ~$0.0006/story.

Claims are now written as plain checkable statements with the claimant kept separate ("Jensen Huang had a
romantic relationship with Alice Huang" — claimed by "US intelligence memo, as reported by the FT"). The
old "the memo alleged…" phrasing made Haiku flip-flop (50/50); the new phrasing gave 4/4 consistent.

**Stage 2b, Step 2 — done (code), not yet live.** `resolution.py` checks each new article against open
claims: free keyword match → Haiku first pass (`claim_match`) → Sonnet final call (`claim_resolve`) only
when Haiku thinks it may settle a claim. New independent outlet supporting 🟡/🟠 → 🟢 by rule. Sonnet's
"no change" is recorded too (`checked` events). Progress cursor = article id (`claims_checked_through_id`).
Caps per round in config (`claims.*`). Bug fixed: Haiku returns "Claim 24", code expected "24".
Backfill over Nov 7-9 (152 articles, 62 checks, $0.016): the Huang/Alice Huang relationship claim went
🟡 → 🟢 (Bloomberg) → ✅ (Nvidia board message naming her, via TechCrunch); the spy-recruitment claim went
🟡 → 🟢 and stays open. Sonnet correctly refused to confirm from an article that didn't name her.

**Stage 2b, Step 3 — done (code), not yet live.** 🧾 Receipts (`receipts.py`, migration 8
`claim_receipts`, migration 9 `claim_events.detail`). Nicholas's choice: receipts go in a 🧾 section of the
8am digest; a claim from a saga he got a 🚨 about gets its receipt right away (silent, yellow Siggy).
Receipt = claim (quoted) · first date + label + claimant · outcome date + one-line reason · links to the
original and the evidence. Sonnet now returns a one-sentence `receipt_line` for the reader plus its full
reasoning (stored in `detail`). One receipt pending (Huang/Alice Huang relationship ✅) → will go out
live after the restart, since the Nvidia saga alerted.

Next up: **restart to make 2b Steps 1-3 live; confirm the live receipt arrives; then 2b Step 4 — bias
ratings + skew metric.** Still to confirm: Nov 10 8am digest + first full day's cost.

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
| Health + cost check | `./.venv/bin/python -m signality.status` |
| Haiku vs. Sonnet report | `./.venv/bin/python -m signality.compare` |
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
- [x] Stage 2a step 1: `anthropic==1.17.0` (latest 1.x; 2.x exists but our reference docs cover 1.x —
      revisit). `ai.ask_json()`: model + effort per role from config, JSON-schema replies, cached
      system prompt, every call priced and logged in `ai_calls`. Budget guard via `budget_status()`.
      Prices + effort in config.yaml. First real call (Haiku): $0.000046. 10 tests passing.
- [x] Stage 2a step 2: `triage.py` (one Haiku call per story, cached instructions, JSON schema),
      `scoring.py` (weights → 0-100, topic multiplier, tiers), `article_text.py` (full text via
      trafilatura when free; else preview → "partial"). Migrations 3-4: story status, story_triage
      table (per model + purpose, so comparisons fit), ai_related flag. Haiku same-event check merged
      The Information + AP "Google/schools AI" (reworded) correctly. 15 tests passing.
      Sample of 22: avg $0.00034/story → ~$1.00-1.50/month at 100-150 stories/day.
- [x] Stage 2a step 3: `validity.py` decides ✅🟢🟡🟠🔴💬 from triage sourcing + independent outlets
      (repeats like "FT says" and an outlet relaying another count once; primary source → ✅;
      opinion → no label). `story_validity` keeps every label change (for receipts later).
      Labels refresh for free each round as outlets join. `alert_check.py`: Sonnet reviews any
      alert-tier story (importance + sourcing + label check), ~$0.003-0.005 each. Tested on 3 real
      stories: all correctly judged "not alert-worthy" with specific reasons. Dedup candidate check
      widened (one shared distinctive word) after Canva duplicates slipped through; merged them.
      25 tests passing.
- [x] Stage 2a step 4: `messages.py` (platform-neutral StoryCard/Message), `telegram.deliver()`
      renders them (🚨 = red Siggy photo + caption, with sound; 🔔 = text, silent; 📰 digest = logo
      photo + numbered list + separate "Unconfirmed" section; notices = logo). `delivery.py`:
      routing (🟠/🔴 → digest only, never ping), Sonnet verdict reused (never paid twice), daily cap
      in Central time, fresh-only (12h) immediate sends, digest once/day at 8am, budget notices at
      80% / 100% once a month. `deliveries` table keyed by recipient = platform:account (migration 6).
      Digest timezone switched to America/Chicago (GitHub page showed CST). 31 tests passing.
- [ ] Later: resolve Google News links (Reuters/AP are headline-only → "partial" for now)
- [x] Stage 2a step 5 (part 1): Sonnet run on the same 21 stories ($0.15). `compare.py` prints agreement,
      cost, and messages/day under 5 bonus options (×1.3 ≈28 🔔/day, ×1.1 or +5 ≈9, none ≈5) and writes
      an HTML side-by-side report. Sonnet scores more generously (≈37-50 🔔/day). Haiku chosen.
- [x] Stage 2a step 5 (part 2): bonus ×1.1; 🔔 folded into digest (route() sends 50-74 to digest when
      `delivery.silent_messages` is false; declined/over-cap alerts also wait for the digest). 32 tests.
- [x] Stage 2a step 6: switched on Nov 9; backlog scored; service restarted on new code; status command.
- [x] First real alert end-to-end (Nov 9, 1:55pm CT): fetch → Haiku → Sonnet gate → Telegram
- [ ] Confirm first real digest (Nov 10 8am) + first full day's cost

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
- **Resolved in step 5:** the ×1.3 topic boost flooded the 🔔 tier (~28/day); now ×1.1 and 🔔 folded
  into the digest. Note: this departs from the brief's "50-74 = 🔔 silent message" by Nicholas's choice.
- **"Not AI" check:** Federal Register now uses the keyword filter (its search matches passing
  mentions). Haiku also flags `ai_related`; false → importance 0, stored only. Rule: AI must be
  central/significant, incl. AI's effect on markets/jobs/policy. Borderline: "Democrats' win rattles
  trades from AI stocks to crypto" judged not AI from the preview — review in step 5.
- **Nicholas may change `polling.interval_minutes` to 30 or 60 later** (to save data on a phone
  hotspot: ~0.7 MB per round ≈ 2 GB/month at 15 min). Never assume 15 minutes anywhere in code —
  always read the interval from config (e.g., alert timing, "breaking" windows, digest windows).
- **No checks while the Mac sleeps** (lid closed). The agent resumes on wake. Moving to a cloud
  server later (task #13) removes this gap.
- **Installing/starting the background service is blocked for Claude** by permission settings —
  Nicholas runs `scripts/install_mac_service.sh` (also needed to restart after code changes).
- **One notification per message (Nicholas's request):** alerts/notices use photo + caption when the
  text fits (≤1024 chars as Telegram counts them); otherwise, and always for the digest, the text is
  sent as ONE message with Siggy shown above it via a link preview of the public image URL
  (`siggy.image_urls`, raw.githubusercontent.com — **requires the GitHub repo to stay public**).
  The digest keeps as many top stories as fit in one message (~12) and ends with "…plus N more".
- **Developing stories (stopgap until Stage 3b):** the Nov 2026 Nvidia/Jensen Huang spy-affair saga
  produced 30+ distinct articles that are NOT the "same event". Digest now folds stories whose Haiku
  headlines share ≥2 distinctive words (`dedup.related`) under the top one ("➕ N related"), and a
  saga that already triggered a 🚨 in the last 24h can't alert again. Real threading/updates = Stage 3b.
- **Alert cutoff 75 → 65 and daily cap 3 → 5 (Nicholas, Nov 9).** Main Nvidia-saga pieces scored 64-69
  (breadth 3), so 75 would never have alerted on it. At 65, ~1 story/day goes to Sonnet (≈$0.15/mo);
  Sonnet is the real gate. Departs from the brief's "75-100 = 🚨, max 3/day" by Nicholas's choice.
- **Alerts only for news first seen in the last 12h** (`delivery.max_age_hours`). The Nvidia probe story
  (77) was 13h old at switch-on, so it correctly went to the digest instead of alerting.
- **Code changes need a service restart** (`scripts/install_mac_service.sh`); config changes don't.
- **Siggy image choice:** 🚨 alerts get red Siggy; digest + notices get the yellow logo; 🔔 silent
  messages are text-only by default to keep the chat readable (`delivery.image_on_silent`).
  Brief says "logo for normal messages" — confirm with Nicholas.
- **Unverified stories never alert** (brief rule) — step 4 must route 🟠/🔴 to the digest only.
  Real "investigate first" comes with Stage 3 search.
- **Google News links** for Reuters/AP still point to news.google.com, not the real article.
  Resolve them in Stage 2a when we need article text.
- Publishing actions (creating public repos, changing visibility) must be run by Nicholas;
  Claude's permission settings block them. Regular `git push` to the existing repo is fine.
