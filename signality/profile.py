"""The onboarding interview (/profile) and the short personal profile it produces.

Siggy asks ~12 questions one at a time (tap buttons where possible, typing always
works too), Sonnet turns the answers into a short profile, and the user approves
or changes it before anything is saved. The profile feeds the
"🎯 How it affects you" notes.

Platform-neutral: takes typed text / button codes, returns Reply objects.
Private: stored only in the local database (data/ is gitignored), per user.
"""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import ai, db, users
from .messages import Reply

FLOW = "profile"
PREFIX = "pf"  # every button code in this flow starts with "pf:"

# kind: choice = tap one · multi = tap several, then Done · text = type it.
# Every question also accepts a typed answer, and every question can be skipped.
QUESTIONS = [
    {"key": "status", "kind": "choice", "text": "What do you do right now?",
     "options": ["Student", "Working", "Job searching", "Student + working"],
     "hint": "Or type your own answer."},
    {"key": "field", "kind": "text", "text": "What's your field of study (or the one you finished)?",
     "hint": "e.g. Finance, Data analytics, Biology", "skip": "Not in school"},
    {"key": "job", "kind": "text", "text": "What's your current job and role?",
     "hint": "e.g. Data analyst intern at a regional bank", "skip": "No job right now"},
    {"key": "goals", "kind": "text", "text": "Where do you want your career to be in 1–3 years?",
     "hint": "A sentence is plenty.", "skip": "Not sure yet"},
    {"key": "industries", "kind": "multi", "text": "Which industries are you aiming for?",
     "options": ["Tech", "Finance & banking", "Consulting", "Healthcare", "Government & policy",
                 "Media & marketing", "Education", "Retail & consumer", "Energy & manufacturing"],
     "hint": "Tap all that fit, then Done. Or type your own."},
    {"key": "skills", "kind": "text", "text": "Which tools and skills do you use or are you learning?",
     "hint": "e.g. Excel, SQL, Python, Tableau, financial modeling"},
    {"key": "ai_use", "kind": "multi", "text": "How do you use AI today?",
     "options": ["Writing", "Coding", "Research", "Data analysis", "Studying", "Job search", "Not much yet"],
     "hint": "Tap all that fit, then Done. Or type your own."},
    {"key": "excites", "kind": "text", "text": "What excites you most about AI?", "hint": "A few words is fine."},
    {"key": "worries", "kind": "text", "text": "What worries you most about AI?", "hint": "A few words is fine."},
    {"key": "location", "kind": "text", "text": "Roughly where are you?",
     "hint": "A city or region is plenty (for local job-market context), e.g. Dallas, TX or the Midwest."},
    {"key": "areas", "kind": "multi", "text": "Which areas should I explain news impact for?",
     "options": ["Career", "Money", "Daily life", "Learning"], "hint": "Tap all that fit, then Done."},
    {"key": "off_limits", "kind": "text", "text": "Anything I should never bring up or connect the news to?",
     "hint": "Type it, or tap Nothing.", "skip": "Nothing"},
]
BY_KEY = {q["key"]: q for q in QUESTIONS}
SHORT = {"status": "What you do", "field": "Field of study", "job": "Job and role", "goals": "Career goals",
         "industries": "Industries", "skills": "Tools and skills", "ai_use": "How you use AI",
         "excites": "AI excites you", "worries": "AI worries you", "location": "Location",
         "areas": "Impact areas", "off_limits": "Off-limits"}


def _shown(answer):
    return answer if isinstance(answer, str) else ", ".join(answer) if answer else "(skipped)"


# --- Saved interview progress (chat_sessions) ---------------------------------

def _load(conn, user_id):
    row = conn.execute("SELECT state FROM chat_sessions WHERE user_id = ? AND flow = ?",
                       (user_id, FLOW)).fetchone()
    return json.loads(row[0]) if row else None


