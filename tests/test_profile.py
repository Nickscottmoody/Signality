import sqlite3

from signality import ai, chat, db, profile, telegram_bot

CFG = {"profile": {"max_words": 150, "checkin_days": 90},
       "siggy": {"images": {"normal": "assets/siggy-logo.png"}, "image_urls": {}}}
USER = "telegram:42"


def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.migrate(conn)
    return conn


def fake_ai(monkeypatch, replies):
    """Stand-in for Sonnet: returns the given profiles in order and records the prompts."""
    prompts = []

    def ask_json(conn, cfg, **kw):
        prompts.append(kw["prompt"])
        return {"profile": replies[min(len(prompts), len(replies)) - 1]}, 0.0
    monkeypatch.setattr(ai, "ask_json", ask_json)
    return prompts


def answer_everything(conn):
    """Walk the whole interview with a mix of taps, typing, and skips. Returns the last replies."""
    chat.handle(conn, CFG, USER, "/profile")
    chat.handle_button(conn, CFG, USER, "pf:status:0")             # Student (tap)
    chat.handle(conn, CFG, USER, "Finance")                        # field (typed)
    chat.handle_button(conn, CFG, USER, "pf:job:skip")             # No job right now
    chat.handle(conn, CFG, USER, "Financial analyst at a fintech")  # goals
    chat.handle_button(conn, CFG, USER, "pf:industries:0")         # Tech
    chat.handle_button(conn, CFG, USER, "pf:industries:1")         # Finance & banking
    chat.handle_button(conn, CFG, USER, "pf:industries:0")         # untick Tech
    chat.handle_button(conn, CFG, USER, "pf:industries:done")
    chat.handle(conn, CFG, USER, "Excel, SQL")                     # skills
    chat.handle_button(conn, CFG, USER, "pf:ai_use:done")          # nothing ticked = skipped
    chat.handle(conn, CFG, USER, "Faster research")                # excites
    chat.handle(conn, CFG, USER, "Entry-level jobs shrinking")     # worries
    chat.handle(conn, CFG, USER, "Dallas, TX")                     # location
    chat.handle_button(conn, CFG, USER, "pf:areas:0")              # Career
    chat.handle_button(conn, CFG, USER, "pf:areas:done")
    return chat.handle_button(conn, CFG, USER, "pf:off_limits:skip")  # Nothing


def test_there_are_twelve_questions_with_valid_button_codes():
    assert len(profile.QUESTIONS) == 12
    state = {"step": 0, "picked": []}
    for i in range(12):
        state["step"] = i
        for row in profile._buttons(state):
            for _, data in row:
                assert len(data.encode()) <= 64


def test_full_interview_collects_answers_and_asks_for_approval(monkeypatch):
    prompts = fake_ai(monkeypatch, ["You're a finance student in Dallas, TX."])
    conn = memory_db()
    replies = answer_everything(conn)
    review = replies[-1]
    assert "Look right?" in review.title and "finance student" in review.text
    assert [label for row in review.buttons for label, _ in row] == ["✅ Save", "✏️ Change something", "🔁 Start over"]
    sent = prompts[0]
    assert "Student" in sent and "Finance & banking" in sent and "Tech" not in sent.split("industries")[1].split("\n")[0]
    assert "job and role? (skipped)" in sent and "How do you use AI today? (skipped)" in sent
    assert profile.get(conn, USER) is None   # nothing saved before approval


def test_saving_stores_the_profile_and_schedules_a_checkin(monkeypatch):
    fake_ai(monkeypatch, ["You're a finance student."])
    conn = memory_db()
    answer_everything(conn)
    [saved] = chat.handle_button(conn, CFG, USER, "pf:save")
    assert saved.title == "✅ Saved!"
    row = profile.get(conn, USER)
    assert row["summary"] == "You're a finance student." and row["next_checkin_at"] > row["created_at"]
    assert not profile.in_progress(conn, USER)


def test_change_something_rewrites_with_the_users_words(monkeypatch):
    prompts = fake_ai(monkeypatch, ["Version one.", "Version two, with fintech."])
    conn = memory_db()
    answer_everything(conn)
    assert "Type what to change" in chat.handle_button(conn, CFG, USER, "pf:change")[0].text
    [review] = chat.handle(conn, CFG, USER, "Add that I'm also looking at fintech")
    assert "Version two" in review.text
    assert "Current profile:\nVersion one." in prompts[1] and "also looking at fintech" in prompts[1]


def test_tapping_a_choice_shows_the_answer_on_that_question_then_asks_the_next():
    conn = memory_db()
    chat.handle(conn, CFG, USER, "/profile")
    shown, nxt = chat.handle_button(conn, CFG, USER, "pf:status:1")
    assert shown.replace and "→ Working" in shown.text and not shown.buttons
    assert "Question 2 of 12" in nxt.text


def test_multi_pick_redraws_ticks_in_place():
    conn = memory_db()
    chat.handle(conn, CFG, USER, "/profile")
    chat.handle_button(conn, CFG, USER, "pf:status:0")
    for typed in ("Finance", "Intern", "Analyst"):  # field, job, goals -> now on industries
        chat.handle(conn, CFG, USER, typed)
    [redraw] = chat.handle_button(conn, CFG, USER, "pf:industries:2")
    assert redraw.replace and ("✅ Consulting", "pf:industries:2") in [b for row in redraw.buttons for b in row]


def test_old_buttons_and_cancel_are_handled_safely():
    conn = memory_db()
    chat.handle(conn, CFG, USER, "/profile")
    chat.handle_button(conn, CFG, USER, "pf:status:0")
    assert "already answered" in chat.handle_button(conn, CFG, USER, "pf:status:1")[0].text
    assert "Nothing was saved" in chat.handle(conn, CFG, USER, "/cancel")[0].text
    assert "closed" in chat.handle_button(conn, CFG, USER, "pf:field:skip")[0].text
    assert "only understand commands" in chat.handle(conn, CFG, USER, "hello")[0].text


def test_ai_failure_keeps_the_answers(monkeypatch):
    def broken(*a, **k):
        raise ai.AIError("reply was not valid JSON")
    monkeypatch.setattr(ai, "ask_json", broken)
    conn = memory_db()
    replies = answer_everything(conn)
    assert "couldn't write your profile" in replies[-1].text and profile.in_progress(conn, USER)


def test_profiles_are_kept_per_user(monkeypatch):
    fake_ai(monkeypatch, ["Profile."])
    conn = memory_db()
    answer_everything(conn)
    chat.handle_button(conn, CFG, USER, "pf:save")
    assert profile.get(conn, "telegram:99") is None and profile.get(conn, "web:42") is None


def test_tap_reply_marked_replace_edits_the_tapped_message(monkeypatch):
    monkeypatch.setenv("TELEGRAM_USER_ID", "42")
    conn, calls, sent = memory_db(), [], []
    chat.handle(conn, CFG, USER, "/profile")
    tap = {"update_id": 3, "callback_query": {"id": "t", "from": {"id": 42}, "data": "pf:status:0",
           "message": {"message_id": 5, "chat": {"id": 42, "type": "private"}}}}
    telegram_bot.process_update(tap, conn, CFG, send=lambda r, c, cfg: sent.append(r),
                                call=lambda method, data: calls.append(method))
    assert calls == ["answerCallbackQuery", "sendChatAction", "editMessageText"]
    assert len(sent) == 1 and "Question 2 of 12" in sent[0].text
