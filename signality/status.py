"""A quick health and cost check.

    ./.venv/bin/python -m signality.status
"""
import calendar
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import ai, db, validity
from .settings import load_config


def _ago(iso):
    if not iso:
        return "never"
    minutes = (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() / 60
    return f"{minutes:.0f} min ago" if minutes < 120 else f"{minutes / 60:.1f} hours ago"


def report(conn, cfg):
    tz = ZoneInfo(cfg["digest"]["timezone"])
    now = datetime.now(tz)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).isoformat(timespec="seconds")
    one = lambda sql, *args: conn.execute(sql, args).fetchone()[0]

    budget = ai.budget_status(conn, cfg)
    today_cost = one("SELECT COALESCE(SUM(cost_usd), 0) FROM ai_calls WHERE created_at >= ?", day_start)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    projected = budget["spent"] / now.day * days_in_month

    lines = [
        f"Signality status · {now:%a %b %d, %I:%M %p %Z}",
        "",
        "Agent",
        f"  last news check     {_ago(one('SELECT MAX(started_at) FROM fetch_runs'))}",
        f"  last AI call        {_ago(one('SELECT MAX(created_at) FROM ai_calls'))}",
        f"  scoring / sending   {'on' if cfg['triage']['enabled'] else 'OFF'} / {'on' if cfg['delivery']['enabled'] else 'OFF'}",
        "",
        "Today",
        f"  new stories         {one('SELECT COUNT(*) FROM stories WHERE first_seen_at >= ?', day_start)}",
        f"  scored by AI        {one('SELECT COUNT(*) FROM story_triage WHERE purpose = ? AND created_at >= ?', 'live', day_start)}",
        f"  alerts sent         {one('SELECT COUNT(*) FROM deliveries WHERE kind = ? AND sent_at >= ?', 'alert', day_start)}"
        f" (limit {cfg['importance']['alert_cap_per_day']})",
        f"  digest sent         {'yes' if one('SELECT COUNT(*) FROM deliveries WHERE kind = ? AND sent_at >= ?', 'digest', day_start) else 'not yet'}"
        f" (due {cfg['digest']['send_hour']}:00)",
        "",
        "AI spending",
        f"  today               ${today_cost:.3f}",
        f"  this month          ${budget['spent']:.2f} of ${budget['cap']} ({budget['percent']:.1f}%)",
        f"  month at this pace  ${projected:.2f}",
        "",
        "All time (portfolio metrics)",
        f"  articles collected  {one('SELECT COUNT(*) FROM articles')}",
        f"  stories scored      {one('SELECT COUNT(*) FROM story_triage WHERE purpose = ?', 'live')}",
        f"  duplicates caught   {one('SELECT COUNT(*) FROM stories WHERE article_count > 1')} grouped stories,"
        f" {one('SELECT COUNT(*) FROM stories WHERE status = ?', 'merged')} reworded merges",
        f"  sent                {one('SELECT COUNT(*) FROM deliveries WHERE kind = ?', 'alert')} alerts,"
        f" {one('SELECT COUNT(*) FROM deliveries WHERE kind = ?', 'silent')} silent,"
        f" {one('SELECT COUNT(DISTINCT local_date) FROM deliveries WHERE kind = ?', 'digest')} digests",
    ]
    labels = dict(conn.execute(
        "SELECT label, COUNT(*) FROM story_validity WHERE id IN (SELECT MAX(id) FROM story_validity GROUP BY story_id) "
        "GROUP BY label"
    ).fetchall())
    if labels:
        lines.append("  validity labels     " + "  ".join(f"{validity.LABELS[k].split()[0]} {v}" for k, v in labels.items()))
    return "\n".join(lines)


def main():
    cfg = load_config()
    print(report(db.connect(cfg["storage"]["db_path"]), cfg))


if __name__ == "__main__":
    main()
