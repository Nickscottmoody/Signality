"""Sends Siggy's messages to Telegram.

Uses Telegram's Bot API directly with requests (which has its own HTTPS
certificates). Two-way chat commands arrive in a later stage.

Send a test message from the project folder:
    ./.venv/bin/python -m signality.telegram
"""
import html
import re

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


# --- Rendering: platform-neutral Message -> Telegram HTML -------------------

CAPTION_LIMIT = 1024   # Telegram's limit for text under a photo
TEXT_LIMIT = 4000      # a little under Telegram's 4096 limit for one message
TIER_ICON = {"alert": "🚨", "silent": "🔔"}


def visible_length(body):
    """Length as Telegram counts it: tags and link addresses excluded, in UTF-16 units (emoji = 2)."""
    text = html.unescape(re.sub(r"<[^>]+>", "", body))
    return len(text.encode("utf-16-le")) // 2


def _e(text):
    return html.escape(text or "", quote=False)


def _links(sources, limit=4):
    return " · ".join(f'<a href="{html.escape(url)}">{_e(name)}</a>' for name, url in sources[:limit])


def render_card(card, kind, note=""):
    """One story, in full (used for 🚨 and 🔔)."""
    f = card.factors
    lines = [
        f"{TIER_ICON.get(kind, '')} <b>{_e(card.headline)}</b>".strip(),
        _e(card.summary),
        "",
        f"<b>Why it matters:</b> {_e(card.why_it_matters)}",
        "",
        f"{card.label_text}: {_e(card.label_reason)}",
    ]
    if card.self_reported:
        lines.append("🏷️ Company claims are self-reported (not independently verified)")
    if card.partial:
        lines.append("📄 Partial: summarized from a preview only")
    lines.append(f"📊 Importance {card.importance}/100 · Impact {f['impact']} · Breadth {f['breadth']}"
                 f" · Urgency {f['urgency']} · Novelty {f['novelty']}")
    lines.append(f"🔗 {_links(card.sources)}")
    if note:
        lines.append(f"<i>{_e(note)}</i>")
    return "\n".join(lines)


def render_digest_item(n, card):
    extras = " · 📄 partial" if card.partial else ""
    extras += " · 🏷️ self-reported" if card.self_reported else ""
    return (f"<b>{n}. {_e(card.headline)}</b>\n{_e(card.why_it_matters)}\n"
            f"{card.label_text} · 📊 {card.importance}{extras} · {_links(card.sources, 2)}")


def render_unconfirmed_item(card):
    return (f"<b>• {_e(card.headline)}</b>\n"
            f"{card.label_text}: {_e(card.label_reason)} · {_links(card.sources, 2)}")


def _chunks(blocks, limit=TEXT_LIMIT):
    """Join blocks with blank lines, splitting into messages that fit Telegram's limit."""
    out, current = [], ""
    for block in blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > limit and current:
            out.append(current)
            current = block
        else:
            current = candidate
    if current:
        out.append(current)
    return out


def deliver(message, cfg, chat_id=None):
    """Send a platform-neutral Message to Telegram. Returns the first Telegram message id."""
    images = cfg["siggy"]["images"]
    first_id = None

    def remember(result):
        nonlocal first_id
        if first_id is None:
            first_id = result["message_id"]

    if message.kind in ("alert", "silent"):
        body = render_card(message.cards[0], message.kind, message.note)
        image = images["alert"] if message.kind == "alert" else (
            images["normal"] if cfg["delivery"]["image_on_silent"] else None)
        if image and visible_length(body) <= CAPTION_LIMIT:
            remember(send_photo(image, body, chat_id, silent=message.silent))
        else:
            if image:
                remember(send_photo(image, TIER_ICON.get(message.kind, ""), chat_id, silent=message.silent))
            remember(send_message(body, chat_id, silent=message.silent))
    elif message.kind == "digest":
        remember(send_photo(images["normal"], f"<b>{_e(message.title)}</b>\n{_e(message.text)}", chat_id, silent=True))
        blocks = [render_digest_item(i, c) for i, c in enumerate(message.cards, 1)]
        if message.unconfirmed:
            blocks.append("⚠️ <b>Unconfirmed: read with care</b>")
            blocks += [render_unconfirmed_item(c) for c in message.unconfirmed]
        for chunk in _chunks(blocks):
            remember(send_message(chunk, chat_id, silent=True))
    else:  # notice
        body = f"<b>{_e(message.title)}</b>\n{_e(message.text)}" if message.title else _e(message.text)
        image = images.get(message.image) if message.image else None
        if image and visible_length(body) <= CAPTION_LIMIT:
            remember(send_photo(image, body, chat_id, silent=message.silent))
        else:
            remember(send_message(body, chat_id, silent=message.silent))
    return first_id


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
