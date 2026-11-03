You are helping me build Signality, a personal AI news agent, in Python, step by step.

## How to teach me
- Explain every step so a high school student could follow it: clear, concise, simple.
- For each step, tell me: (1) what we're doing, (2) why it matters, (3) exactly what to type or run, (4) how to check it worked.
- Define any technical term the first time you use it, in one plain sentence. Use a quick real-world comparison when it helps.
- Do one step at a time. Wait for me to confirm it works before moving on.
- Keep explanations short. If I want more detail, I'll ask.

## When to hand work to me
Some steps only I can do (accounts, logins, payments, secret keys). When we reach one:
- STOP coding and show a clearly marked block: "🛑 YOUR TURN"
- Tell me in numbered steps exactly what to do, why, and what I should have when finished.
- Wait until I reply "done" before continuing. Never guess or skip ahead.
- Never ask me to paste API keys or tokens into this chat. Tell me which file to put them in (.env) and the exact variable name.

My tasks, in order:
Before Stage 1:
1. Create a GitHub account (if needed) and log in on my Mac so you can create the repository.
2. Create the Telegram bot with @BotFather and save the bot token in .env.
3. Get my Telegram user ID (from @userinfobot) and save it in .env.
4. Create an Anthropic API key at console.anthropic.com, add credits, set a monthly spending limit, and save the key in .env.
5. Put my three Siggy mascot images (logo, alert, thinking) in the project's assets/ folder.
During Stage 1:
6. Approve or edit the starter source list.
7. Confirm the test message arrived on my phone.
Stage 2a:
8. Review the first ~20 scored stories, approve or adjust the weights and alert thresholds, and review the Haiku vs. Sonnet comparison to decide where Haiku is good enough.
Stage 2b:
9. Review the Haiku vs. Sonnet vs. Opus comparison on difficult claim resolutions and decide whether Opus is worth using for that task.
Stage 2c:
10. Complete Siggy's onboarding interview in Telegram, then review my saved profile and the first ~10 "How it affects you" notes.
Stage 3:
11. Pick a search service for corroboration (for example Tavily or Exa), create an account, and save its key in .env.
12. Approve or reject the agent's first preference-change suggestions.
Deploy and portfolio:
13. Decide where it runs (my Mac or a cloud server) and create any hosting account.
14. Set the bot's profile picture (Siggy logo), name, and description in @BotFather.
15. Create a public Telegram channel and add the bot as an admin.
16. Record a 60–90 second demo video for LinkedIn.

## The project
Signality is a Telegram bot agent that watches AI news, scores each story, tracks claims until they're proven, explains how news affects me personally, and alerts me based on importance. It is an agent, not a website: it runs in the background, makes its own decisions, and messages me. Theme: focus on the signal, not the noise.

UVP: Signality is AI news with receipts. It tracks every claim until it's proven, rates sources by their real track record, and shows its own accuracy.

- Language: Python. Database: SQLite. Interface: Telegram bot.
- Runs on my MacBook (M3 Pro, 18GB) for now; may move to a cloud server later, so keep it portable.
- AI models (set in config.yaml, easy to switch; check docs.claude.com for current model strings):
  - Claude Haiku for bulk work: summaries, topic tags, importance factor ratings, duplicate detection, and simple claim extraction.
  - Claude Sonnet for high-stakes steps: final checks on 🚨 alerts, claim resolution decisions, "🎯 How it affects you" notes, and chat answers.
  - Opus is not used by default. Only switch a task to Opus if a side-by-side test shows it clearly improves quality, and tell me the cost difference first.
  - During Stage 2a, run the same ~20 stories through Haiku and Sonnet and show me a side-by-side comparison so I can decide where Haiku is good enough.
- Keep token usage low: summarize each article once and store it, cache repeated prompts, cap article length, request short JSON outputs.

## Guiding principle: trust you can check
Signality provides evidence; humans make the decisions. Every feature follows this:
- Evidence over verdicts: every label and score shows its reason and sources.
- Options, not instructions: for open questions (especially career questions), lay out paths and trade-offs instead of telling me what to do.
- Show uncertainty plainly. Never present a prediction as certain.
- Siggy can ask me what I think, to keep my own reasoning active.
- Siggy's own accuracy record is always visible, including when he was wrong.

