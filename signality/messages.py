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

    @property
    def label_text(self):
        return validity.LABELS[self.label]


@dataclass
class Message:
    kind: str                       # alert | silent | digest | notice
    silent: bool                    # deliver without sound
    image: str | None = None        # key into config siggy.images: alert | normal | thinking
    title: str = ""
    cards: list = field(default_factory=list)
    unconfirmed: list = field(default_factory=list)  # digest only: 🟠/🔴 stories, shown apart
    text: str = ""                  # body for notices
    note: str = ""                  # small extra line, e.g. why an alert was sent quietly


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
