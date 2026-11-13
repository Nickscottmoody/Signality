"""Platform-neutral messages: WHAT Siggy says, not HOW a platform displays it.

Delivery builds these; a channel module (today: telegram.py) turns them into
that platform's format. Adding a website or another chat app later means
writing a new renderer, not changing the agent.
"""
import json
from dataclasses import dataclass, field

from . import scoring, validity


@dataclass
class StoryCard:
    """Everything shown about one story."""
    story_id: int
    headline: str
    summary: str
    why_it_matters: str
    label: str              # validity label code, e.g. 'likely'
    label_reason: str
    self_reported: bool
    partial: bool           # summarized from a preview only
    importance: int
    factors: dict           # impact/breadth/urgency/novelty -> 1-5
    topics: list
    sources: list           # [(outlet name, url), ...]
    related_ids: list = field(default_factory=list)  # digest: other stories on the same saga, folded in
    update_line: str = ""   # "🔄 Update": what's new, for a saga this reader already heard about (personal)
    impact_note: str = ""   # "🎯 How it affects you" (personal: never show in a public channel)

    @property
    def label_text(self):
        return validity.LABELS[self.label]


@dataclass
class ReceiptCard:
    """A resolved claim: what was claimed, what turned out to be true, and the evidence."""
    event_id: int
    claim_id: int
    claim: str
    claimant: str
    first_label: str         # claims.LABELS key when it was first reported
    first_date: str          # YYYY-MM-DD
    first_source: tuple      # (outlet name, url)
    outcome: str             # claims.STATUSES key: confirmed | walked_back | delayed | never_happened
    outcome_date: str
    reason: str
    evidence_source: tuple   # (outlet name, url)
    story_headline: str      # the story the claim came from (used to spot related alerts)


@dataclass
class Message:
    kind: str                       # alert | silent | digest | notice | receipt
    silent: bool                    # deliver without sound
    image: str | None = None        # key into config siggy.images: alert | normal | thinking
    title: str = ""
    cards: list = field(default_factory=list)
    unconfirmed: list = field(default_factory=list)  # digest only: 🟠/🔴 stories, shown apart
    receipts: list = field(default_factory=list)     # 🧾 ReceiptCards
    text: str = ""                  # body for notices
    note: str = ""                  # small extra line, e.g. why an alert was sent quietly
    reply_to: str | None = None     # an update: the platform's id of the earlier message it follows up


@dataclass
class Reply:
    """Siggy's answer to something the user typed or tapped in chat.

    Plain text only: the platform renderer handles escaping and formatting.
    """
    text: str
    title: str = ""                 # shown in bold above the text
    buttons: list = field(default_factory=list)  # rows of (label, data) tap buttons
    image: str | None = None        # key into config siggy.images, or None for text only
    replace: bool = False           # after a button tap: update the tapped message instead of sending a new one


def story_card(conn, story_id):
    t = conn.execute("SELECT * FROM story_triage WHERE story_id = ? AND purpose = 'live'", (story_id,)).fetchone()
    label = validity.current(conn, story_id) or validity.update(conn, story_id)
    sources = conn.execute(
        """
        SELECT s.name, a.url FROM articles a JOIN sources s ON s.id = a.source_id
        WHERE a.story_id = ? ORDER BY (s.type = 'primary') DESC, a.id
        """,
        (story_id,),
    ).fetchall()
    web = validity.web_evidence(conn, story_id) or {"results": []}
    sources = list(sources) + [(r["outlet"], r["url"]) for r in web["results"]]  # pages web search found
    seen, unique = set(), []
    for name, url in sources:  # one link per outlet
        if name not in seen:
            seen.add(name)
            unique.append((name, url))
    return StoryCard(
        story_id=story_id, headline=t["headline"], summary=t["summary"],
        why_it_matters=t["why_it_matters"], label=label["label"], label_reason=label["reason"],
        self_reported=bool(t["self_reported"]), partial=t["text_source"] == "snippet",
        importance=t["importance"], factors={f: t[f] for f in scoring.FACTORS},
        topics=json.loads(t["topics"]), sources=unique,
    )