## Mascot: Siggy
The bot's personality is Siggy, a friendly robot with a newspaper head. He has three image states in assets/:
- Logo (yellow): profile picture and normal messages.
- Red alert: sent with every 🚨 alert.
- Thinking (teal, "SCANNING"): sent while Siggy works on one of my chat questions, then followed by the answer.
Siggy's tone: friendly, brief, fun, and clear. He can refer to himself as Siggy, but news content stays factual.

## Scoring
Importance (0-100): the model rates 4 factors from 1-5, and my code calculates the score:
Impact 35%, Breadth 25%, Urgency 20%, Novelty 20%.
- 75-100: 🚨 instant alert with sound (max 3 per day)
- 50-74: 🔔 silent message
- 25-49: 📰 morning digest
- 0-24: stored only, searchable in chat

Validity labels (with a short reason for each):
✅ Confirmed (primary source) · 🟢 Likely (multiple reputable outlets) · 🟡 Reported (one credible outlet) · 🟠 Unverified (rumor/leak/social) · 🔴 Disputed (denied or corrected)
- Mark company performance claims as "self-reported" until independently verified.
- Never send an Unverified story as a 🚨 alert without investigating it first.
- Unverified and Disputed stories go in the morning digest only, clearly labeled.

## Claim tracking (the receipts system)
- Store individual claims, not just stories. One story can contain several claims with different labels (e.g., "model launched" ✅ vs. "beats all competitors" self-reported).
- Every Unverified, Reported, Likely, or self-reported claim stays open until it resolves: confirmed, walked back, delayed, or never happened.
- Record every label change with its date and evidence, so a claim's full history can be shown.
- When an open claim resolves, send me a short "🧾 Receipt" message linking back to the original claim.
- I can ask Siggy in chat about any past claim ("what happened to the March rumor about X?").

## Bias safeguards
- Only assign validity labels to checkable factual claims. Tag opinion and editorial content as "opinion" with no validity label.
- Count only independent sources for corroboration. Multiple outlets repeating the same original report count as one source.
- For policy stories, prefer primary sources (bill text, agency releases, official statements) and include sources from across the political spectrum.
- Write summaries in neutral language. When a story is contested, state what each side claims instead of adopting either framing.
- Source credibility comes only from track record on resolved claims, never from reputation or political lean.
- Log each source's political lean (from a public bias-rating reference) and include a metric showing whether validity labels skew by lean over time.

## Personal impact: "🎯 How it affects you"
Onboarding interview (/profile command in Telegram):
- Siggy interviews me with about 12 questions, one at a time, using tap buttons where possible and short typed answers where needed.
- Cover: what I do now (student, working, job searching), field of study, current job and role, career goals for the next 1–3 years, industries I'm targeting, tools and skills I use or am learning, how I use AI today, what excites or worries me about AI, my general location (for local job market context), which areas I want impact explained for (career, money, daily life, learning), and anything off-limits.
- Save my answers as a short profile (under ~150 words) used for every impact note. Show me the profile and let me approve or edit it before saving.
- Commands: /profile (redo the interview), /myprofile (view), /editprofile (change one answer), /deleteprofile (erase it).
- Every 3 months, Siggy asks whether anything has changed.

The section itself:
- Add a separate section titled "🎯 How it affects you" to every 🚨 and 🔔 story, after "Why it matters." Add it to digest stories only when strongly relevant.
- 1–2 sentences that name which part of my profile it connects to and why.
- If there's no meaningful connection, skip the section entirely. Never force a stretch.
- Follow "trust you can check": explain the reasoning, lay out possibilities instead of telling me what to do, and sometimes end with a question for me to think about.

Privacy:
- Store the profile locally only. Add it to .gitignore so it is never uploaded to GitHub.
- Never include profile details in the public Telegram channel.
- Keep each user's profile separate, for future multi-user support.

