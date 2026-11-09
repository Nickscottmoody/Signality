"""Claims: the receipts system.

A story can hold several claims with different support, for example:
  "OpenAI launched GPT-7"             -> ✅ confirmed (OpenAI announced it)
  "GPT-7 beats every competitor"      -> 🏷️ self-reported (OpenAI's own claim)
  "It launches in Europe next month"  -> open until it happens (or doesn't)

Labels come from rules in code, like story labels. Any claim that isn't settled
stays OPEN until it resolves: confirmed, walked back, delayed, or never happened.
Every change is recorded in claim_events with its date and the evidence.
"""
from datetime import datetime, timedelta, timezone

from . import db
from .dedup import key_words

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
    "duplicate": "Same as another claim",
}

# Attribution words appear in many claims ("according to the New York Times...")
# and say nothing about the subject, so they don't count toward a match.
ATTRIBUTION = {"according", "reports", "reported", "report", "says", "said", "york", "times", "bloomberg",
               "reuters", "information", "journal", "street", "wall", "financial", "unnamed", "sources",
               "people", "familiar", "matter", "memo", "told"}


def subject_words(text, claimant=""):
    """The words that say what a claim is ABOUT (not who reported it)."""
    return key_words(text) - ATTRIBUTION - key_words(claimant or "")


def related_claims(conn, text, window_days=120, limit=12):
    """Claims already recorded on the same subject (shares 2+ subject words), best match first."""
    since = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat(timespec="seconds")
    words = subject_words(text)
    scored = []
    for c in conn.execute("SELECT * FROM claims WHERE status != 'duplicate' AND created_at >= ?", (since,)):
        overlap = len(words & subject_words(c["text"], c["claimant"]))
        if overlap >= 2:
            scored.append((overlap, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:limit]]

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
        return "reported", "open", f"Relayed reporting ({who}); counts as one source."
    return "reported", "open", "One outlet so far."


def _number(raw):
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    return int(digits) if digits else None


def record(conn, story_id, article_id, extracted, independent_outlets, read_from="", known_ids=()):
    """Save newly extracted claims with their starting label and a 'created' history row.

    A claim the model marked as the same as one Signality already tracks (same_as, one of
    known_ids) is NOT saved again: the existing claim gets an 'also reported' note instead.
    Whether the new article changes that claim's status is decided by resolution.py.
    """
    now = db.utcnow()
    saved = []
    for c in extracted:
        text = c["text"].strip()
        if not text:
            continue
        same = _number(c.get("same_as", ""))
        if same in set(known_ids):
            existing = conn.execute("SELECT * FROM claims WHERE id = ?", (same,)).fetchone()
            conn.execute(
                "INSERT INTO claim_events (claim_id, at, event, label, status, reason, evidence_article_id, decided_by)"
                " VALUES (?, ?, 'repeated', ?, ?, ?, ?, 'haiku')",
                (same, now, existing["label"], existing["status"], f"Also reported in {read_from or 'another outlet'}.",
                 article_id),
            )
            saved.append({"id": same, "text": existing["text"], "label": existing["label"], "status": "repeat",
                          "reason": f"Same as claim {same}; noted as also reported.", "kind": existing["kind"],
                          "due_date": existing["due_date"]})
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


# --- One-time cleanup of copies recorded before same_as existed -------------------------

GROUP_SYSTEM = """You help Signality keep one record per claim. You get a list of claims about one news \
subject. Group the claims that state the SAME checkable thing, even if worded differently (for \
example "Huang admitted an affair" and "Jensen Huang acknowledged having an affair"). Claims that are \
merely related but assert different things stay separate (for example "the board opened an \
investigation" vs. "the woman is a suspected spy"). Only return groups with two or more claims."""

GROUP_SCHEMA = {
    "type": "object",
    "properties": {"groups": {"type": "array", "items": {
        "type": "object",
        "properties": {"claim_ids": {"type": "array", "items": {"type": "string"}}, "reason": {"type": "string"}},
        "required": ["claim_ids", "reason"], "additionalProperties": False}}},
    "required": ["groups"], "additionalProperties": False,
}

