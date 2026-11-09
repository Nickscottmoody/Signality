"""Claims: the receipts system.

A story can hold several claims with different support, for example:
  "OpenAI launched GPT-7"             -> ✅ confirmed (OpenAI announced it)
  "GPT-7 beats every competitor"      -> 🏷️ self-reported (OpenAI's own claim)
  "It launches in Europe next month"  -> open until it happens (or doesn't)

Labels come from rules in code, like story labels. Any claim that isn't settled
stays OPEN until it resolves: confirmed, walked back, delayed, or never happened.
Every change is recorded in claim_events with its date and the evidence.
"""
from . import db

LABELS = {
    "confirmed": "✅ Confirmed",
    "likely": "🟢 Likely",
    "reported": "🟡 Reported",
    "unverified": "🟠 Unverified",
    "disputed": "🔴 Disputed",
    "self_reported": "🏷️ Self-reported",
}

STATUSES = {
    "open": "Open",
    "not_tracked": "Not in doubt",
    "confirmed": "✅ Confirmed",
    "walked_back": "↩️ Walked back",
    "delayed": "⏳ Delayed",
    "never_happened": "❌ Never happened",
}

BASES = ["official_source", "on_record_reporting", "anonymous_sources", "rumor_leak_social",
         "repeats_other_outlet", "denial_or_correction"]


def initial_label(claim, independent_outlets, read_from=""):
    """(label, status, reason) for a newly extracted claim.

    claim: dict with kind, basis, self_reported, claimant, in_doubt
    independent_outlets: how many independent outlets have reported the story
    read_from: the outlet the claim was read in (so an outlet citing itself isn't a "relay")

    Only claims that are genuinely in doubt stay open. Routine facts nobody disputes
    (market moves, what someone said in public) get a label but aren't tracked.
    """
    who = claim.get("claimant") or "the source"
    label, status, reason = _label(claim, independent_outlets, read_from, who)
    if status == "open" and not claim.get("in_doubt", True) and not claim["self_reported"] \
            and claim["kind"] != "future":
        return label, "not_tracked", reason + " Not in doubt, so not tracked."
    return label, status, reason


def _label(claim, independent_outlets, read_from, who):
    cites_itself = bool(read_from) and (who.lower() in read_from.lower() or read_from.lower() in who.lower())
    if claim["self_reported"]:
        return "self_reported", "open", f"{who}'s own claim about itself; not independently verified."
    if claim["basis"] == "denial_or_correction":
        return "disputed", "open", f"Denied or corrected ({who})."
    if claim["basis"] == "official_source":
        if claim["kind"] == "future":
            return "confirmed", "open", f"Officially announced by {who}; open until it happens."
        return "confirmed", "confirmed", f"Stated by {who} itself or in an official document."
    if independent_outlets >= 2:
        return "likely", "open", f"Reported independently by {independent_outlets} outlets."
    if claim["basis"] == "rumor_leak_social":
        return "unverified", "open", "Based on a rumor, leak, or social-media post."
    if claim["basis"] == "anonymous_sources":
        return "reported", "open", "One outlet so far, citing unnamed sources."
    if claim["basis"] == "repeats_other_outlet" and not cites_itself:
        return "reported", "open", f"Relayed from {who}'s report; counts as one source."
    return "reported", "open", "One outlet so far."


def record(conn, story_id, article_id, extracted, independent_outlets, read_from=""):
    """Save newly extracted claims with their starting label and a 'created' history row."""
    now = db.utcnow()
    saved = []
    for c in extracted:
        text = c["text"].strip()
        if not text:
            continue
        label, status, reason = initial_label(c, independent_outlets, read_from)
        claim_id = conn.execute(
            """
            INSERT INTO claims (story_id, article_id, text, kind, basis, claimant, due_date, self_reported,
                                label, status, created_at, updated_at, resolved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (story_id, article_id, text, c["kind"], c["basis"], c.get("claimant") or None,
             c.get("due_date") or None, int(c["self_reported"]), label, status, now, now,
             now if status not in ("open", "not_tracked") else None),
        ).lastrowid
        conn.execute(
            "INSERT INTO claim_events (claim_id, at, event, label, status, reason, evidence_article_id, decided_by)"
            " VALUES (?, ?, 'created', ?, ?, ?, ?, 'rules')",
            (claim_id, now, label, status, reason, article_id),
        )
        saved.append({"id": claim_id, "text": text, "label": label, "status": status, "reason": reason,
                      "kind": c["kind"], "due_date": c.get("due_date") or None})
    conn.commit()
    return saved


def history(conn, claim_id):
    """Every recorded change to a claim, oldest first."""
    return conn.execute("SELECT * FROM claim_events WHERE claim_id = ? ORDER BY id", (claim_id,)).fetchall()
