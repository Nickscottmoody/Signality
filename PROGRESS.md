# Signality — Progress Log

Read this at the start of every session.

## Start here (new session checklist)

**Where we are:** Stages 1, 2a, 2b, 2c are complete and live (2c finished Nov 9: chat commands, /profile,
"🎯 How it affects you"). **Stage 3 in progress** (step 1 story corroboration live Nov 9; step 2 claim
search live Nov 9; next: step 3 developing stories; see the Stage 3 plan under "Current state").
**Task #10 done (Nov 10):** the first 8am digest arrived as ONE message, looked right, and the 🎯 note
fit him. But a 🧾 receipt arrived as a SEPARATE message 4 seconds before the digest (claim 121, Anthropic
~$1.4T IPO valuation, confirmed 8:13 CT from Anthropic's updated filing via TechCrunch; sent "live" because
its saga got a 🚨 at 6:59 CT). Nicholas then chose: receipts are never their own message (see Decisions). Overnight: claim search ran 10/10 (claim 37 "the woman is a suspected
Chinese spy" → 🔴 disputed: China called it a smear, AP/PBS say only "alleged"); 30/30 story searches; 2
alerts today (Anthropic $1.4T IPO 87, Gemini 4 Carbon 70). Step 3 (developing stories) is next.

**Working rules we settled on**
- Teach per CLAUDE.md: one step at a time, plain language, 🛑 YOUR TURN blocks for anything only Nicholas can do.
- **Nicholas runs** `./scripts/install_mac_service.sh` (restart) and anything that publishes (Claude's
  permissions block both). Claude can commit and `git push` normally.
- **Code change → service restart needed. `config.yaml` change → no restart** (reread every round).
- Commit + push after every working step; update this file; scan staged files so `.env` / `data/` never ship.
- Python: `./.venv/bin/python`. This Mac's Python can't verify HTTPS certs → always fetch with `requests`.
- Claude API code: load the `claude-api` skill first; SDK pinned `anthropic==1.17.0`; every call goes
  through `signality/ai.py` (`ask_json`: priced, logged, budget-guarded).
- Never ask for secrets in chat; they live only in `.env`.
- Phone previews: mark "🧪 PREVIEW" and don't record them as deliveries. When re-running AI on real stories
  for tests, use stories first seen >12h ago (fresh ones can trigger real alerts).
- Every Telegram message must arrive as ONE notification (photo+caption, or text with Siggy shown above it).
- Platform-ready rules in CLAUDE.md: core never imports Telegram; users = platform + account id; per-user
  settings/profile in the DB, config.yaml = defaults.

**Nicholas's decisions (don't re-litigate)**
- Models: **Haiku** = triage, claim extraction, first-pass checks. **Sonnet** = 🚨 alert checks, claim
  decisions. **Opus not used** (tested in 2b: no gain at 2.3× cost).
- Alerts: cutoff **65**, max **5/day**, only news first seen ≤12h, Sonnet must agree, one alert per saga/24h.
- Topic bonus **×1.1** (jobs, finance_analytics). **🔔 silent messages off** (`delivery.silent_messages:
  false`) → 50-64 lead the digest.
- Digest **8am America/Chicago**, covers everything since the last digest (max 48h), ONE message (~12 stories),
  related stories folded ("➕ N related").
- Receipts (**changed Nov 10**): NEVER a message of their own ("I don't want to get spammed"). A receipt
  for a saga he got a 🚨 about is **added to that original alert by editing it** (no new notification),
  and every receipt is listed in the next morning digest. Rejected: separate live receipt messages (the
  old way; one arrived 4s before the digest), digest-only. Only claims genuinely in doubt are tracked;
  claim text is a plain fact, claimant kept separate; one record per claim (`same_as`).
- Sources: **17** (Washington Examiner added for balance); lean from AllSides (checked 2026-11-09).
- Developing stories (step 3, Nicholas Nov 10): updates on a story go in the **digest**; an update that
  itself scores **65+** may **alert** him.
