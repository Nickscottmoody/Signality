"""Sends Siggy's messages to Telegram.

Uses Telegram's Bot API directly with requests (which has its own HTTPS
certificates). Two-way chat commands arrive in a later stage.

Send a test message from the project folder:
    ./.venv/bin/python -m signality.telegram
"""
import html
import json
import re

import requests

from . import claims, db
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


def send_message(text, chat_id=None, silent=False, image_url=None):
    """Send a text message. Text may use simple HTML: <b>, <i>, <a href>.

    With image_url, Telegram shows that picture above the text, all in ONE message.
    """
    preview = ({"url": image_url, "show_above_text": True, "prefer_large_media": True}
               if image_url else {"is_disabled": True})
    return _call("sendMessage", {
        "chat_id": _chat_id(chat_id),
        "text": text,
        "parse_mode": "HTML",
        "disable_notification": silent,
        "link_preview_options": json.dumps(preview),
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
        lines += ["", f"<i>{_e(note)}</i>"]  # blank line keeps it apart from the source links
    return "\n".join(lines)


def render_digest_item(n, card):
    extras = " · 📄 partial" if card.partial else ""
    extras += " · 🏷️ self-reported" if card.self_reported else ""
    more = len(card.related_ids)
    related = f"\n➕ {more} related {'story' if more == 1 else 'stories'} on this" if more else ""
    return (f"<b>{n}. {_e(card.headline)}</b>\n{_e(card.why_it_matters)}\n"
            f"{card.label_text} · 📊 {card.importance}{extras} · {_links(card.sources, 2)}{related}")


def render_unconfirmed_item(card):
    return (f"<b>• {_e(card.headline)}</b>\n"
            f"{card.label_text}: {_e(card.label_reason)} · {_links(card.sources, 2)}")


def _day(iso_date):
    """'2026-11-07' -> 'Nov 7'."""
    from datetime import date
    d = date.fromisoformat(iso_date[:10])
    return f"{d:%b} {d.day}"


def _receipt_links(r):
    links = [f'<a href="{html.escape(r.first_source[1])}">original ({_e(r.first_source[0])})</a>']
    if r.evidence_source[1]:
        links.append(f'<a href="{html.escape(r.evidence_source[1])}">evidence ({_e(r.evidence_source[0])})</a>')
    return " · ".join(links)


def _short(text, max_chars=280):
    """The first sentence or two, so an older long explanation still fits a receipt."""
    if len(text) <= max_chars:
        return text
    out = ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if out and len(out) + len(sentence) > max_chars:
            break
        out = f"{out} {sentence}".strip()
    return out if len(out) <= max_chars else out[: max_chars - 1].rstrip() + "…"


def render_receipt(r, compact=False):
    """A resolved claim: what was claimed, by whom, when, and how it turned out."""
    outcome = claims.STATUSES[r.outcome]
    reason = _short(r.reason)
    if compact:  # one item in the digest
        return (f"🧾 <b>{outcome}:</b> “{_e(r.claim)}”\n{_e(reason)}\n🔗 {_receipt_links(r)}")
    return "\n".join([
        f"🧾 <b>Receipt · {outcome}</b>",
        f"“{_e(r.claim)}”",
        "",
        f"<b>{_day(r.first_date)}:</b> {claims.LABELS[r.first_label]}, claimed by {_e(r.claimant or r.first_source[0])}",
        f"<b>{_day(r.outcome_date)}:</b> {outcome}. {_e(reason)}",
        "",
        f"🔗 {_receipt_links(r)}",
    ])


def fit_digest(message, limit=TEXT_LIMIT):
    """The digest as ONE message: drop the lowest-ranked stories until it fits.

    Returns (text, cards included, unconfirmed included).
    """
    cards, unconfirmed = list(message.cards), list(message.unconfirmed)
    while True:
        dropped = (len(message.cards) - len(cards)) + (len(message.unconfirmed) - len(unconfirmed))
        blocks = [f"<b>{_e(message.title)}</b>\n{_e(message.text)}"]
        blocks += [render_digest_item(i, c) for i, c in enumerate(cards, 1)]
        if message.receipts:
            blocks.append("🧾 <b>Receipts: claims that resolved</b>")
            blocks += [render_receipt(r, compact=True) for r in message.receipts]
        if unconfirmed:
            blocks.append("⚠️ <b>Unconfirmed: read with care</b>")
            blocks += [render_unconfirmed_item(c) for c in unconfirmed]
        if dropped:
            blocks.append(f"<i>…plus {dropped} more lower-ranked {'story' if dropped == 1 else 'stories'}, "
                          "saved and searchable.</i>")
        text = "\n\n".join(blocks)
        if visible_length(text) <= limit or not (cards or unconfirmed):
            return text, cards, unconfirmed
        if len(cards) > 3 or not unconfirmed:  # trim main list first, keep at least 3
            cards.pop()
        else:
            unconfirmed.pop()


def deliver(message, cfg, chat_id=None):
    """Send a platform-neutral Message to Telegram as ONE notification.

    Returns {"message_id": ..., "story_ids": [stories actually included]}.
    """
    images, image_urls = cfg["siggy"]["images"], cfg["siggy"].get("image_urls", {})

    def with_image(body, key, silent):
        """Photo with caption if it fits; otherwise the picture shown above a text message."""
        if key and visible_length(body) <= CAPTION_LIMIT:
            return send_photo(images[key], body, chat_id, silent=silent)
        return send_message(body, chat_id, silent=silent, image_url=image_urls.get(key) if key else None)

    if message.kind in ("alert", "silent"):
        key = "alert" if message.kind == "alert" else ("normal" if cfg["delivery"]["image_on_silent"] else None)
        result = with_image(render_card(message.cards[0], message.kind, message.note), key, message.silent)
        return {"message_id": result["message_id"], "story_ids": [message.cards[0].story_id]}

    if message.kind == "digest":
        text, cards, unconfirmed = fit_digest(message)
        result = send_message(text, chat_id, silent=True, image_url=image_urls.get("normal"))
        included = [c.story_id for c in cards + unconfirmed] + [i for c in cards + unconfirmed for i in c.related_ids]
        return {"message_id": result["message_id"], "story_ids": included,
                "receipt_event_ids": [r.event_id for r in message.receipts]}

    if message.kind == "receipt":
        result = with_image(render_receipt(message.receipts[0]), "normal", message.silent)
        return {"message_id": result["message_id"], "story_ids": [],
                "receipt_event_ids": [message.receipts[0].event_id]}

    body = f"<b>{_e(message.title)}</b>\n{_e(message.text)}" if message.title else _e(message.text)
    result = with_image(body, message.image, message.silent)
    return {"message_id": result["message_id"], "story_ids": []}


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