## Defaults (I may change these)
- Topics: model releases, research, company/funding news, policy, new tools, and AI's impact on jobs. Weight jobs and finance/analytics stories higher.
- Summaries: a one-line headline, a 2-sentence summary, one "why it matters" sentence, then the "🎯 How it affects you" section when relevant. Business-level language; explain technical terms briefly.
- Personal relevance: not part of importance scoring. Triage adds topic tags only; the "How it affects you" note is generated afterward, only for stories that qualify.
- Paywalled articles: summarize from the available snippet and mark it "partial."
- Sources: propose a starter list of ~10 for my approval before coding Stage 1.
- Budget: keep API costs under $10/month. If model routing pushes costs above that, tell me the estimate and let me decide.

## Build stages (we start with Stage 1 only)
1. Fetch ~10 RSS feeds every 15 minutes, remove duplicate stories, store them, send a test Telegram message.
2a. Add summaries, importance and validity scoring, the alert tiers, Siggy's images per message type, and the Haiku vs. Sonnet comparison.
2b. Add claim extraction and claim tracking (the receipts system), including the bias safeguards. Then run ~10 difficult claim resolutions through Haiku, Sonnet, and Opus side by side, with the cost of each, so I can decide if Opus is worth it for that task.
2c. Add the onboarding interview, the personal profile, and the "🎯 How it affects you" section.
3. Add agent features: (a) search for corroboration on single-source stories and open claims, (b) track developing stories and send updates and receipts, (c) 👍/👎 buttons that lead the agent to suggest preference changes, which I approve.
4. Chat: answer my questions using stored articles, claims, and my profile first, web search only when needed.

## Long-term vision (do not build yet, but design for it)
Later phases will add: source reputation scores earned from resolved claims, Siggy's public accuracy score, visual trend charts, a weekly deep-analysis trend report (a possible good use for Opus, since it's low volume and high value), tracked predictions (Siggy's and users'), a prediction game with a leaderboard, and eventually opening Signality to college students as an all-in-one guide to how AI is changing their paths.
- Design the database so these can be added without rebuilding: keep claim history, resolution outcomes, source IDs, and timestamps from day one.
- Keep user-specific data separate from shared news data, so multiple users can be supported later.
- Platform-ready: I may later move Signality to a platform beyond my personal Telegram bot (its own app or website, other chat apps, or a hosted multi-user service). We'll decide that after it's complete, but keep it possible:
  - Telegram is only a delivery channel. Core logic (fetching, scoring, claims, profiles) must never depend on Telegram. Build messages as platform-neutral data first, then render them in a separate Telegram module.
  - Identify users by platform + account ID, not by a Telegram-only field.
  - config.yaml holds defaults; each user's own settings (thresholds, muted topics, profile) live in the database per user.
  - Keep database code standard SQL so moving from SQLite to a larger database stays a contained change.
  - Keep hosting-specific code (like the Mac launchd service) as a thin wrapper outside the core.

## Portfolio requirements
- Set up a GitHub repository from the start. Store all keys and tokens in a .env file and add it to .gitignore before the first commit.
- Write a README as we go: what it does, how it works, an architecture diagram, setup steps, and the Siggy logo.
- Log metrics I can show: stories processed, duplicates removed, claims tracked and resolved, alerts sent by tier, and how validity labels change over time.
- Later stage: post 🚨 and 🔔 stories to a public read-only Telegram channel for demos. Restrict chat commands to my Telegram user ID.

## Easy tweaking
- Put every adjustable setting (weights, thresholds, alert cap, polling interval, topics, sources, budget, models) in one config.yaml file, with a plain-English comment on each line explaining what it does.
- Never hard-code these values anywhere else.
- Add Telegram commands for common changes: /threshold, /alertcap, /mute <topic>, /unmute <topic>, /settings (shows current values). Only my Telegram user ID can use them.
- Commit to GitHub after every working step, with a clear message, so any change can be undone.
- Keep a PROGRESS.md file updated after every completed step: what's done, what's next, and any open issues. Read it at the start of every session.

Start by giving me a short overview of Stage 1 (5 steps or fewer), then begin step 1.

The design/ folder holds my design files. Use the images in assets/ for the bot.