def _save(conn, user_id, state):
    conn.execute("INSERT INTO chat_sessions (user_id, flow, state, updated_at) VALUES (?, ?, ?, ?) "
                 "ON CONFLICT(user_id) DO UPDATE SET flow = excluded.flow, state = excluded.state, "
                 "updated_at = excluded.updated_at",
                 (user_id, FLOW, json.dumps(state), db.utcnow()))
    conn.commit()


def _clear(conn, user_id):
    conn.execute("DELETE FROM chat_sessions WHERE user_id = ? AND flow = ?", (user_id, FLOW))
    conn.commit()


def in_progress(conn, user_key):
    return _load(conn, users.get_or_create(conn, user_key)) is not None


# --- Asking the questions ------------------------------------------------------

def _question_text(state):
    q = QUESTIONS[state["step"]]
    if state.get("mode") == "edit":
        current = _shown(state["answers"].get(q["key"]))
        return f"Editing one answer\n{q['text']}\n\nNow: {current}\n\n{q.get('hint', '')}".strip()
    return f"Question {state['step'] + 1} of {len(QUESTIONS)}\n{q['text']}\n\n{q.get('hint', '')}".strip()


def _buttons(state):
    q = QUESTIONS[state["step"]]
    key = q["key"]
    rows = []
    if q["kind"] in ("choice", "multi"):
        picked = state.get("picked", [])
        labels = [("✅ " if q["kind"] == "multi" and o in picked else "") + o for o in q["options"]]
        codes = [f"{PREFIX}:{key}:{i}" for i in range(len(q["options"]))]
        pairs = list(zip(labels, codes))
        rows = [pairs[i:i + 2] for i in range(0, len(pairs), 2)]
    last = []
    if q["kind"] == "multi":
        last.append(("Done ➡️", f"{PREFIX}:{key}:done"))
    last.append((q.get("skip", "Skip"), f"{PREFIX}:{key}:skip"))
    return rows + [last]


def _ask(state):
    return Reply(_question_text(state), buttons=_buttons(state))


def start(conn, cfg, user_key):
    """/profile: begin (or restart) the interview."""
    user_id = users.get_or_create(conn, user_key)
    state = {"step": 0, "answers": {}, "picked": [], "phase": "asking"}
    _save(conn, user_id, state)
    intro = Reply("I'll ask 12 quick questions so I can explain how news affects you. Tap a button or "
                  "type your answer. Skip anything you like, and type /cancel to stop.\n\n"
                  "Your answers stay on this computer. They're never posted anywhere.",
                  title="🎯 Let's build your profile", image="normal")
    return [intro, _ask(state)]


def cancel(conn, user_key):
    user_id = users.get_or_create(conn, user_key)
    had = _load(conn, user_id) is not None
    _clear(conn, user_id)
    return [Reply("Stopped. Nothing was saved. Type /profile to start again." if had
                  else "Nothing to cancel.")]


def _record(conn, cfg, user_id, state, answer, tapped_label=None):
    """Store one answer and move on: the next question, or the profile review."""
    q = QUESTIONS[state["step"]]
    replies = []
    if tapped_label is not None:  # show the answer on the question that was tapped
        replies.append(Reply(f"{_question_text(state)}\n\n→ {_shown(answer)}", replace=True))
    state["answers"][q["key"]] = answer
    if state.get("mode") == "edit":  # one answer changed: rewrite the saved profile to match
        change = f'Update the profile for this new answer to "{q["text"]}": {_shown(answer)}'
        return replies + _review(conn, cfg, user_id, state, change=change)
    state["step"] += 1
    state["picked"] = []
    if state["step"] < len(QUESTIONS):
        _save(conn, user_id, state)
        return replies + [_ask(state)]
    return replies + _review(conn, cfg, user_id, state)


def on_text(conn, cfg, user_key, text):
    """A typed message while the interview is open."""
    user_id = users.get_or_create(conn, user_key)
    state = _load(conn, user_id)
    if state is None:
        return None
    text = text.strip()[:400]  # a short answer; keeps prompts small
    if state["phase"] == "asking":
        q = QUESTIONS[state["step"]]
        answer = state["picked"] + [text] if q["kind"] == "multi" else text
        return _record(conn, cfg, user_id, state, answer)
    if state["phase"] == "revising":
        return _review(conn, cfg, user_id, state, change=text)
    return [Reply("Tap one of the buttons under your profile above.")]


