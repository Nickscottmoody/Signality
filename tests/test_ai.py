import sqlite3

import pytest

from signality import ai, db

CFG = {
    "budget": {"monthly_usd_cap": 10, "warn_at_percent": 80},
    "models": {
        "bulk": "claude-haiku-5-5",
        "effort": {"bulk": "low"},
        "max_output_tokens": 100,
        "prices_per_million_usd": {
            "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_write": 0.125, "cache_read": 0.01},
        },
    },
}


def memory_db():
    conn = sqlite3.connect(":memory:")
    db.migrate(conn)
    return conn


def spend(conn, dollars):
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0}
    ai._record(conn, "test", "claude-haiku-5-5", None, usage, dollars, ok=True)


def test_cost_matches_published_prices():
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000,
             "cache_write_tokens": 0, "cache_read_tokens": 1_000_000}
    assert ai.cost_usd(CFG, "claude-haiku-5-5", usage) == pytest.approx(0.10 + 0.50 + 0.01)


def test_budget_warns_at_80_percent():
    conn = memory_db()
    spend(conn, 7.99)
    assert not ai.budget_status(conn, CFG)["warn"]
    spend(conn, 0.01)
    status = ai.budget_status(conn, CFG)
    assert status["warn"] and not status["over"]


def test_no_call_is_made_once_budget_is_reached(monkeypatch):
    conn = memory_db()
    spend(conn, 10.00)

    def must_not_be_called():
        raise AssertionError("Claude was called despite the budget being reached")

    monkeypatch.setattr(ai, "client", must_not_be_called)
    with pytest.raises(ai.BudgetExceeded):
        ai.ask_json(conn, CFG, task="t", role="bulk", system="s", prompt="p", schema={})
