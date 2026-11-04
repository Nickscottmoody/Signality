"""The always-on loop: check the news, wait, repeat.

Run it in the foreground (Ctrl+C to stop):
    ./.venv/bin/python -m signality.agent
Run a single round and exit:
    ./.venv/bin/python -m signality.agent --once

On a Mac it's kept running in the background by launchd
(see scripts/install_mac_service.sh).
"""
import logging
import sys
import time
from logging.handlers import RotatingFileHandler

from . import ai, db, delivery, fetcher, triage, validity
from .settings import ROOT, load_config

log = logging.getLogger("signality")


def setup_logging(log_path):
    """Log to the screen and to a file that's capped at ~3 MB total."""
    path = ROOT / log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    file_handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2)
    screen_handler = logging.StreamHandler(sys.stdout)
    for handler in (file_handler, screen_handler):
        handler.setFormatter(fmt)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def one_round():
    """Run the fetcher once and log a one-line summary. Never raises."""
    try:
        s = fetcher.run_once(load_config())  # reread config so edits apply next round
        log.info(
            "fetch: %d/%d sources ok | %d new articles (%d new stories, %d grouped) | "
            "%d duplicates | %d not AI | %d too old",
            s["sources_ok"], s["sources_ok"] + s["sources_failed"], s["new_articles"],
            s["new_stories"], s["grouped_articles"], s["duplicates_removed"],
            s["filtered_non_ai"], s["too_old"],
        )
        for error in s["errors"]:
            log.warning("source failed: %s", error)
    except Exception:
        # One bad round (no internet, a broken feed) must never stop the agent.
        log.exception("fetch round crashed; will try again next round")

    cfg = load_config()
    if not cfg["triage"]["enabled"]:
        return
    try:
        conn = db.connect(cfg["storage"]["db_path"])
        t = triage.run(conn, cfg)
        relabeled = validity.refresh_recent(conn, cfg)  # free: rules only, no AI
        budget = ai.budget_status(conn, cfg)
        conn.close()
        log.info(
            "triage: %d scored, %d merged as duplicates, %d failed, %d too old, %d relabeled | "
            "$%.4f this round | $%.2f of $%s this month",
            t["triaged"], t["merged"], t["failed"], t["too_old"], relabeled, t["cost_usd"],
            budget["spent"], budget["cap"],
        )
    except ai.BudgetExceeded as e:
        log.warning("triage skipped: %s", e)
    except Exception:
        log.exception("triage round crashed; will try again next round")

    if not cfg["delivery"]["enabled"]:
        return
    try:
        conn = db.connect(cfg["storage"]["db_path"])
        d = delivery.run(conn, cfg)
        conn.close()
        if any(d.values()):
            log.info("delivery: %d alerts, %d silent, %d in digest%s", d["alert"], d["silent"],
                     d["digest_items"], f", budget notice: {d['budget_notice']}" if d["budget_notice"] else "")
    except Exception:
        log.exception("delivery round crashed; will try again next round")


def main():
    setup_logging(load_config()["storage"]["log_path"])
    if "--once" in sys.argv:
        one_round()
        return
    log.info("Signality agent started")
    while True:
        started = time.monotonic()
        one_round()
        interval = load_config()["polling"]["interval_minutes"] * 60
        time.sleep(max(0, interval - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
