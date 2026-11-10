import json
import sqlite3

from signality import chat, db, telegram, telegram_bot

CFG = {"siggy": {"images": {"normal": "assets/siggy-logo.png"}, "image_urls": {}}}
OWNER = "12345"


def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.migrate(conn)
    return conn


def test_help_lists_working_and_coming_commands():
    [reply] = chat.handle(None, CFG, "telegram:1", "/help")
    assert "/start" in reply.text and "/help" in reply.text
    assert "Coming soon:" in reply.text and "/profile" in reply.text.split("Coming soon:")[1]


def test_command_menu_shows_only_working_commands():
    names = [name for name, _ in chat.menu()]
    assert "help" in names and "profile" not in names


def test_commands_ignore_case_bot_name_and_extra_words():
    [reply] = chat.handle(None, CFG, "telegram:1", "/Help@Signalitynewsbot please")
    assert reply.title == "🤖 What I can do"


def test_unknown_commands_and_plain_text_get_a_friendly_pointer_to_help():
    assert "/help" in chat.handle(None, CFG, "telegram:1", "/nope")[0].text
    assert "/help" in chat.handle(None, CFG, "telegram:1", "hello?")[0].text
    assert "coming soon" in chat.handle(None, CFG, "telegram:1", "/profile")[0].text


def test_button_codes_must_fit_telegram_limit():
    assert json.loads(telegram.keyboard([[("Yes", "profile:yes")]]))["inline_keyboard"][0][0]["text"] == "Yes"
    try:
        telegram.keyboard([[("Too long", "x" * 65)]])
        assert False, "should refuse"
    except ValueError:
        pass


def _message(sender, text, chat_type="private"):
    return {"update_id": 1, "message": {"message_id": 7, "from": {"id": sender}, "text": text,
                                        "chat": {"id": sender, "type": chat_type}}}


def test_only_the_owner_in_a_private_chat_gets_answers(monkeypatch):
    monkeypatch.setenv("TELEGRAM_USER_ID", OWNER)
    sent = []
    send = lambda reply, chat_id, cfg: sent.append((reply, chat_id))
    telegram_bot.process_update(_message(999, "/help"), None, CFG, send=send)
    telegram_bot.process_update(_message(int(OWNER), "/help", chat_type="group"), None, CFG, send=send)
    assert sent == []
    telegram_bot.process_update(_message(int(OWNER), "/help"), None, CFG, send=send)
    assert len(sent) == 1 and sent[0][1] == int(OWNER)


def test_button_tap_is_acknowledged_and_its_buttons_removed(monkeypatch):
    monkeypatch.setenv("TELEGRAM_USER_ID", OWNER)
    calls, sent = [], []
    tap = {"update_id": 2, "callback_query": {
        "id": "abc", "from": {"id": int(OWNER)}, "data": "old:button",
        "message": {"message_id": 9, "chat": {"id": int(OWNER), "type": "private"}}}}
    telegram_bot.process_update(tap, None, CFG, send=lambda r, c, cfg: sent.append(r),
                                call=lambda method, data: calls.append(method))
    assert calls == ["answerCallbackQuery", "editMessageReplyMarkup"]
    assert "expired" in sent[0].text


def test_a_broken_update_is_logged_not_raised(monkeypatch):
    monkeypatch.setenv("TELEGRAM_USER_ID", OWNER)
    telegram_bot.process_update({"message": {"from": {"id": 1}}}, None, CFG)  # no chat: must not raise


def test_first_run_skips_old_messages_but_answers_recent_ones():
    now = 1_000_000
    old, recent = {"message": {"date": now - 3600}}, {"message": {"date": now - 60}}
    conn = memory_db()
    updates = [{"update_id": 40, **old}, {"update_id": 41, **old}, {"update_id": 42, **recent}]
    assert telegram_bot.skip_backlog(conn, call=lambda m, d: updates, now=now) == 42  # 42 still answered
    assert db.get_state(conn, telegram_bot.OFFSET_KEY) == "42"
    only_recent = [{"update_id": 50, **recent}]
    assert telegram_bot.skip_backlog(memory_db(), call=lambda m, d: only_recent, now=now) == 50
    assert telegram_bot.skip_backlog(memory_db(), call=lambda m, d: [], now=now) == 0
