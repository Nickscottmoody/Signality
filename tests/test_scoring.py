from signality import scoring

CFG = {
    "importance": {
        "weights": {"impact": 0.35, "breadth": 0.25, "urgency": 0.20, "novelty": 0.20},
        "thresholds": {"alert": 75, "silent": 50, "digest": 25},
    },
    "topics": {"model_releases": 1.0, "jobs": 1.3, "finance_analytics": 1.3},
}


def test_all_ones_is_zero_and_all_fives_is_hundred():
    w = CFG["importance"]["weights"]
    assert scoring.base_score(dict(impact=1, breadth=1, urgency=1, novelty=1), w) == 0
    assert scoring.base_score(dict(impact=5, breadth=5, urgency=5, novelty=5), w) == 100


def test_weights_follow_config():
    w = CFG["importance"]["weights"]
    # Only impact maxed: 35% of the score.
    assert round(scoring.base_score(dict(impact=5, breadth=1, urgency=1, novelty=1), w)) == 35


def test_favored_topic_boosts_and_caps_at_100():
    ratings = dict(impact=5, breadth=5, urgency=5, novelty=4)
    _, mult, final = scoring.importance(ratings, ["jobs", "model_releases"], CFG)
    assert mult == 1.3 and final == 100


def test_unfavored_topics_get_no_boost():
    assert scoring.topic_multiplier(["model_releases", "other"], CFG["topics"]) == 1.0


def test_tiers():
    assert [scoring.tier(s, CFG) for s in (80, 75, 60, 30, 10)] == ["alert", "alert", "silent", "digest", "stored"]
