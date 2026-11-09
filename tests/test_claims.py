from signality.claims import initial_label


def claim(basis="on_record_reporting", kind="event", self_reported=False, claimant="Reuters"):
    return {"basis": basis, "kind": kind, "self_reported": self_reported, "claimant": claimant}


def test_official_event_is_confirmed_and_closed():
    assert initial_label(claim("official_source", claimant="OpenAI"), 1)[:2] == ("confirmed", "confirmed")


def test_official_plan_stays_open_until_it_happens():
    assert initial_label(claim("official_source", kind="future", claimant="OpenAI"), 1)[:2] == ("confirmed", "open")


def test_company_bragging_is_self_reported_and_open():
    label, status, reason = initial_label(claim("official_source", "performance", True, "OpenAI"), 3)
    assert (label, status) == ("self_reported", "open") and "OpenAI" in reason


def test_two_independent_outlets_make_a_claim_likely():
    assert initial_label(claim("anonymous_sources"), 2)[:2] == ("likely", "open")


def test_rumor_is_unverified_and_one_outlet_is_reported():
    assert initial_label(claim("rumor_leak_social"), 1)[0] == "unverified"
    assert initial_label(claim("anonymous_sources"), 1)[0] == "reported"


def test_denial_is_disputed():
    assert initial_label(claim("denial_or_correction"), 1)[0] == "disputed"


def test_routine_fact_not_in_doubt_is_labeled_but_not_tracked():
    c = {**claim("on_record_reporting"), "in_doubt": False}
    label, status, _ = initial_label(c, 1, "Reuters")
    assert (label, status) == ("reported", "not_tracked")


def test_plans_and_bragging_are_tracked_even_if_marked_not_in_doubt():
    assert initial_label({**claim("official_source", "future", claimant="Meta"), "in_doubt": False}, 1)[1] == "open"
    assert initial_label({**claim("official_source", "performance", True, "Meta"), "in_doubt": False}, 1)[1] == "open"


def test_outlet_citing_its_own_analysis_is_not_a_relay():
    c = claim("repeats_other_outlet", claimant="The Information")
    assert "Relayed" not in initial_label(c, 1, "The Information")[2]