- "🎯 How it affects you": **strict bar** (~3 in 10 stories; generic market/hiring links skipped), 1-2 sentences.
- Budget **$10/month**; expected running cost ~$2-3/month (`python -m signality.status`).
- Search service (task #11, Nov 9): **Tavily**, free plan (1,000 searches/month), **no card** so it can
  never charge; cap searches/day in config to stay under. Exa was the alternative ($10/month free credit).
  Key in `.env` as `TAVILY_API_KEY`.

**Recovered from the first session (Stages 1-2b), not recorded elsewhere**
- Preferences: blank line between source links and the note on 🚨 alerts (keep the alert format, he likes
  it). Few pings: digest at the same time every morning + alerts only when they truly clear the bar.
  Repo is public on purpose (LinkedIn portfolio): keep README and commits presentable. Credible sources over volume.
- Rejected, don't re-suggest: adding sources just for credibility (independence > count; let data decide);
  Washington Times (Examiner only, to limit echo coverage); topic bonus ×1.3 / ×1.15 / +5 / none (×1.1
  chosen); receipts digest-only or always-live (chose digest + live for alerted sagas); Haiku for claim
  decisions; a mid-day catch-up digest; yellow Siggy on every 🔔.
- Promised for later: **source track-record review after a few weeks** (per source: how often first, how
  often only echoing others, how often its claims hold up → add sources that fill gaps, drop pure echoes;
  feeds the long-term source-reputation feature).
- How Nicholas works: decisions that change what he receives (alert counts, thresholds, sources) are
  offered as choices with a "(Recommended)" pick; technical calls are Claude's. Real measured costs, not
  guesses. Show only the one command to run now; label on/off commands clearly.
- Gotchas: git is 2.15 (no `git init -b` etc.); BSD `sed -i ''`; compare dates as Python ISO strings
  (SQLite `datetime('now')` uses a space, not `T`); re-running live triage on a stored story also runs the
  same-event merge and overwrites the live row (claims skipped if present); a new migration is applied by
  whichever process connects first, the old service ignores it; Telegram: user must press Start first,
  caption limit counts visible UTF-16 text, `link_preview_options`/`reply_markup` are JSON strings in form
  data, Siggy-above-text needs the public raw GitHub URLs; structured outputs: ids as strings ("Claim 24"),
  parse digits; schema/system changes invalidate the prompt cache once; local HTML report previews need
  `python3 -m http.server`; Reuters/AP via Google News are headline-only ("partial").

**Stage 3 — what to build (from CLAUDE.md), one step at a time**
- (a) Search for corroboration on single-source stories and open claims. Needs Nicholas's **task #11**:
  pick a search service (e.g. Tavily or Exa: compare current prices/free tiers first, recommend one), he
  creates the account and puts the key in `.env` (tell him the exact variable name; never in chat).
  Also: "never send an Unverified story as a 🚨 without investigating it first" becomes real here.
  Count only independent sources (echoes = one source). Keep within the $10/month budget; measure cost.
- (b) Track developing stories (sagas): send updates and receipts. Replaces the stopgap "➕ N related"
  folding and the "one alert per saga per 24h" rule (see Open issues: Developing stories).
- (c) 👍/👎 buttons on stories → the agent suggests preference changes (topics, thresholds), Nicholas
  approves (**task #12**). Two-way chat already exists (`chat.py` + `telegram_bot.py`, button codes ≤64
  bytes, prefix per feature like `pf:`); per-user settings belong in the DB, config.yaml = defaults.
- Also in the brief, not built yet: `/threshold`, `/alertcap`, `/mute`, `/unmute`, `/settings` commands.

**Stage 2c — what was built (from CLAUDE.md)**
- `/profile` onboarding interview in Telegram: ~12 questions, one at a time, tap buttons where possible.
  Topics listed in CLAUDE.md. Save a short profile (<150 words), show it, Nicholas approves/edits before saving.
- Commands `/profile`, `/myprofile`, `/editprofile`, `/deleteprofile`; ask every 3 months if anything changed.
- **Telegram is send-only today.** Commands need two-way messaging (`python-telegram-bot` is already in
  requirements.txt). Accept commands only from `TELEGRAM_USER_ID`. Keep it platform-ready (handlers thin,
  logic in core).
- Profile stored locally only (DB under `data/`, which is gitignored), per user, never in the public channel.
- "🎯 How it affects you": Sonnet writes 1-2 sentences after "Why it matters" on 🚨 alerts (and 🔔 if ever
  re-enabled); digest items only when strongly relevant; skip when there's no real connection; lay out
  options, never instructions; sometimes end with a question.
- Nicholas's **task #10**: do the interview, review the profile and the first ~10 notes.

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

**Steps 1-3 LIVE (restart 14:31 CT, Nov 9).** ✅ First real 🧾 receipt delivered live at 14:32 CT (Huang /
Alice Huang relationship → Confirmed); Nicholas confirmed it arrived.

**Stage 2b, Step 4 — done.** Lean labels replaced with AllSides ratings (checked 2026-11-09; noted per
source in config.yaml). Corrections vs. my original guesses: Bloomberg is Center (not lean-left); Reason
is Center since Sept 2024 ("clear libertarian bias"), not lean-right. That left NO right-leaning source,
so Nicholas approved adding **Washington Examiner (Technology)** — AllSides Lean Right, ~70% AI stories.
17 sources now. `bias.py` audits share of ✅/🟢 vs 🟠/🔴 labels by lean (news outlets only, opinion and
primary sources excluded), with weekly buckets and a "too few to judge" flag under 30 stories; summary
in `signality.status`. First run: Center 15% strong (n=92); other groups too small so far. 54 tests.
No restart needed: sources and config are reread every round (status/bias are separate commands).

**Stage 2b, Step 5 — done (task #9).** `compare_claims.py` ran the live claim-decision prompt through
Haiku, Sonnet, and Opus on 11 cases: 5 real (all Nvidia-saga or Anthropic, all correctly "no change") +
6 practice cases written to test the rules (interested-party denial → disputed, outlet correction →
walked back, slipped launch → delayed, 600 confirmed vs 3,000 reported → disputed, independent 28% test of
a 30% claim → confirmed, echoes of one rumor → no change). **All three models agreed on all 11 and got all
6 practice cases right.** Cost per decision: Haiku $0.0003, Sonnet $0.0044, Opus $0.0103. Receipt wording:
Opus slightly crisper, Sonnet adds attribution/dates, Haiku a bit clunkier. **Decision (Nicholas): keep
Sonnet; Opus not worth it.** Caveats: small sample; real pool was thin (claims only hours old). Re-run
`python -m signality.compare_claims` (delete data/reports/claim-cases.json first) after a few weeks of
real resolutions. Report: data/reports/claims-haiku-sonnet-opus-2026-11-09.html.

**Duplicate claims fixed.** The same claim was being saved once per story (e.g. 6 wordings of "Alice Huang
was recruited by China's spy agency"), which would have sent duplicate receipts.
- Going forward: Haiku's triage call sees up to 12 claims already tracked on the subject and marks a
  repeat with `same_as`; the existing claim gets a `repeated` "also reported in …" event instead of a
  copy (test: 2 of 3 repeats linked; the miss was a claim not in the list, hence 8 → 12).
- Cleanup: `claims.merge_existing_duplicates()` (Haiku groups same-meaning claims per subject) + one
  manual merge (decided_by `review`) of three "Nvidia opened an investigation" claims Haiku kept apart.
  51 → 37 unique claims. Copies kept with status `duplicate` + `duplicate_of` (migration 10). Merges
  never create receipts.
- Accuracy fix: claim #58 "Huang was the target of a foreign intelligence effort" had been ✅ Confirmed
  "by Nvidia", but Nvidia only said it was investigating REPORTS of it. Corrected to 🟡 open (event
  decided_by `review`), and the extraction rule now says official_source only when the organization
  states the claim as fact, not when it says it's investigating reports.
57 tests passing.

**Stage 2b — complete and live** (restart 15:09 CT Nov 9; 17/17 sources ok; claim checks running).
Month-to-date AI spend $0.47 (includes one-off comparison tests).

Next up: **confirm the Nov 10 8am digest (first one; should include a 🧾 Receipts section only if a claim
resolves overnight) + first full day's cost; then Stage 2c — onboarding interview (/profile), personal
profile, and "🎯 How it affects you" (task #10).**

**Stage 2c plan (5 steps):** 1) two-way chat: Siggy hears commands · 2) `/profile` interview with tap
buttons + profile approval · 3) `/myprofile` `/editprofile` `/deleteprofile` + 3-month check-in ·
4) "🎯 How it affects you" (Sonnet) on 🚨 alerts and strongly relevant digest items · 5) Nicholas's task #10.

