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
   16 news sources
         │  every 15 minutes
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
             🚨 75-100            🔔 50-74              📰 25-49
             instant alert        silent message        morning digest
             (max 3/day)                                (0-24: stored only)
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

Sixteen feeds, chosen for credibility and freshness and tested before use. Reputation
is only the starting point: Signality grades every source by how its claims hold up.

| Kind | Sources |
|---|---|
| **Primary** (what the organization itself said) | OpenAI · Google DeepMind · Google AI · NVIDIA · Hugging Face · Federal Register |
| **Top-tier news** (fact-checking + correction policies) | Reuters · AP · Wall Street Journal · Bloomberg · Financial Times |
| **AI specialists** | The Information · MIT Technology Review · Ars Technica · TechCrunch |
| **Viewpoint balance** (policy) | Reason |

Paywalled sources contribute their headline and preview, and those summaries are marked
*partial*. Broad feeds pass through a free keyword filter so only AI stories reach the
paid AI steps.

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

Run the tests:

```bash
./.venv/bin/python -m pytest -q
```

Secrets go in `.env`, which is listed in `.gitignore` and never committed.
Every adjustable setting — weights, thresholds, alert cap, polling interval, topics,
sources, budget, models — lives in `config.yaml` with a comment explaining each line.

## Tech

Python · SQLite · Telegram Bot API · Claude (Haiku for bulk work, Sonnet for high-stakes steps)

## Status

Stage 1 of 4 — in progress. See [PROGRESS.md](PROGRESS.md).

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
