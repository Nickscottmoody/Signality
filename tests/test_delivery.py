from signality import delivery, telegram
from signality.messages import StoryCard

CFG = {"importance": {"thresholds": {"alert": 75, "silent": 50, "digest": 25}}}


def test_route_by_score():
    assert delivery.route(80, "confirmed", CFG) == "alert"
    assert delivery.route(60, "reported", CFG) == "silent"
    assert delivery.route(30, "likely", CFG) == "digest"
    assert delivery.route(10, "confirmed", CFG) == "stored"


def test_unconfirmed_stories_never_alert_or_ping():
    for label in ("unverified", "disputed"):
        assert delivery.route(95, label, CFG) == "digest"
        assert delivery.route(60, label, CFG) == "digest"


def test_low_scoring_unconfirmed_story_is_still_just_stored():
    assert delivery.route(10, "unverified", CFG) == "stored"


def card(headline="OpenAI <launches> GPT & more"):
    return StoryCard(story_id=1, headline=headline, summary="S.", why_it_matters="W.",
                     label="reported", label_reason="One outlet so far (Reuters).", self_reported=True,
                     partial=True, importance=80, factors=dict(impact=4, breadth=4, urgency=4, novelty=3),
                     topics=["model_releases"], sources=[("Reuters", "https://example.com/a?x=1&y=2")])


def test_card_escapes_html_and_shows_evidence():
    body = telegram.render_card(card(), "alert")
    assert "&lt;launches&gt; GPT &amp; more" in body       # text can't break the formatting
    assert "🟡 Reported: One outlet so far (Reuters)." in body
    assert "self-reported" in body and "Partial" in body
    assert body.startswith("🚨")


def test_caption_length_ignores_link_addresses_and_tags():
    body = '<b>Hi</b> <a href="https://example.com/very/long/address">link</a>'
    assert telegram.visible_length(body) == len("Hi link")


def test_digest_always_fits_in_one_message():
    from signality.messages import Message
    cards = [card("x" * 200) for _ in range(30)]
    message = Message(kind="digest", silent=True, title="Morning digest", text="30 stories.", cards=cards)
    text, kept, _ = telegram.fit_digest(message)
    assert telegram.visible_length(text) <= telegram.TEXT_LIMIT
    assert 3 <= len(kept) < 30 and f"plus {30 - len(kept)} more" in text


def test_silent_tier_can_be_folded_into_the_digest():
    cfg = {**CFG, "delivery": {"silent_messages": False}}
    assert delivery.route(60, "reported", cfg) == "digest"
    assert delivery.route(80, "confirmed", cfg) == "alert"   # alerts are unaffected
