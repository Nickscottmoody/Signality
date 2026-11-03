from signality.dedup import clean_url, similarity, strip_outlet_suffix, title_words


def test_clean_url_removes_tracking_and_fragment():
    a = clean_url("https://Example.com/story/?utm_source=x&id=7#comments")
    b = clean_url("https://example.com/story?id=7")
    assert a == b


def test_clean_url_keeps_meaningful_params():
    assert clean_url("https://x.com/a?id=1") != clean_url("https://x.com/a?id=2")


def test_strip_outlet_suffix():
    assert strip_outlet_suffix("OpenAI raises $40B - Reuters") == "OpenAI raises $40B"
    assert strip_outlet_suffix("Chips are back — AP News") == "Chips are back"


def test_title_words_drops_filler():
    assert title_words("The New Model Is Here") == {"model"}


def test_identical_headlines_match():
    a = title_words("Nvidia unveils Rubin chip for AI data centers")
    assert similarity(a, a) == 1.0


def test_lightly_reworded_headlines_match():
    a = title_words("Nvidia unveils Rubin chip for AI data centers")
    b = title_words("Nvidia unveils Rubin AI chip for data centers")
    assert similarity(a, b) >= 0.6


def test_different_stories_from_same_company_do_not_match():
    a = title_words("OpenAI launches GPT-6 model")
    b = title_words("OpenAI faces lawsuit from authors")
    assert similarity(a, b) < 0.6
