from signality.validity import decide, repeats_another_outlet


def art(id, source_id, source_type="news", title="Something happened"):
    return {"id": id, "source_id": source_id, "source_name": source_id.upper(),
            "source_type": source_type, "title": title}


def tri(sourcing="on_record_reporting", content_type="news", article_id=1, attributed_to=None):
    return {"sourcing": sourcing, "content_type": content_type, "article_id": article_id,
            "attributed_to": attributed_to, "self_reported": 0}


def test_primary_source_is_confirmed():
    label, reason, _ = decide(tri("official_source"), [art(1, "openai", "primary")])
    assert label == "confirmed" and "OPENAI itself" in reason


def test_two_independent_outlets_is_likely():
    label, _, n = decide(tri(), [art(1, "reuters"), art(2, "wsj")])
    assert (label, n) == ("likely", 2)


def test_one_outlet_is_reported():
    assert decide(tri(), [art(1, "reuters")])[0] == "reported"


def test_repeating_another_outlet_does_not_count_as_independent():
    # Bloomberg repeats the FT: still only one independent source.
    articles = [art(1, "ft"), art(2, "bloomberg", title="Nvidia tells clients to trim China business, FT Says")]
    label, _, n = decide(tri(article_id=1), articles)
    assert (label, n) == ("reported", 1)


def test_two_articles_from_same_outlet_count_once():
    assert decide(tri(), [art(1, "ap"), art(2, "ap")])[0] == "reported"


def test_rumor_from_one_outlet_is_unverified():
    assert decide(tri("rumor_leak_social"), [art(1, "the_information")])[0] == "unverified"


def test_denial_is_disputed():
    assert decide(tri("denial_or_correction"), [art(1, "reuters"), art(2, "ap")])[0] == "disputed"


def test_opinion_gets_no_factual_label():
    assert decide(tri("not_applicable", "opinion"), [art(1, "reason")])[0] == "opinion"


def test_repeat_pattern():
    assert repeats_another_outlet("Nvidia Tells Clients to Trim China Business, FT Says")
    assert repeats_another_outlet("OpenAI in talks to raise funds, report says")
    assert not repeats_another_outlet("OpenAI says new model beats rivals")


def test_outlet_citing_its_own_earlier_scoop_is_not_a_repeat():
    t = tri("repeats_other_outlet", attributed_to="The Information")
    a = [{"id": 1, "source_id": "the_information", "source_name": "The Information",
          "source_type": "specialist", "title": "Shares fall after report on Anthropic"}]
    label, reason, n = decide(t, a)
    assert label == "reported" and "relaying" not in reason and n == 1
