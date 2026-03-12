"""Ensure Garmin Daily and Meals databases exist (create only if missing), then run sync_garmin and sync_meals. When not RUN_ONCE, runs every SYNC_INTERVAL_MINUTES (default 60)."""

import os
import time
from datetime import datetime, timedelta

from dotenv import load_dotenv

from notion_db import get_or_create_garmin_db, get_or_create_meals_db
from sync_garmin import main as sync_garmin_main
from sync_meals import main as sync_meals_main

load_dotenv()

DEFAULT_SYNC_INTERVAL_MINUTES = 60


def _run_meal_analysis() -> bool:
    """True if RUN_MEAL_ANALYSIS is set to a truthy value (e.g. True, 1, yes)."""
    v = os.environ.get("RUN_MEAL_ANALYSIS", "").strip().lower()
    return v in ("true", "1", "yes", "on")


def main():
    notion_key = os.environ.get("NOTION_API_KEY", "").strip()
    page_id = os.environ.get("NOTION_PAGE_ID", "").strip()
    if not notion_key or not page_id:
        print("Set NOTION_API_KEY and NOTION_PAGE_ID in .env")
        return

    print("Ensuring databases exist…")
    get_or_create_garmin_db(notion_key, page_id)
    if _run_meal_analysis():
        get_or_create_meals_db(notion_key, page_id)
    print("Running Garmin sync…")
    sync_garmin_main()
    if _run_meal_analysis():
        print("Running Meals analysis…")
        sync_meals_main()
    else:
        print("Meals analysis skipped (RUN_MEAL_ANALYSIS not enabled).")


def _sync_interval_seconds() -> float:
    """Seconds to sleep between runs (from SYNC_INTERVAL_MINUTES, default 60). Clamped to 1–1440 minutes."""
    raw = os.environ.get("SYNC_INTERVAL_MINUTES", "").strip() or str(DEFAULT_SYNC_INTERVAL_MINUTES)
    try:
        minutes = max(1, min(1440, int(raw)))
    except ValueError:
        minutes = DEFAULT_SYNC_INTERVAL_MINUTES
    return minutes * 60.0


if __name__ == "__main__":
    main()
    if os.environ.get("RUN_ONCE", "").strip().lower() in ("1", "true", "yes", "on"):
        exit(0)
    while True:
        secs = _sync_interval_seconds()
        next_run = datetime.now() + timedelta(seconds=secs)
        print(f"Next run at {next_run.strftime('%H:%M')} (sleeping {int(secs)}s)")
        time.sleep(secs)
        main()
