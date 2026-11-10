import sqlite3

import pytest

from signality import db, delivery, messages, telegram

CFG = {"siggy": {"image_urls": {"alert": "https://example.com/red.png", "normal": "https://example.com/yellow.png"}},
       "impact_notes": {"enabled": False}}


# --- editing an alert in place (Telegram side) ---

def _message():
    card = messages.StoryCard(
        story_id=1, headline="Anthropic seeks $1.4T valuation", summary="s", why_it_matters="w", label="reported",
        label_reason="One outlet so far.", self_reported=False, partial=False, importance=87,
        factors={"impact": 5, "breadth": 4, "urgency": 4, "novelty": 4}, topics=[], sources=[("Bloomberg", "https://b")])
    receipt = messages.ReceiptCard(
        event_id=9, claim_id=3, claim="Anthropic seeks about $1.4T", claimant="Bloomberg", first_label="reported",
        first_date="2026-11-10", first_source=("Bloomberg", "https://b"), outcome="confirmed",
        outcome_date="2026-11-10", reason="Confirmed by the filing.", evidence_source=("TechCrunch", "https://t"), story_headline="h")
    return messages.Message(kind="alert", silent=True, image="alert", cards=[card], note="Why: big",
                            receipts=[receipt])


def test_photo_alert_gets_its_caption_edited(monkeypatch):
    calls = []
    monkeypatch.setattr(telegram, "edit_caption", lambda mid, body, chat_id=None: calls.append(("caption", body)))
    monkeypatch.setattr(telegram, "edit_text", lambda *a, **k: calls.append(("text",)))
    assert telegram.update_delivered(_message(), 55, CFG) is True
    assert calls[0][0] == "caption" and "🧾" in calls[0][1] and "Why: big" in calls[0][1]


def test_text_alert_falls_back_to_editing_text(monkeypatch):
    def no_caption(*a, **k):
        raise telegram.TelegramError("Bad Request: there is no caption in the message to edit")
    edits = []
    monkeypatch.setattr(telegram, "edit_caption", no_caption)
    monkeypatch.setattr(telegram, "edit_text", lambda mid, body, chat_id=None, image_url=None: edits.append(image_url))
    assert telegram.update_delivered(_message(), 55, CFG) is True
    assert edits == ["https://example.com/red.png"]  # Siggy stays above the text


def test_receipt_that_no_longer_fits_a_photo_is_left_for_the_digest(monkeypatch):
    def is_photo(*a, **k):
        raise telegram.TelegramError("Bad Request: there is no text in the message to edit")
    monkeypatch.setattr(telegram, "edit_caption", lambda *a, **k: pytest.fail("too long for a caption"))
    monkeypatch.setattr(telegram, "edit_text", is_photo)
    m = _message()
    m.cards[0].summary = "A long summary. " * 70  # the alert's caption was nearly full already
    assert telegram.update_delivered(m, 55, CFG) is False


# --- which alert a receipt is added to (delivery side) ---

def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.migrate(conn)
    return conn


def test_receipt_is_added_to_its_alert_and_still_waits_for_the_digest(monkeypatch):
    conn = _db()
    monkeypatch.setattr(delivery, "recipient", lambda: "telegram:1")
    monkeypatch.setattr(delivery.receipts, "pending", lambda conn, who: [9])
    monkeypatch.setattr(delivery.receipts, "card", lambda conn, e: _message().receipts[0])
    monkeypatch.setattr(delivery.messages, "story_card", lambda conn, sid: _message().cards[0])
    monkeypatch.setattr(delivery.impact, "stored_note", lambda *a, **k: "")
    edited = []
    monkeypatch.setattr(delivery.telegram, "update_delivered", lambda m, mid, cfg: edited.append((mid, len(m.receipts))) or True)
    conn.execute("INSERT INTO sources (id, name, url, type, added_at) VALUES ('bb','Bloomberg','u','news','t')")
    conn.execute("INSERT INTO stories (id, title, first_seen_at, last_seen_at) VALUES (1, 'x', 't', 't')")
    conn.execute("INSERT INTO articles (id, source_id, story_id, guid, url, title, title_words, snippet, published_at,"
                 " fetched_at) VALUES (1, 'bb', 1, 'g', 'https://b', 'x', '', '', 't', 't')")
    conn.execute("INSERT INTO claims (id, story_id, article_id, text, kind, basis, self_reported, label, status,"
                 " created_at, updated_at) VALUES (3, 1, 1, 'c', 'event', 'b', 0, 'confirmed', 'confirmed', 't', 't')")
    conn.execute("INSERT INTO claim_events (id, claim_id, at, event, label, status, reason, decided_by)"
                 " VALUES (9, 3, 't', 'resolved', 'confirmed', 'confirmed', 'r', 'm')")
    conn.execute(
        "INSERT INTO story_triage (story_id, article_id, model, created_at, text_source, headline, summary,"
        " why_it_matters, topics, content_type, sourcing, self_reported, impact, impact_reason, breadth,"
        " breadth_reason, urgency, urgency_reason, novelty, novelty_reason, base_score, topic_multiplier,"
        " importance, cost_usd) VALUES (1, 1, 'm', 't', 'full', 'Anthropic seeks $1.4T valuation', 's', 'w', '[]',"
        " 'news', 'x', 0, 3, 'r', 3, 'r', 3, 'r', 3, 'r', 50, 1, 87, 0)")
    conn.execute("INSERT INTO deliveries (story_id, recipient, kind, sent_at, local_date, channel_message_id, note)"
                 " VALUES (1, 'telegram:1', 'alert', ?, '2026-11-10', '55', 'Why: big')", (db.utcnow(),))
    assert delivery.attach_receipts_to_alerts(conn, CFG) == 1
    assert edited == [("55", 1)]
    assert delivery.attach_receipts_to_alerts(conn, CFG) == 0  # never added twice
    # The digest still lists it: attaching doesn't count as delivering.
    assert conn.execute("SELECT COUNT(*) FROM claim_receipts").fetchone()[0] == 0
