from signality.bias import summarize


def test_percentages_and_small_sample_flag():
    data = ([("center", "confirmed", "2026-11-09")] * 30 + [("center", "reported", "2026-11-09")] * 10
            + [("lean-right", "unverified", "2026-11-09")] * 2 + [("lean-right", "likely", "2026-11-09")] * 2)
    r = summarize(data)["leans"]
    assert r["center"]["n"] == 40 and round(r["center"]["strong_pct"]) == 75 and r["center"]["enough"]
    assert r["lean-right"]["strong_pct"] == 50 and r["lean-right"]["weak_pct"] == 50
    assert not r["lean-right"]["enough"]


def test_weekly_buckets():
    data = [("center", "confirmed", "2026-11-02"), ("center", "reported", "2026-11-10")]
    weeks = summarize(data)["weeks"]
    assert list(weeks) == ["2026-W45", "2026-W46"] and weeks["2026-W45"]["center"] == 100
