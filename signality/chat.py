"""Siggy's side of a chat: what to answer when the user types or taps something.

Platform-neutral on purpose. A chat app (today: Telegram, see telegram_bot.py)
turns the user's message into a call here and shows the Reply objects it gets
back. Nothing in this file knows about Telegram.

Users are identified as "platform:account id" (e.g. "telegram:12345"), so the
same code can serve other apps or more people later.
"""
from . import profile
from .messages import Reply

# name -> (one-line description for /help, function). Filled by @command below.
COMMANDS = {}


def command(name, description, coming=False):
    """Register a chat command. coming=True lists it in /help as 'coming soon'."""
    def register(func):
        COMMANDS[name] = (description, func, coming)
        return func
    return register


def menu():
    """[(command, description)] for the platform's command menu: working commands only."""
    return [(name, desc) for name, (desc, _, coming) in COMMANDS.items() if not coming]


def handle(conn, cfg, user, text):
    """Answer one typed message. Returns a list of Replies (usually one)."""
    text = (text or "").strip()
    if not text.startswith("/"):
        if text and profile.in_progress(conn, user):  # an answer to an interview question
            return profile.on_text(conn, cfg, user, text)
        return [Reply("I only understand commands so far. Chatting about the news comes later. "
                      "Tap /help to see what I can do.")]
    name = text.split()[0][1:].split("@")[0].lower()  # "/Help@Signalitynewsbot now" -> "help"
    args = text[len(text.split()[0]):].strip()
    if name not in COMMANDS:
        return [Reply(f"I don't know /{name} yet. Tap /help to see what I can do.")]
    _, func, coming = COMMANDS[name]
    if coming:
        return [Reply(f"/{name} is coming soon. Siggy's still building it. 🛠️")]
    return func(conn, cfg, user, args)


def handle_button(conn, cfg, user, data):
    """Answer a tapped button. data is the button's short code, e.g. 'pf:status:0'."""
    if data.startswith(profile.PREFIX + ":"):
        return profile.on_button(conn, cfg, user, data)
    return [Reply("That button has expired. Tap /help to start again.")]


@command("start", "Say hello and see what Siggy can do")
def _start(conn, cfg, user, args):
    return [Reply("I'm Siggy, your AI-news agent. I watch the news, score every story, and track "
                  "claims until they're proven. You'll get a digest every morning and a 🚨 alert "
                  "when something big breaks.\n\nTap /help to see my commands.",
                  title="👋 Hi! Siggy here.", image="normal")]


@command("help", "List Siggy's commands")
def _help(conn, cfg, user, args):
    ready = [f"/{name} · {desc}" for name, (desc, _, coming) in COMMANDS.items() if not coming]
    soon = [f"/{name} · {desc}" for name, (desc, _, coming) in COMMANDS.items() if coming]
    text = "\n".join(ready)
    if soon:
        text += "\n\nComing soon:\n" + "\n".join(soon)
    return [Reply(text, title="🤖 What I can do")]


@command("profile", "Answer 12 quick questions so I can explain how news affects you")
def _profile(conn, cfg, user, args):
    return profile.start(conn, cfg, user)


@command("cancel", "Stop the interview without saving")
def _cancel(conn, cfg, user, args):
    return profile.cancel(conn, user)


# Stage 2c: listed now so /help shows what's on the way; each one is switched on as it's built.
command("myprofile", "See the profile I saved about you", coming=True)(None)
command("editprofile", "Change one answer in your profile", coming=True)(None)
command("deleteprofile", "Erase your profile", coming=True)(None)