def on_button(conn, cfg, user_key, data):
    """A tapped button whose code starts with 'pf:'."""
    user_id = users.get_or_create(conn, user_key)
    parts = data.split(":")
    # Buttons that work any time (from /myprofile, /editprofile, /deleteprofile, the check-in)
    if parts[1] == "menu":
        return edit_menu(conn, user_key) if parts[2] == "edit" else start(conn, cfg, user_key)
    if parts[1] == "edit":
        return begin_edit(conn, user_key, parts[2])
    if parts[1] == "delete":
        return delete(conn, user_key) if parts[2] == "yes" else [Reply("Kept. Nothing was erased.")]
    if parts[1] == "checkin":
        return [Reply("Great, I'll keep using it. I'll check in again in a few months. "
                      "Type /editprofile any time something changes.")]

    state = _load(conn, user_id)
    if state is None:
        return [Reply("That interview is closed. Type /profile to start a new one.")]

    if parts[1] in ("save", "change", "restart", "keep"):
        if state["phase"] not in ("review", "revising"):
            return [Reply("That button is from an older profile. Keep going with the questions above.")]
        if parts[1] == "save":
            return _store(conn, cfg, user_id, state)
        if parts[1] == "restart":
            return start(conn, cfg, user_key)
        if parts[1] == "keep":
            _clear(conn, user_id)
            return [Reply("No change. Your saved profile stays as it was.")]
        state["phase"] = "revising"
        _save(conn, user_id, state)
        return [Reply("Type what to change, in your own words.\n\n"
                      "e.g. \"Add that I'm also looking at fintech\" or \"Remove the part about my location\".")]

    if state["phase"] != "asking" or parts[1] != QUESTIONS[state["step"]]["key"]:
        return [Reply("That question's already answered. Keep going with the latest one.")]
    q, choice = QUESTIONS[state["step"]], parts[2]
    if choice == "skip":
        return _record(conn, cfg, user_id, state, None, tapped_label="skip")
    if choice == "done":
        return _record(conn, cfg, user_id, state, list(state["picked"]) or None, tapped_label="done")
    option = q["options"][int(choice)]
    if q["kind"] == "choice":
        return _record(conn, cfg, user_id, state, option, tapped_label=option)
    picked = state["picked"]  # multi: toggle the tick and redraw the buttons
    picked.remove(option) if option in picked else picked.append(option)
    _save(conn, user_id, state)
    return [Reply(_question_text(state), buttons=_buttons(state), replace=True)]


# --- Writing the profile (Sonnet) and saving it ----------------------------------

SYSTEM = """You write the private reader profile for Signality, a personal AI-news agent. \
Another model will read this profile before writing a 1-2 sentence "How it affects you" note \
on news stories, so it must capture what makes a story personally relevant to this reader.

From the interview answers, write ONE short paragraph addressed to the reader ("You're a ..."). \
Include, when answered: what they do now, field of study, job and role, 1-3 year career goals, \
target industries, tools and skills, how they use AI, what excites and worries them about AI, \
general location, and which areas (career, money, daily life, learning) they want impact explained for.

Rules:
- Use only what the answers say. Never invent, embellish, or guess at details.
- Keep the reader's meaning, in plain neutral words. No praise, no advice.
- Never infer sensitive traits (health, religion, politics, finances beyond what they said).
- Skipped questions are simply left out.
- If they named anything off-limits, end with a separate sentence: "Off-limits: ...". \
If they said nothing is off-limits, leave that sentence out.
- Stay under the word limit given."""

SCHEMA = {
    "type": "object",
    "properties": {"profile": {"type": "string"}},
    "required": ["profile"],
    "additionalProperties": False,
}


