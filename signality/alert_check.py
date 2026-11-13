"""Sonnet's double-check before Signality sends a loud 🚨 alert.

Haiku's triage is cheap and good, but a loud alert interrupts you, and you
only get a few per day. So any story about to become an alert is reviewed
by the more careful model first. If Sonnet disagrees, the story is sent as a
silent 🔔 message instead.
"""
from . import ai, article_text, db, validity

SYSTEM = """You are the senior editor at Signality, a personal AI-news agent whose motto is \
"AI news with receipts." A cheaper model has already triaged this story and rated it important \
enough for a loud alert: a phone notification with sound. The reader gets at most a few per day, \
so each one must earn the interruption.

Decide two things, and give short, specific reasons the reader can check against the story.

1. send_as_alert: true only if BOTH are true:
   - Importance: a busy professional who follows AI would want to know about this today, not \
in tomorrow's digest. Major model releases from top labs, laws or rulings taking effect, very \
large deals, major outages or security incidents, or big shifts for jobs and the economy qualify. \
Routine funding rounds, product tweaks, earnings in line with expectations, and opinion do not.
   - Sourcing: the support is solid enough to act on. A single outlet citing unnamed sources \
can qualify only if the outlet is credible and the claim is specific; rumors and leaks do not.
   If either fails, set send_as_alert to false; the story is still delivered as a silent message.

2. validity_agrees: whether the validity label and its reason (decided by fixed rules from the \
sources) fit what the article actually says. Disagree only for a concrete reason, such as the \
article citing a primary document the rules missed, or the claims resting on a single unnamed \
source. Put your explanation in validity_note; leave it empty if you agree.

reason: one or two sentences explaining your send_as_alert decision.
Be neutral and precise. Do not restate the summary."""

SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {"type": "string"},
        "send_as_alert": {"type": "boolean"},
        "validity_note": {"type": "string"},
        "validity_agrees": {"type": "boolean"},
    },
    "required": ["reason", "send_as_alert", "validity_note", "validity_agrees"],
    "additionalProperties": False,
}


def build_prompt(t, label, article, text, text_source, update=None):
    factors = "\n".join(f"  {f}: {t[f]}/5 - {t[f + '_reason']}" for f in ("impact", "breadth", "urgency", "novelty"))
    follow_up = [] if not update else [
        f"UPDATE TO A DEVELOPING STORY: the reader already got an alert on {update['date']} about: "
        f"\"{update['headline']}\".",
        f"What this story adds, per triage: {t['whats_new'] or '(not stated)'}",
        "Send this as an alert only if it is a significant NEW development in that story (a new decision, "
        "action, or confirmed fact), not reaction, analysis, or a recap of what the reader already knows.",
        "",
    ]
    return "\n".join([
        *follow_up,
        f"Headline: {t['headline']}",
        f"Summary: {t['summary']}",
        f"Why it matters: {t['why_it_matters']}",
        f"Importance: {t['importance']}/100 (alert threshold reached)",
        f"Ratings:\n{factors}",
        f"Validity: {validity.LABELS[label['label']]} - {label['reason']}",
        f"Self-reported company claims: {'yes' if t['self_reported'] else 'no'}",
        f"Source read: {article['source_name']}",
        "",
        "Article text:" if text_source == "full" else "Article preview (full text unavailable):",
        text or "(none)",
    ])


def check(conn, cfg, story_id, update=None):
    """Ask Sonnet whether this story deserves a loud alert. Saves and returns the verdict.

    update: for a story in a saga the reader already got a 🚨 about, {"headline", "date"} of that alert.
    """
    t = conn.execute("SELECT * FROM story_triage WHERE story_id = ? AND purpose = 'live'", (story_id,)).fetchone()
    label = validity.update(conn, story_id)
    article = conn.execute(
        "SELECT a.*, s.name AS source_name FROM articles a JOIN sources s ON s.id = a.source_id WHERE a.id = ?",
        (t["article_id"],),
    ).fetchone()
    text = None
    if t["text_source"] == "full":
        text = article_text.fetch(article["url"], cfg)
    text_source = "full" if text else "snippet"
    text = text or article["snippet"]

    data, cost = ai.ask_json(
        conn, cfg, task="alert_check", role="high_stakes", story_id=story_id,
        system=SYSTEM, prompt=build_prompt(t, label, article, text, text_source, update), schema=SCHEMA,
    )
    model = cfg["models"]["high_stakes"]
    conn.execute(
        "INSERT INTO alert_checks (story_id, model, created_at, send_as_alert, reason, validity_agrees,"
        " validity_note, cost_usd) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (story_id, model, db.utcnow(), int(data["send_as_alert"]), data["reason"],
         int(data["validity_agrees"]), data["validity_note"], cost),
    )
    conn.commit()
    return {**data, "cost_usd": cost, "headline": t["headline"], "label": label["label"]}
