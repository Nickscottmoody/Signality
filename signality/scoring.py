"""Turns the AI's 1-5 factor ratings into a 0-100 importance score.

The model only rates; this code does the math, using the weights in
config.yaml, so the formula is visible, testable, and easy to change.
"""
FACTORS = ("impact", "breadth", "urgency", "novelty")


def base_score(ratings, weights):
    """Weighted 0-100 score from four 1-5 ratings (1 -> 0, 5 -> 100)."""
    total = sum(weights[f] for f in FACTORS)
    return sum(weights[f] * (ratings[f] - 1) / 4 * 100 for f in FACTORS) / total


def topic_multiplier(topics, topic_weights):
    """The largest weight among the story's topics (1.0 if none are favored)."""
    return max([topic_weights.get(t, 1.0) for t in topics] + [1.0])


def importance(ratings, topics, cfg):
    """(base score, topic multiplier, final 0-100 importance)."""
    base = base_score(ratings, cfg["importance"]["weights"])
    mult = topic_multiplier(topics, cfg["topics"])
    return base, mult, min(100, round(base * mult))


def tier(score, cfg):
    """Which delivery tier a score falls in: alert | silent | digest | stored."""
    t = cfg["importance"]["thresholds"]
    if score >= t["alert"]:
        return "alert"
    if score >= t["silent"]:
        return "silent"
    if score >= t["digest"]:
        return "digest"
    return "stored"
