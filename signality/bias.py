"""Bias audit: do Signality's validity labels skew by a source's political lean?

Lean is never used to judge credibility; it is recorded only so Signality can
check itself. If stories from one lean kept getting weaker labels than another
for the same kind of reporting, that would be a red flag worth investigating.

    ./.venv/bin/python -m signality.bias

Notes on reading it:
- Primary sources (the organization itself) are left out: they're confirmed by
  definition and would distort the comparison.
- Small groups are flagged; a few stories can swing a percentage a lot.
- A gap is a prompt to look closer, not proof of bias: outlets differ in what
  they cover (e.g., wire services relay more official statements).
"""
from collections import defaultdict
from datetime import date

from . import db
from .settings import load_config

STRONG = {"confirmed", "likely"}      # well-supported
WEAK = {"unverified", "disputed"}     # shaky
MIN_SAMPLE = 30


def rows(conn):
    """(lean, current label, ISO week) for every scored AI story from a news outlet (not opinion)."""
    return conn.execute(
        """
        SELECT src.lean, v.label, s.first_seen_at
        FROM story_triage t
        JOIN stories s ON s.id = t.story_id
        JOIN articles a ON a.id = t.article_id
        JOIN sources src ON src.id = a.source_id
        JOIN story_validity v ON v.id = (SELECT MAX(id) FROM story_validity WHERE story_id = t.story_id)
        WHERE t.purpose = 'live' AND t.ai_related = 1 AND src.type != 'primary' AND v.label != 'opinion'
        """
    ).fetchall()


def _week(iso):
    y, w, _ = date.fromisoformat(iso[:10]).isocalendar()
    return f"{y}-W{w:02d}"


def summarize(data):
    """{lean: {n, strong %, weak %}} plus {week: {lean: strong %}} from (lean, label, first_seen) rows."""
    by_lean = defaultdict(lambda: {"n": 0, "strong": 0, "weak": 0})
    by_week = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # week -> lean -> [strong, n]
    for lean, label, seen in data:
        g = by_lean[lean]
        g["n"] += 1
        g["strong"] += label in STRONG
        g["weak"] += label in WEAK
        w = by_week[_week(seen)][lean]
        w[0] += label in STRONG
        w[1] += 1
    leans = {
        lean: {"n": g["n"], "strong_pct": 100 * g["strong"] / g["n"], "weak_pct": 100 * g["weak"] / g["n"],
               "enough": g["n"] >= MIN_SAMPLE}
        for lean, g in by_lean.items()
    }
    weeks = {wk: {lean: 100 * s / n for lean, (s, n) in per.items()} for wk, per in sorted(by_week.items())}
    return {"leans": leans, "weeks": weeks}


ORDER = ["left", "lean-left", "center", "lean-right", "right", "unrated"]


def report(conn):
    result = summarize(rows(conn))
    leans = result["leans"]
    out = ["Bias audit: validity labels by source lean (news outlets only)", "",
           f"  {'lean':<11}{'stories':>8}{'✅/🟢 strong':>14}{'🟠/🔴 weak':>12}"]
    for lean in sorted(leans, key=lambda x: ORDER.index(x) if x in ORDER else 99):
        g = leans[lean]
        flag = "" if g["enough"] else f"   (under {MIN_SAMPLE}: too few to judge)"
        out.append(f"  {lean:<11}{g['n']:>8}{g['strong_pct']:>13.0f}%{g['weak_pct']:>11.0f}%{flag}")
    if result["weeks"]:
        out += ["", "  share of ✅/🟢 labels by week:"]
        for wk, per in result["weeks"].items():
            out.append(f"  {wk}  " + "  ".join(f"{lean} {pct:.0f}%" for lean, pct in sorted(per.items())))
    return "\n".join(out)


def main():
    cfg = load_config()
    print(report(db.connect(cfg["storage"]["db_path"])))


if __name__ == "__main__":
    main()
