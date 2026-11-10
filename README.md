<img src="assets/siggy-logo.png" alt="Siggy, the Signality mascot" width="140" align="right">

# Signality

**AI news with receipts.** Signality is a personal AI news agent that runs in the
background, watches AI news, scores every story for importance, tracks each claim
until it is proven or walked back, explains how a story affects you personally, and
messages you on Telegram. It is an agent, not a website: it decides what is worth
your attention and comes to you.

*Focus on the signal, not the noise.*

---

## What makes it different

Most news tools summarize. Signality keeps a record.

- **Every claim is tracked.** A single story can hold several claims — "the model
  launched" (confirmed) and "it beats every competitor" (self-reported). Each one stays
  open until it resolves, and you get a 🧾 **Receipt** when it does.
- **Every label shows its reason.** Scores and validity labels come with the evidence
  behind them, never a bare verdict.
- **Sources earn trust by track record**, measured on resolved claims — not by reputation.
- **Signality shows its own accuracy**, including when it was wrong.

## How it works

```
   17 news sources          + Tavily web search for
         │  every 15 minutes    single-source stories
         ▼
   ┌───────────┐   non-AI stories + duplicates removed (free, no AI)
   │  Fetcher  │──────────────────────────┐
   └───────────┘                          ▼
                                   ┌─────────────┐
   Claude Haiku  ──  summaries,    │   SQLite    │  articles · claims
   (bulk work)       topic tags,   │  database   │  claim history · sources
                     1-5 factor    └─────────────┘  metrics
                     ratings             │
                                         ▼
   Claude Sonnet ──  alert checks,  ┌───────────┐
   (high stakes)     claim          │  Scoring  │  Impact 35% · Breadth 25%
                     resolution,    │  & triage │  Urgency 20% · Novelty 20%
                     impact notes   └───────────┘
                                         │
                   ┌─────────────────────┼─────────────────────┐
                   ▼                     ▼                     ▼
             🚨 65-100            🔔 50-64              📰 25-49
             alert, if Sonnet     silent message        morning digest
             agrees (max 5/day)                                (0-24: stored only)
                   │                     │                     │
                   └─────────────────────┼─────────────────────┘
                                         ▼
                                  Telegram  ·  Siggy
```

## Duplicate handling

Signality separates two kinds of duplicates, because they mean different things:

- **Exact repeats** (the same article seen again on the next check) are skipped.
- **Same event, different outlet** is *kept and grouped* under one story. Independent
  coverage is evidence: it's how a claim moves from 🟡 Reported to 🟢 Likely.

Stage 1 groups near-identical headlines for free. Stage 2a adds Claude Haiku to catch
the same event written in very different words.

## Sources

Seventeen feeds, chosen for credibility and freshness and tested before use. Reputation
is only the starting point: Signality grades every source by how its claims hold up.

| Kind | Sources |
|---|---|
| **Primary** (what the organization itself said) | OpenAI · Google DeepMind · Google AI · NVIDIA · Hugging Face · Federal Register |
| **Top-tier news** (fact-checking + correction policies) | Reuters · AP · Wall Street Journal · Bloomberg · Financial Times |
| **AI specialists** | The Information · MIT Technology Review · Ars Technica · TechCrunch |
| **Viewpoint balance** (policy) | Reason · Washington Examiner |

Paywalled sources contribute their headline and preview, and those summaries are marked
*partial*. Broad feeds pass through a free keyword filter so only AI stories reach the
paid AI steps.

## Bias safeguards

- Validity labels go only on checkable facts; opinion pieces get none.
- Only **independent** sources count: an outlet repeating another outlet's report counts once.
- Credibility comes only from **track record on resolved claims**, never from reputation or lean.
- Each news source's political lean is recorded from [AllSides Media Bias Ratings](https://www.allsides.com/media-bias)
  for one purpose: **auditing Signality itself**. `python -m signality.bias` shows whether stories
  from different leans get systematically different labels, week by week.

Current mix (AllSides, Nov 2026): 7 Center, 1 Lean Left (AP), 1 Lean Right (Washington Examiner),
2 unrated, plus 6 primary sources (the organizations themselves).

## Importance score

The model rates four factors from 1 to 5; the code does the math.

| Factor | Weight | Means |
|---|---|---|
| Impact | 35% | how big the consequences are |
| Breadth | 25% | how many people or companies it touches |
| Urgency | 20% | how time-sensitive it is |
| Novelty | 20% | how new or surprising it is |

## Validity labels

| | Label | Earned by |
|---|---|---|
| ✅ | Confirmed | a primary source |
| 🟢 | Likely | multiple independent reputable outlets |
| 🟡 | Reported | one credible outlet |
| 🟠 | Unverified | rumor, leak, or social post |
| 🔴 | Disputed | denied or corrected |

Company performance claims are marked **self-reported** until independently verified.
Unverified and Disputed stories never go out as alerts — digest only, clearly labeled.

### Corroboration search