def answers_text(answers):
    lines = []
    for q in QUESTIONS:
        a = answers.get(q["key"])
        shown = ", ".join(a) if isinstance(a, list) else a
        lines.append(f"- {q['text']} {shown or '(skipped)'}")
    return "\n".join(lines)


def write_summary(conn, cfg, answers, current=None, change=None):
    """Sonnet turns the answers into the short profile. Returns the text."""
    limit = cfg["profile"]["max_words"]
    prompt = f"Word limit: {limit}\n\nInterview answers:\n{answers_text(answers)}"
    if current and change:
        prompt += (f"\n\nCurrent profile:\n{current}\n\nThe reader asked for this change: {change}\n"
                   "Rewrite the profile with that change. Follow the reader's request even if it "
                   "differs from the interview answers.")
    for _ in range(2):  # one retry if it runs long
        data, _cost = ai.ask_json(conn, cfg, task="profile_write", role="high_stakes",
                                  system=SYSTEM, prompt=prompt, schema=SCHEMA)
        summary = data["profile"].strip()
        if len(summary.split()) <= limit:
            return summary
        prompt += f"\n\nYour last version had {len(summary.split())} words. Make it shorter."
    return summary


def _review(conn, cfg, user_id, state, change=None):
    """Write (or rewrite) the profile and ask the user to approve it."""
    try:
        state["summary"] = write_summary(conn, cfg, state["answers"], state.get("summary"), change)
    except (ai.AIError, ai.BudgetExceeded) as e:
        state["phase"] = "revising" if state.get("summary") else "review"
        _save(conn, user_id, state)
        return [Reply(f"Sorry, I couldn't write your profile just now ({e}). Your answers are saved. "
                      "Type /profile to start over, or try again later.")]
    state["phase"] = "review"
    _save(conn, user_id, state)
    words = len(state["summary"].split())
    last = (("↩️ Keep my old profile", f"{PREFIX}:keep") if state.get("mode") == "edit"
            else ("🔁 Start over", f"{PREFIX}:restart"))
    return [Reply(f"{state['summary']}\n\n({words} words. Only you can see this.)",
                  title="📋 Here's your profile. Look right?",
                  buttons=[[("✅ Save", f"{PREFIX}:save")],
                           [("✏️ Change something", f"{PREFIX}:change")],
                           [last]])]


def _store(conn, cfg, user_id, state):
    now = datetime.now(timezone.utc)
    checkin = (now + timedelta(days=cfg["profile"]["checkin_days"])).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO user_profiles (user_id, answers, summary, created_at, updated_at, next_checkin_at) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET answers = excluded.answers, "
        "summary = excluded.summary, updated_at = excluded.updated_at, "
        "next_checkin_at = excluded.next_checkin_at",
        (user_id, json.dumps(state["answers"]), state["summary"], db.utcnow(), db.utcnow(), checkin),
    )
    conn.commit()
    _clear(conn, user_id)
    return [Reply("Your profile is saved on this computer only. I'll use it to add a "
                  "\"🎯 How it affects you\" note to stories that really connect to you, and I'll skip "
                  "it when they don't.\n\nType /profile any time to redo the interview.",
                  title="✅ Saved!")]


def get(conn, user_key):
    """The saved profile row for a user, or None."""
    user_id = users.get_or_create(conn, user_key)
    return conn.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()


# --- /myprofile, /editprofile, /deleteprofile -------------------------------------

def _day(iso, cfg):
    """A saved UTC time as the user's calendar day, e.g. 'Nov 9, 2026'."""
    d = datetime.fromisoformat(iso).astimezone(ZoneInfo(cfg["digest"]["timezone"]))
    return f"{d:%b} {d.day}, {d.year}"


NO_PROFILE = Reply("You don't have a profile yet. Type /profile to answer 12 quick questions.")