**Stage 2c, Step 1 — done (code), waiting for restart.** Health check first (Nov 9, 19:28 CT): 17/17
sources ok, only a one-round Wi-Fi blip at 15:35; today $0.33 (incl. one-off tests), month $0.50, pace
$1.67/month. Two-way chat: `chat.py` (core: commands registry, `/start`, `/help`, button handler;
`/profile` etc. listed as "coming soon"), `telegram_bot.py` (long polling in a background thread of the
agent; answers only `TELEGRAM_USER_ID` in a private chat; removes tapped buttons; first run skips
messages older than 15 min but answers newer ones; offset in `app_state`; logs once per outage; sets the "/" command menu). `Reply` added to
`messages.py`; `send_message`/`send_photo` take tap buttons. `chat.enabled` in config (no restart needed
to switch). Database switched to WAL so the chat thread and news loop don't block each other.
Note: only ONE program can listen to the bot at a time — don't run `python -m signality.telegram_bot`
while the service runs. 66 tests. **Live** after Nicholas's restart (19:47 CT); /help replied. ✅

**Stage 2c, Step 2 — done (code), waiting for restart.** `/profile` interview (`profile.py`): 12 questions
(status, field, job, 1-3yr goals, industries, skills, AI use, excites, worries, location, impact areas,
off-limits) one at a time; tap buttons for status/industries/AI use/areas (multi-pick with ✅ ticks + Done),
typing always accepted, every question skippable, `/cancel` stops. Tapped questions are edited in place to
show the answer. Sonnet (`profile_write`, role high_stakes) writes a ≤150-word second-person profile from
the answers only (no invented details, no inferred sensitive traits, "Off-limits:" sentence kept); Nicholas
sees it with ✅ Save / ✏️ Change something (types the change, Sonnet rewrites) / 🔁 Start over. Nothing is
saved before Save. Migration 11: `users` (platform + account_id), `user_profiles` (answers, summary,
next_checkin_at = +90 days), `chat_sessions` (interview progress survives restarts). Config: `profile.max_words`,
`profile.checkin_days`. Sample run on made-up answers: 92 words, change request handled, $0.0067 for 2 calls.
"typing…" shown while Siggy works. 76 tests. **Live** (restart 19:58 CT). ✅ Nicholas did the real interview
and saved his profile (136 words, 1 Sonnet call; next check-in Feb 7, 2027).