When only one outlet has an important story, Signality runs **one web search**
([Tavily](https://tavily.com), free plan) looking for other outlets. Claude Haiku judges each
page it finds (own reporting, a copy of someone else's report, the organization's own page,
an on-record confirmation, a denial, or a different event), then fixed rules in code
decide the label:

- Aggregators (Yahoo, MSN…), sister sites (Bloomberg Law for Bloomberg), and social media never count.
- "The organization's own page" must really be its own site, not a news site quoting its blog.
- A site that carries both its own reporting and copies of others' gets no credit.

The pages that changed a label are linked in the message, and the reason says which outlets
web search found. Alert-level stories are searched **before** the 🚨 decision; others wait a
couple of hours so the regular feeds can find other outlets for free. Hard limits per day and
per month keep it inside the free plan.

**Open claims get searched too.** Instead of waiting for a feed to report the outcome, Siggy
searches for each open claim every few days (less often for plans not yet due). Haiku sorts
each page (confirms, contradicts, walked back, delayed, or just repeats it); if a page may settle
the claim, Sonnet makes the final call after reading the page itself. The claim's own outlet,
pages from before the claim was made, and aggregators never count, and the 🧾 receipt links
the page that settled it.

## What arrives on your phone

| | When | Looks like |
|---|---|---|
| 🚨 **Alert** | Importance 65+, Sonnet agrees it's worth interrupting you, max 5/day | Red-alert Siggy, with sound |
| 🔔 **Silent** | Importance 50–64 (optional; off by default, so these lead the digest) | Text message, no sound |
| 📰 **Digest** | Importance 25–64, alert-level stories Sonnet declined, plus anything unconfirmed | One message each morning at 8am |
| — | Below 25 | Stored and searchable, never sent |
| 🧾 **Receipt** | A tracked claim resolves | Never its own message: listed in the next digest, and added to the original 🚨 alert by editing it (no new notification) |

Every story shows its validity label **and the reason**, a self-reported flag where it applies,
whether it was summarized from a preview only, the four factor ratings, and links to each outlet.
🟠 Unverified and 🔴 Disputed stories never ping you; they wait in the digest's clearly labeled
"Unconfirmed" section.

Messages are built in a platform-neutral form first and rendered for Telegram last, so other
platforms can be added without changing the agent.

## Talking to Siggy

Siggy also listens. Send `/help` in Telegram to see his commands. Commands are decided in
`signality/chat.py` (platform-neutral, users identified as `platform:account id`) and
`signality/telegram_bot.py` only translates to and from Telegram. Only the owner's Telegram
account is answered, and only in a private chat, so personal details never reach a group or channel.

`/profile` runs a 12-question onboarding interview (tap buttons where possible). Sonnet condenses the
answers into a short profile (under 150 words) that the user approves or edits before it's saved. It
lives only in the local database and powers the "🎯 How it affects you" notes.
`/myprofile`, `/editprofile` and `/deleteprofile` manage it, and Siggy checks in every 3 months.

## 🎯 How it affects you

After "Why it matters", 🚨 alerts get a 1-2 sentence note on how the story connects to the reader's
profile, and the few digest stories that are strongly relevant get one too. The bar is deliberately high:
no note is written when the only link is generic ("the market fell, so tech hiring might slow"), every
decision to write or skip is stored with its reason, and notes lay out possibilities rather than telling
the reader what to do. Rumors are never personalized, and notes never appear in a public channel.

## Meet Siggy

| | |
|---|---|
| <img src="assets/siggy-logo.png" width="90"> | Normal messages and the bot's profile picture |
| <img src="assets/siggy-alert.png" width="90"> | Sent with every 🚨 alert |
| <img src="assets/siggy-thinking.png" width="90"> | Shown while Siggy works on a question you asked |

## Setup

```bash
git clone <this-repo>
cd Signality
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env     # then fill in your own keys
```

Fetch the news once (creates `data/signality.db` on first run):

```bash
./.venv/bin/python -m signality.fetcher
```

Run the always-on agent (checks every 15 minutes; Ctrl+C to stop):

```bash
./.venv/bin/python -m signality.agent
```

Or, on a Mac, install it as a background service that starts at login and restarts if it
crashes (undo with `scripts/uninstall_mac_service.sh`):

```bash
./scripts/install_mac_service.sh
```

Check health and AI spending:

```bash
./.venv/bin/python -m signality.status
```

Send a test message to your Telegram (needs `TELEGRAM_BOT_TOKEN` and `TELEGRAM_USER_ID` in `.env`):

```bash
./.venv/bin/python -m signality.telegram
```

Run the tests:

```bash
./.venv/bin/python -m pytest -q
```

Secrets go in `.env`, which is listed in `.gitignore` and never committed.
Every adjustable setting — weights, thresholds, alert cap, polling interval, topics,
sources, budget, models — lives in `config.yaml` with a comment explaining each line.

## Tech

Python · SQLite · Telegram Bot API · Claude (Haiku for bulk work, Sonnet for high-stakes steps) · Tavily web search

## Status

Stages 1, 2a, 2b complete and live ✅ (fetching, scoring, alerts, digest, claim tracking with receipts,
bias audit). Stage 2c built: two-way chat, the onboarding interview and profile commands, and personal impact notes.
Stage 3 in progress: corroboration search on single-source stories and open claims built.
See [PROGRESS.md](PROGRESS.md).

| Stage | Scope |
|---|---|
| 1 | Fetch feeds, remove duplicates, store, test Telegram message |
| 2a | Summaries, importance + validity scoring, alert tiers |
| 2b | Claim extraction and tracking (the receipts system) |
| 2c | Onboarding interview and "🎯 How it affects you" notes |
| 3 | Agent features: corroboration search, developing-story updates, learned preferences |
| 4 | Chat over stored articles, claims, and profile |

## Privacy

The personal profile and the article database stay on the local machine. Neither is
committed to GitHub, and no profile detail is ever posted to the public demo channel.