RANK = {"confirmed": 5, "disputed": 4, "likely": 3, "reported": 2, "self_reported": 2, "unverified": 1}


def merge_group(conn, ids, decided_by="haiku"):
    """Keep the earliest claim; it takes the strongest evidence in the group; others become duplicates."""
    members = conn.execute(
        f"SELECT * FROM claims WHERE id IN ({','.join('?' * len(ids))}) ORDER BY created_at, id", ids).fetchall()
    keeper, copies = members[0], members[1:]
    best = max(members, key=lambda m: (m["status"] not in ("open", "not_tracked"), RANK.get(m["label"], 0)))
    status = best["status"] if best["status"] not in ("not_tracked",) else keeper["status"]
    if all(m["status"] == "not_tracked" for m in members):
        status = "not_tracked"
    elif status == "not_tracked":
        status = "open"
    now = db.utcnow()
    for m in copies:
        conn.execute("UPDATE claims SET status = 'duplicate', duplicate_of = ?, updated_at = ? WHERE id = ?",
                     (keeper["id"], now, m["id"]))
        conn.execute(
            "INSERT INTO claim_events (claim_id, at, event, label, status, reason, evidence_article_id, decided_by)"
            " VALUES (?, ?, 'merged', ?, 'duplicate', ?, ?, ?)",
            (m["id"], now, m["label"], f"Same claim as #{keeper['id']}; tracked there.", m["article_id"], decided_by))
    if (best["label"], status) != (keeper["label"], keeper["status"]):
        reason = (f"Merged with the same claim from another story (#{best['id']}): "
                  f"{LABELS[best['label']]}, {STATUSES.get(best['status'], best['status'])}.")
        conn.execute("UPDATE claims SET label = ?, status = ?, updated_at = ?,"
                     " resolved_at = CASE WHEN ? IN ('open', 'not_tracked') THEN resolved_at ELSE COALESCE(resolved_at, ?) END"
                     " WHERE id = ?", (best["label"], status, now, status, now, keeper["id"]))
        conn.execute(
            "INSERT INTO claim_events (claim_id, at, event, label, status, reason, evidence_article_id, decided_by)"
            " VALUES (?, ?, 'merged', ?, ?, ?, ?, ?)",
            (keeper["id"], now, best["label"], status, reason, best["article_id"], decided_by))
    conn.commit()
    return keeper["id"], [m["id"] for m in copies]


def merge_existing_duplicates(conn, cfg):
    """Find and merge copies among recorded claims. Returns [(kept id, [copy ids])]."""
    from . import ai
    from .dedup import related
    rows = conn.execute("SELECT * FROM claims WHERE status != 'duplicate' ORDER BY id").fetchall()
    words = {r["id"]: subject_words(r["text"], r["claimant"]) for r in rows}
    clusters = []
    for r in rows:  # group claims on the same subject (shares 2+ subject words with any member)
        home = next((cl for cl in clusters if any(related(words[r["id"]], words[o]) for o in cl)), None)
        (home.append(r["id"]) if home else clusters.append([r["id"]]))
    merged = []
    for cl in (c for c in clusters if len(c) > 1):
        listing = "\n".join(f"Claim {i}: {next(r['text'] for r in rows if r['id'] == i)}" for i in cl)
        data, _ = ai.ask_json(conn, cfg, task="claim_dedup", role="bulk", system=GROUP_SYSTEM,
                              prompt=listing, schema=GROUP_SCHEMA)
        for g in data["groups"]:
            ids = sorted({n for n in (_number(x) for x in g["claim_ids"]) if n in cl})
            ids = [i for i in ids if conn.execute("SELECT status FROM claims WHERE id = ?", (i,)).fetchone()[0] != "duplicate"]
            if len(ids) >= 2:
                merged.append(merge_group(conn, ids))
    return merged