def show(conn, cfg, user_key):
    row = get(conn, user_key)
    if row is None:
        return [NO_PROFILE]
    return [Reply(f"{row['summary']}\n\nSaved {_day(row['updated_at'], cfg)} · next check-in {_day(row['next_checkin_at'], cfg)}"
                  "\nStored only on this computer.",
                  title="📋 Your profile",
                  buttons=[[("✏️ Edit an answer", f"{PREFIX}:menu:edit")],
                           [("🔁 Redo the interview", f"{PREFIX}:menu:redo")]])]


def edit_menu(conn, user_key):
    if get(conn, user_key) is None:
        return [NO_PROFILE]
    pairs = [(SHORT[q["key"]], f"{PREFIX}:edit:{q['key']}") for q in QUESTIONS]
    return [Reply("Which answer do you want to change?", title="✏️ Edit your profile",
                  buttons=[pairs[i:i + 2] for i in range(0, len(pairs), 2)])]


def begin_edit(conn, user_key, key):
    row = get(conn, user_key)
    if row is None:
        return [NO_PROFILE]
    if key not in BY_KEY:
        return [Reply("That button has expired. Type /editprofile to try again.")]
    state = {"step": next(i for i, q in enumerate(QUESTIONS) if q["key"] == key), "mode": "edit",
             "answers": json.loads(row["answers"]), "summary": row["summary"], "picked": [], "phase": "asking"}
    _save(conn, users.get_or_create(conn, user_key), state)
    return [_ask(state)]


def confirm_delete(conn, user_key):
    if get(conn, user_key) is None:
        return [Reply("There's no profile to erase.")]
    return [Reply("This permanently erases your profile and interview answers from this computer. "
                  "\"🎯 How it affects you\" notes stop until you do /profile again.",
                  title="🗑️ Erase your profile?",
                  buttons=[[("🗑️ Yes, erase it", f"{PREFIX}:delete:yes"), ("Keep it", f"{PREFIX}:delete:no")]])]


def delete(conn, user_key):
    user_id = users.get_or_create(conn, user_key)
    gone = conn.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,)).rowcount
    _clear(conn, user_id)
    conn.commit()
    return [Reply("Erased. Your profile and answers are gone. Type /profile any time to make a new one."
                  if gone else "There's no profile to erase.")]


# --- The check-in every few months -------------------------------------------------

def due_checkins(conn, cfg, now=None):
    """Profiles due for a "has anything changed?" message: [(user_id, user_key, Reply)].

    Only sent during the day (from the digest hour until 8pm, the user's clock).
    """
    now = now or datetime.now(timezone.utc)
    local_hour = now.astimezone(ZoneInfo(cfg["digest"]["timezone"])).hour
    if not cfg["digest"]["send_hour"] <= local_hour < 20:
        return []
    rows = conn.execute(
        "SELECT p.user_id, p.summary, u.platform, u.account_id FROM user_profiles p "
        "JOIN users u ON u.id = p.user_id WHERE p.next_checkin_at <= ?",
        (now.isoformat(timespec="seconds"),)).fetchall()
    months = round(cfg["profile"]["checkin_days"] / 30)
    return [(r["user_id"], f"{r['platform']}:{r['account_id']}",
             Reply(f"It's been about {months} months since your profile was saved. Is it still right?\n\n"
                   f"{r['summary']}",
                   title="🎯 Quick check-in", image="normal",
                   buttons=[[("👍 Still accurate", f"{PREFIX}:checkin:ok")],
                            [("✏️ Edit an answer", f"{PREFIX}:menu:edit")],
                            [("🔁 Redo the interview", f"{PREFIX}:menu:redo")]]))
            for r in rows]


def checked_in(conn, cfg, user_id, now=None):
    """The check-in was sent: schedule the next one (no nagging if it goes unanswered)."""
    now = now or datetime.now(timezone.utc)
    nxt = (now + timedelta(days=cfg["profile"]["checkin_days"])).isoformat(timespec="seconds")
    conn.execute("UPDATE user_profiles SET next_checkin_at = ? WHERE user_id = ?", (nxt, user_id))
    conn.commit()
