"""Listens for the user's Telegram messages and button taps, and sends Siggy's replies.

A thin layer: it only translates between Telegram and chat.py (where the
answers are decided). It uses "long polling": we ask Telegram "anything new?"
and Telegram holds the question open until a message arrives or the wait ends.

Only the owner (TELEGRAM_USER_ID in .env) is answered, and only in a private
chat, so personal details can never land in a group or the public channel.
"""
import json
import logging
import threading
import time

import requests

from . import chat, db, telegram
from .settings import load_config, secret

log = logging.getLogger("signality")

OFFSET_KEY = "telegram_update_offset"  # app_state: the next update we haven't handled yet


def user_key(telegram_user_id):
    """Platform + account id: how the core identifies a user."""
    return f"telegram:{telegram_user_id}"


def _body(reply):
    e = telegram._e
    return f"<b>{e(reply.title)}</b>\n{e(reply.text)}" if reply.title else e(reply.text)


def send_reply(reply, chat_id, cfg):
    """Show one chat.Reply in Telegram as ONE message."""
    body = _body(reply)
    if reply.image and telegram.visible_length(body) <= telegram.CAPTION_LIMIT:
        return telegram.send_photo(cfg["siggy"]["images"][reply.image], body, chat_id, buttons=reply.buttons)
    image_url = cfg["siggy"].get("image_urls", {}).get(reply.image) if reply.image else None
    return telegram.send_message(body, chat_id, image_url=image_url, buttons=reply.buttons)


def send_to_user(user_key, reply, cfg):
    """Start a message to a user (not a reply), e.g. the profile check-in."""
    platform, account_id = user_key.split(":", 1)
    if platform != "telegram":
        raise ValueError(f"not a Telegram user: {user_key}")
    return send_reply(reply, account_id, cfg)


def is_owner(sender_id, chat_type):
    owner = secret("TELEGRAM_USER_ID")
    return bool(owner) and str(sender_id) == owner and chat_type == "private"


def _typing(chat_id, call):
    """Show "typing..." while Siggy works (some answers take a few seconds)."""
    try:
        call("sendChatAction", {"chat_id": chat_id, "action": "typing"})
    except telegram.TelegramError:
        pass


def _edit(reply, chat_id, message_id, call):
    """Update the tapped message in place (its text and buttons). False if Telegram refused."""
    try:
        call("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": _body(reply),
                                 "parse_mode": "HTML",
                                 "reply_markup": telegram.keyboard(reply.buttons) or '{"inline_keyboard": []}'})
        return True
    except telegram.TelegramError as e:
        return "not modified" in str(e)  # same text tapped twice: nothing to change, that's fine


def process_update(update, conn, cfg, send=send_reply, call=telegram._call):
    """Handle one Telegram update (a typed message or a button tap). Never raises."""
    try:
        if "message" in update:
            msg = update["message"]
            sender, chat_info = msg.get("from", {}), msg["chat"]
            if not is_owner(sender.get("id"), chat_info.get("type")):
                log.info("chat: ignored a message from someone who isn't the owner")
                return
            chat_id = chat_info["id"]
            _typing(chat_id, call)
            for reply in chat.handle(conn, cfg, user_key(sender["id"]), msg.get("text", "")):
                send(reply, chat_id, cfg)
        elif "callback_query" in update:
            tap = update["callback_query"]
            msg = tap.get("message", {})
            call("answerCallbackQuery", {"callback_query_id": tap["id"]})  # stops the button's spinner
            if not is_owner(tap["from"]["id"], msg.get("chat", {}).get("type")):
                log.info("chat: ignored a button tap from someone who isn't the owner")
                return
            chat_id, message_id = msg["chat"]["id"], msg["message_id"]
            _typing(chat_id, call)
            replies = chat.handle_button(conn, cfg, user_key(tap["from"]["id"]), tap.get("data", ""))
            if not any(r.replace for r in replies):
                try:  # remove the tapped buttons, so an answer can't be sent twice
                    call("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id,
                                                    "reply_markup": '{"inline_keyboard": []}'})
                except telegram.TelegramError:
                    pass  # e.g. the message is too old to edit; the tap still counts
            for reply in replies:
                if not (reply.replace and _edit(reply, chat_id, message_id, call)):
                    send(reply, chat_id, cfg)
    except Exception:
        log.exception("chat: couldn't handle a Telegram update")


def set_command_menu(call=telegram._call):
    """Show Siggy's working commands in Telegram's '/' menu."""
    commands = [{"command": name, "description": desc} for name, desc in chat.menu()]
    call("setMyCommands", {"commands": json.dumps(commands)})


BACKLOG_MINUTES = 15  # first run: still answer messages sent this recently


def skip_backlog(conn, call=telegram._call, now=None):
    """First run only: ignore old messages, but answer ones from the last few minutes
    (e.g. a /help sent just before the restart)."""
    now = now or time.time()
    updates = call("getUpdates", {"timeout": 0})
    old = [u["update_id"] for u in updates
           if u.get("message", {}).get("date", 0) < now - BACKLOG_MINUTES * 60]
    offset = max(old, default=min((u["update_id"] for u in updates), default=0) - 1) + 1
    db.set_state(conn, OFFSET_KEY, str(offset))
    return offset


def listen(stop=None):
    """Wait for messages forever (or until stop is set). Survives network outages."""
    stop = stop or threading.Event()
    cfg = load_config()
    conn = db.connect(cfg["storage"]["db_path"])  # this thread's own connection
    failures, menu_set, listening = 0, False, None
    while not stop.is_set():
        try:
            cfg = load_config()  # reread, so switching chat on/off in config.yaml needs no restart
            if cfg["chat"]["enabled"] != listening:
                listening = cfg["chat"]["enabled"]
                log.info("chat: %s", "listening for Telegram commands" if listening else "switched off in config")
            if not listening:
                stop.wait(60)
                continue
            if db.get_state(conn, OFFSET_KEY) is None:
                skip_backlog(conn)
            if not menu_set:
                set_command_menu()
                menu_set = True
            wait = cfg["chat"]["long_poll_seconds"]
            offset = int(db.get_state(conn, OFFSET_KEY))
            updates = telegram._call("getUpdates", {
                "offset": offset, "timeout": wait,
                "allowed_updates": '["message", "callback_query"]',
            }, timeout=wait + 15)
            if failures:
                log.info("chat: reconnected to Telegram")
            failures = 0
            for update in updates:
                # Save progress first: a message that crashes us must not be retried forever.
                db.set_state(conn, OFFSET_KEY, str(update["update_id"] + 1))
                process_update(update, conn, cfg)
        except (requests.RequestException, telegram.TelegramError) as e:
            failures += 1
            if failures == 1:  # log once per outage, not every retry
                log.warning("chat: can't reach Telegram (%s); retrying quietly", str(e)[:120])
            stop.wait(min(60, 5 * failures))
        except Exception:
            failures += 1
            log.exception("chat: listener error; retrying")
            stop.wait(min(60, 5 * failures))
    conn.close()


def start_in_background():
    """Run the listener next to the news loop. Returns the thread."""
    thread = threading.Thread(target=listen, name="telegram-chat", daemon=True)
    thread.start()
    return thread


if __name__ == "__main__":
    # Try it in the foreground (Ctrl+C to stop). Don't run this while the service is
    # running: Telegram lets only one program listen at a time.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(message)s")
    try:
        listen()
    except KeyboardInterrupt:
        pass
