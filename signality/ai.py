"""Every call to Claude goes through here, so every call is priced and logged.

- Picks the model and effort for a role ('bulk', 'high_stakes', 'deep') from config.
- Asks for JSON that matches a schema, so replies are always machine-readable.
- Caches the instructions (system prompt) so repeated calls reread them cheaply.
- Records tokens and dollars in the ai_calls table: the cost meter.
- Refuses to call at all once this month's spending reaches the budget cap.
"""
import json
from datetime import datetime, timezone

import anthropic

from . import db
from .settings import secret


class BudgetExceeded(Exception):
    """This month's AI spending has reached budget.monthly_usd_cap."""


class AIError(Exception):
    """Claude's reply couldn't be used (refused, cut off, or not valid JSON)."""


_client = None


def client():
    global _client
    if _client is None:
        key = secret("ANTHROPIC_API_KEY")
        if not key:
            raise AIError("ANTHROPIC_API_KEY is missing from .env")
        _client = anthropic.Anthropic(api_key=key, timeout=120.0)
    return _client


def cost_usd(cfg, model, usage):
    """Dollar cost of one call, from its token counts and the prices in config."""
    price = cfg["models"]["prices_per_million_usd"][model]
    return (
        usage["input_tokens"] * price["input"]
        + usage["output_tokens"] * price["output"]
        + usage["cache_write_tokens"] * price["cache_write"]
        + usage["cache_read_tokens"] * price["cache_read"]
    ) / 1_000_000


def month_spend(conn):
    """Total dollars spent on Claude so far this calendar month (UTC)."""
    month_start = datetime.now(timezone.utc).strftime("%Y-%m-01")
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM ai_calls WHERE created_at >= ?", (month_start,)
    ).fetchone()
    return row[0]


def budget_status(conn, cfg):
    """How this month's spending compares to the cap."""
    cap = cfg["budget"]["monthly_usd_cap"]
    spent = month_spend(conn)
    return {
        "spent": spent,
        "cap": cap,
        "percent": 100 * spent / cap if cap else 0,
        "warn": spent >= cap * cfg["budget"]["warn_at_percent"] / 100,
        "over": spent >= cap,
    }


def _record(conn, task, model, story_id, usage, cost, ok, error=None, request_id=None):
    conn.execute(
        """
        INSERT INTO ai_calls (created_at, task, model, story_id, input_tokens, output_tokens,
                              cache_write_tokens, cache_read_tokens, cost_usd, ok, error, request_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (db.utcnow(), task, model, story_id, usage["input_tokens"], usage["output_tokens"],
         usage["cache_write_tokens"], usage["cache_read_tokens"], cost, int(ok), error, request_id),
    )
    conn.commit()


def ask_json(conn, cfg, *, task, role, system, prompt, schema, story_id=None, model=None):
    """Ask Claude for a JSON reply that matches `schema`. Returns (data, cost_usd).

    `role` picks the model and effort from config ('bulk', 'high_stakes', 'deep').
    Pass `model` to override the model (used by the side-by-side comparisons).
    """
    if budget_status(conn, cfg)["over"]:
        raise BudgetExceeded(f"monthly cap of ${cfg['budget']['monthly_usd_cap']} reached")

    model = model or cfg["models"][role]
    effort = cfg["models"]["effort"][role]
    empty = {"input_tokens": 0, "output_tokens": 0, "cache_write_tokens": 0, "cache_read_tokens": 0}

    try:
        response = client().messages.create(
            model=model,
            max_tokens=cfg["models"]["max_output_tokens"],
            # The instructions are identical on every call, so cache them.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        )
    except anthropic.APIError as e:
        _record(conn, task, model, story_id, empty, 0.0, ok=False, error=f"{type(e).__name__}: {e}"[:500])
        raise

    u = response.usage
    usage = {
        "input_tokens": u.input_tokens or 0,
        "output_tokens": u.output_tokens or 0,
        "cache_write_tokens": u.cache_creation_input_tokens or 0,
        "cache_read_tokens": u.cache_read_input_tokens or 0,
    }
    cost = cost_usd(cfg, model, usage)
    request_id = response._request_id

    problem = None
    if response.stop_reason == "refusal":
        problem = "Claude declined this request"
    elif response.stop_reason == "max_tokens":
        problem = "reply was cut off (raise models.max_output_tokens)"
    else:
        text = next((b.text for b in response.content if b.type == "text"), None)
        try:
            data = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            problem = "reply was not valid JSON"

    _record(conn, task, model, story_id, usage, cost, ok=problem is None,
            error=problem, request_id=request_id)
    if problem:
        raise AIError(problem)
    return data, cost
