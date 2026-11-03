"""Sends Siggy's messages to Telegram.

Uses Telegram's Bot API directly with requests (which has its own HTTPS
certificates). Two-way chat commands arrive in a later stage.

Send a test message from the project folder:
    ./.venv/bin/python -m signality.telegram
"""
import html

import requests

from . import db
from .settings import ROOT, load_config, secret

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(Exception):
    """Telegram refused a request. The message says why."""


def _call(method, data, files=None):
    token = secret("TELEGRAM_BOT_TOKEN")
    if not token:
        raise TelegramError("TELEGRAM_BOT_TOKEN is missing from .env")
    response = requests.post(API.format(token=token, method=method),
                             data=data, files=files, timeout=30)
    body = response.json()
    if not body.get("ok"):
        raise TelegramError(body.get("description", f"HTTP {response.status_code}"))
    return body["result"]


def _chat_id(chat_id):
    chat_id = chat_id or secret("TELEGRAM_USER_ID")
    if not chat_id:
        raise TelegramError("TELEGRAM_USER_ID is missing from .env")
    return chat_id


def send_message(text, chat_id=None, silent=False):
    """Send a text message. Text may use simple HTML: <b>, <i>, <a href>."""
    return _call("sendMessage", {
        "chat_id": _chat_id(chat_id),
        "text": text,
        "parse_mode": "HTML",
        "disable_notification": silent,
        "disable_web_page_preview": True,
    })


def send_photo(image, caption, chat_id=None, silent=False):
    """Send one of Siggy's pictures with a caption (max 1024 characters)."""
    with open(ROOT / image, "rb") as f:
        return _call("sendPhoto", {
            "chat_id": _chat_id(chat_id),
            "caption": caption,
            "parse_mode": "HTML",
            "disable_notification": silent,
        }, files={"photo": f})


def test_message(cfg):
    """Siggy's hello, built from what's actually in the database."""
    conn = db.connect(cfg["storage"]["db_path"])
    sources = conn.execute("SELECT COUNT(*) FROM sources WHERE active = 1").fetchone()[0]
    articles = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    stories = conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
    latest = conn.execute(
        "SELECT a.title, s.name FROM articles a JOIN sources s ON s.id = a.source_id "
        "ORDER BY a.published_at DESC LIMIT 1"
    ).fetchone()
    conn.close()

    lines = [
        "<b>👋 Siggy here. Signality is online!</b>",
        "",
        f"I'm watching <b>{sources} sources</b> and holding "
        f"<b>{articles} AI articles</b> ({stories} unique stories).",
    ]
    if latest:
        lines += ["", f"Newest one I've got: <i>{html.escape(latest['title'])}</i> "
                      f"({html.escape(latest['name'])})"]
    lines += ["", "No scoring yet. That's next. For now I'm just proving I can reach you. 📡"]
    return "\n".join(lines)


def main():
    cfg = load_config()
    try:
        send_photo(cfg["siggy"]["images"]["normal"], test_message(cfg))
    except TelegramError as e:
        if "can't initiate conversation" in str(e) or "chat not found" in str(e):
            print("Telegram says the bot can't message you yet.")
            print("Open your bot in Telegram and press Start, then run this again.")
        else:
            print(f"Telegram error: {e}")
        raise SystemExit(1)
    print("Test message sent. Check Telegram on your phone.")


if __name__ == "__main__":
    main()
