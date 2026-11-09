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


def test_related_headlines_are_grouped_but_different_stories_are_not():
    from signality.dedup import key_words, related
    a = key_words("Nvidia board opens probe into CEO Jensen Huang")
    assert related(a, key_words("Trump backs Nvidia CEO Jensen Huang after affair admission"))
    assert not related(a, key_words("Nvidia announces new Korea investments"))
    assert not related(key_words("OpenAI raises new AI funding"), key_words("Anthropic AI model release"))


def test_digest_item_shows_related_count():
    c = card()
    c.related_ids = [5, 6, 7]
    assert "➕ 3 related stories on this" in telegram.render_digest_item(1, c)


def test_alert_note_is_separated_from_links_by_a_blank_line():
    body = telegram.render_card(card(), "alert", note="Why this is an alert: big news.")
    assert "</a>\n\n<i>Why this is an alert" in body


def receipt():
    from signality.messages import ReceiptCard
    return ReceiptCard(event_id=9, claim_id=3, claim="Jensen Huang had a <relationship> with Alice Huang",
                       claimant="US memo, as reported by the FT", first_label="reported", first_date="2026-11-07",
                       first_source=("FT", "https://ft.com/a"), outcome="confirmed", outcome_date="2026-11-08",
                       reason="Nvidia's board published Huang's apology naming her.",
                       evidence_source=("TechCrunch", "https://tc.com/b"), story_headline="Nvidia memo")


def test_receipt_shows_before_after_and_both_links():
    body = telegram.render_receipt(receipt())
    assert "🧾 <b>Receipt · ✅ Confirmed</b>" in body
    assert "&lt;relationship&gt;" in body
    assert "<b>Nov 7:</b> 🟡 Reported, claimed by US memo, as reported by the FT" in body
    assert "<b>Nov 8:</b> ✅ Confirmed." in body
    assert "original (FT)" in body and "evidence (TechCrunch)" in body


def test_digest_carries_receipts_section():
    from signality.messages import Message
    m = Message(kind="digest", silent=True, title="Morning digest", text="1 receipt.", cards=[card()], receipts=[receipt()])
    text, _, _ = telegram.fit_digest(m)
    assert "🧾 <b>Receipts: claims that resolved</b>" in text and "✅ Confirmed:</b>" in text


def test_long_reason_is_cut_to_whole_sentences():
    r = receipt()
    r.reason = "First sentence is here. " * 30
    body = telegram.render_receipt(r)
    line = next(l for l in body.split("\n") if l.startswith("<b>Nov 8"))
    assert len(line) < 360 and line.rstrip().endswith(".")