**Stage 2c, Step 3 — done (code), waiting for restart.** `/myprofile` (profile + saved date + next check-in,
buttons to edit or redo), `/editprofile` (12 answer buttons → that one question again, showing the current
answer → Sonnet updates the saved profile from the change, keeping earlier hand edits → ✅ Save / ✏️ Change
something / ↩️ Keep my old profile), `/deleteprofile` (needs a confirming tap; erases profile + answers).
Check-in: the agent loop sends "🎯 Quick check-in" when `next_checkin_at` passes, only 8am-8pm Central,
then schedules the next one 90 days out (no nagging if ignored). Dates shown on Nicholas's clock. 81 tests.
**Live** (restart 20:06 CT); Nicholas confirmed /myprofile and /editprofile work. ✅

**Stage 2c, Step 4 — done (code), waiting for restart.** "🎯 How it affects you" (`impact.py`, migration 12
`impact_notes`: per user per story, skips stored with their reason so nothing is paid twice). 🚨 (and 🔔 if
re-enabled): one Sonnet call per story (`impact_note`), shown after "Why it matters". Digest: ONE Sonnet call
(`impact_digest`) over only the stories that fit in the message, confirmed ones only (never personalize a
rumor), max `impact_notes.digest_max_notes` (3). Rules: specific link to the profile or skip; market/valuation
moves and "hiring might slow" don't qualify alone; 1-2 sentences; options not instructions; uncertainty
inside the sentence; code lets ~1 in 3 alert notes end with a question (story_id % 3), digest at most one.
First prompt was too loose (7/10 notes, three near-identical "market rout → hiring" notes, a question on
almost every one) → tightened: 3/10, all specific. Measured: ~$0.0025 per alert note, $0.007-0.012 per
digest → ~$0.45/month. Preview without sending: `python -m signality.impact --preview 10`. 89 tests.
**Live** (restart 20:17 CT, migration 12 applied). **Decision (Nicholas, Nov 9): keep the strict bar** (~3 in
10 stories get a note). Open: his review of the first real notes (task #10), starting with the Nov 10 digest.

**Stage 3 plan (5 steps):** 1) corroboration search on single-source stories · 2) the same search for
open claims (more 🧾 receipts) · 3) developing stories: follow a saga, send updates (replaces "➕ N related")
· 4) 👍/👎 buttons → preference suggestions Nicholas approves (task #12) · 5) `/settings` `/threshold`
`/alertcap` `/mute` `/unmute`.

**Stage 3, Step 1 — done.** Nicholas chose **Tavily** (task #11 done: free
plan, no card, key in `.env` as `TAVILY_API_KEY`, verified with a test search). `search.py` (Tavily over
`requests`, topic=news, 1 credit/search, usage counted from `web_searches`; caps `search.max_per_day` 30 and
`search.monthly_limit` 950) + `corroborate.py` (picks 🟡/🟠 stories ≥40 importance, ≤36h old, waits 2h so
feeds can find outlets for free — alert-level stories searched at once, before the 🚨 decision; ONE search
per story; Haiku judges each page: own_reporting / repeats_other / primary / official_confirmation / denial
/ not_same_event / low_quality / unclear). Code rules overrule the model where it slipped in testing:
aggregators (Yahoo, MSN, …) never count; "primary" must be the organization's own site (a news site quoting
Meta's blog was called primary); a site judged both "own" and "copy" gets no credit (Kitco/Yahoo); sister
sites (Bloomberg Law for Bloomberg) and social/video/directory pages are excluded. Prompt fixes: "the
headline's specific news must match, not its background" (a CNBC page about the Marvell deal had counted for
a story about betting odds on the deal); wire services under their own name = own reporting. Migration 13:
`web_searches` + `web_results` (subject_type story|claim, every page kept with the verdict and why).
`validity.decide` adds web outlets (by name, never double-counting a feed outlet); reasons say "(X found by
web search)" or "Web search found no independent confirmation yet." Found pages are linked in messages.
Tested on 8 real stories (13 searches): #668 ✅ (Nvidia's own board statement), #708 🟢 (BBC + Reuters),
#721 🟢, #724 🟢, others correctly unchanged. Cost: ~$0.0005 AI per search → ≤$0.45/month at the cap.
`python -m signality.corroborate --list` / `--story N`. 106 tests.
**Live** (restart 21:03 CT): first round searched 5 stories, 2 labels changed. Spot-check caught a bad ✅:
"Law firms race to file suits against Nvidia" was "confirmed" by Nvidia's probe statement and pages about
the stock drop (background, not the lawsuits). Fix: Haiku first writes the story's `key_fact` (stored,
migration 14) and answers `reports_key_fact` per page; code drops any page that says no. Re-tested: #806
back to 🟡 (correct); #668 ✅ and #681 🟢 still hold. 107 tests. **Live** (restart 22:10 CT, migration 14 applied, clean round). ✅

**Stage 3, Step 2 — done.** Web search for open claims (`claim_search.py`).
Each round up to 2 claims (`search.claims_per_round`), 10/day kept for claims inside the 30/day total
(`search.claims_per_day`; stories get the other 20). A claim is first searched once its article is ≥12h
old, then every 3 days; plans not yet due and self-reported performance claims every 14 days. Order: never
searched → past due date → story importance. Query = claim text minus "According to X," / "X reports
that". The claim's own outlet (incl. its real site for Google News sources), its sister sites,
aggregators and pages already judged for that claim are skipped. Haiku (`claim_search_match`) gives each
page a relation (same enum as resolution.py) + independent; code: pages dated before the claim can't
settle it, aggregators never independent. Settling pages (max 3, strongest first) → Sonnet
(`claim_resolve_web`, the same DECIDE_SYSTEM + `evidence_id`), reading the page's full text when free
(`search.evidence_char_cap` 2500). Not settled but an independent page supports a 🟡/🟠 claim (from any
search for it) → 🟢 by rule. Migration 15: `web_results.independent`, `claim_events.evidence_web_result_id`;
receipts link the web page. Bugs found in testing and fixed: the claim's own outlet (Reuters via Google
News) was found and called "confirms" (annotated in claim 1's history); the 🟢 upgrade was skipped when
Sonnet said no change; claims were "too new" because their DB rows were made in the backfill (age now from
the article's publish date). Tested on 6 real claims: claim 1 (USDA AI crop tool) 🟡 → 🟢 via DTN; claim 31
(Anthropic road show) Sonnet: no change ("can begin as early as" isn't the event); Apple/Siri, Meta $60B,
China 1% chips: only repeats → unchanged (correct). Measured: Haiku $0.0005/claim, Sonnet $0.0049 when
needed → ~$0.75/month. `python -m signality.claim_search --list` / `--claim N`. 112 tests. **Live** (restart
22:17 CT, migration 15 applied, clean round; searches paused until midnight because testing used today's
30). Check tomorrow's log for the first `claim search:` lines.

**Receipts folded into alerts — done (code), waiting for restart.** Nicholas's choice A (Nov 10): no
receipt is ever its own message. `delivery.attach_receipts_to_alerts` (replaces `send_live_receipts`) adds
a receipt for an alerted saga to the newest matching 🚨 by editing it (`telegram.update_delivered`:
`editMessageCaption` for photo alerts, `editMessageText` with Siggy above for text alerts; "not modified"
counts as done; if it won't fit a 1024-char caption it's skipped). Migration 16 `receipt_attachments`
records each attachment (edited 0/1); attaching does NOT count as delivery, so `claim_receipts` / the
digest still list every receipt. Re-rendering uses the stored impact note only (`impact.stored_note`, never
calls the AI). Tested for real: claim 121's receipt added to the 6:59 CT Anthropic $1.4T alert (story 854,
text message, edited OK, no ping). 116 tests.

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
| Preview "🎯 How it affects you" notes | `./.venv/bin/python -m signality.impact --preview 10` |
| Which stories web search checks next | `./.venv/bin/python -m signality.corroborate --list` |
| Search one story now (1 credit) | `./.venv/bin/python -m signality.corroborate --story 123` |
| Which open claims get searched next | `./.venv/bin/python -m signality.claim_search --list` |
| Search one claim now (1 credit) | `./.venv/bin/python -m signality.claim_search --claim 31` |

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
- **Claim de-duplication is model-judged and not perfect:** Haiku sometimes keeps same-meaning claims
  apart (or groups a loose fit). Re-run `claims.merge_existing_duplicates()` occasionally; spot-check.
- **Siggy image choice:** 🚨 alerts get red Siggy; digest + notices get the yellow logo; 🔔 silent
  messages are text-only by default to keep the chat readable (`delivery.image_on_silent`).
  Brief says "logo for normal messages" — confirm with Nicholas.
- **Unverified stories never alert** (brief rule) — step 4 must route 🟠/🔴 to the digest only.
  Real "investigate first" comes with Stage 3 search.
- **Google News links** for Reuters/AP still point to news.google.com, not the real article.
  Resolve them in Stage 2a when we need article text.
- Publishing actions (creating public repos, changing visibility) must be run by Nicholas;
  Claude's permission settings block them. Regular `git push` to the existing repo is fine.
