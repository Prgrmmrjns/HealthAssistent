"""Ensure Garmin Daily and Meals databases exist (create only if missing), then run sync_garmin and sync_meals.

This file also contains the Notion database helper functions (previously in notion_db.py).

When not RUN_ONCE, runs every SYNC_INTERVAL_MINUTES.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

from params import RUN_MEAL_ANALYSIS, SYNC_INTERVAL_MINUTES

load_dotenv()

GARMIN_DB_TITLE = "📊 Garmin Daily"
MEALS_DB_TITLE = "🍽️ Meals"
GARMIN_NUMBER_KEYS = (
    "steps", "total_calories", "active_calories", "resting_hr", "avg_stress",
    "body_battery_high", "body_battery_low", "intensity_minutes",
    "sleep_hours", "hrv", "weight_kg",
)


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }


def _norm_id(val: str | None) -> str:
    return (val or "").replace("-", "").strip()


def _raise_for_status_with_body(r: requests.Response) -> None:
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        try:
            body = r.json()
        except Exception:
            body = (getattr(r, "text", "") or "").strip()[:2000]
        if body:
            raise requests.HTTPError(f"{e} – response: {body}", response=r) from None
        raise


def _validate_database_id(api_key: str, database_id: str) -> str | None:
    database_id = _norm_id(database_id)
    if not database_id:
        return None
    r = requests.get(
        f"https://api.notion.com/v1/databases/{database_id}",
        headers=_headers(api_key),
        timeout=30,
    )
    return database_id if r.status_code == 200 else None


def _env_database_id(api_key: str, env_var: str) -> str | None:
    raw = os.environ.get(env_var, "")
    if not raw:
        return None
    return _validate_database_id(api_key, raw)


def _databases_under_page(api_key: str, page_id: str) -> dict[str, str]:
    page_id = _norm_id(page_id)
    out: dict[str, str] = {}
    r = requests.post(
        "https://api.notion.com/v1/search",
        json={"filter": {"property": "object", "value": "database"}, "page_size": 100},
        headers=_headers(api_key),
        timeout=30,
    )
    _raise_for_status_with_body(r)
    for item in r.json().get("results", []):
        if item.get("object") != "database":
            continue
        parent = item.get("parent", {})
        if parent.get("type") != "page_id" or (parent.get("page_id") or "").replace("-", "").strip() != page_id:
            continue
        title_arr = item.get("title") or []
        name = (title_arr[0].get("plain_text") or "").strip() if title_arr else ""
        if name:
            out[name] = item["id"]
    return out


def _garmin_schema() -> dict:
    props = {"Date": {"title": {}}, "date": {"date": {}}}
    for k in GARMIN_NUMBER_KEYS:
        props[k] = {"number": {}}
    return props


def _meals_schema() -> dict:
    return {
        "Intake": {"title": {}},
        "Time": {"date": {}},
        "Image": {"files": {}},
        "Meal components": {"multi_select": {"options": []}},
        "kcals": {"number": {}},
        "Proteins": {"number": {}},
        "Fats": {"number": {}},
        "Carbohydrates": {"number": {}},
        "Sugars": {"number": {}},
        "Dietary Fibers": {"number": {}},
    }


def _create_database(api_key: str, page_id: str, title: str, properties: dict) -> str:
    r = requests.post(
        "https://api.notion.com/v1/databases",
        json={
            "parent": {"type": "page_id", "page_id": page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": properties,
        },
        headers=_headers(api_key),
        timeout=30,
    )
    _raise_for_status_with_body(r)
    return r.json()["id"]


def get_or_create_garmin_db(api_key: str, page_id: str) -> str:
    env_id = _env_database_id(api_key, "GARMIN_DB_ID")
    if env_id:
        return env_id
    title_to_id = _databases_under_page(api_key, page_id)
    db_id = title_to_id.get(GARMIN_DB_TITLE) or title_to_id.get("Garmin Daily")
    if not db_id:
        db_id = _create_database(api_key, page_id, GARMIN_DB_TITLE, _garmin_schema())
        print(f"  Created database: {GARMIN_DB_TITLE}")
    return db_id


def get_or_create_meals_db(api_key: str, page_id: str) -> str:
    env_id = _env_database_id(api_key, "MEALS_DB_ID")
    if env_id:
        return env_id
    title_to_id = _databases_under_page(api_key, page_id)
    db_id = title_to_id.get(MEALS_DB_TITLE) or title_to_id.get("Meals")
    if not db_id:
        db_id = _create_database(api_key, page_id, MEALS_DB_TITLE, _meals_schema())
        print(f"  Created database: {MEALS_DB_TITLE}")
    return db_id


def get_garmin_db_id(api_key: str, page_id: str) -> str | None:
    env_id = _env_database_id(api_key, "GARMIN_DB_ID")
    if env_id:
        return env_id
    title_to_id = _databases_under_page(api_key, page_id)
    return title_to_id.get(GARMIN_DB_TITLE) or title_to_id.get("Garmin Daily")


def get_meals_db_id(api_key: str, page_id: str) -> str | None:
    env_id = _env_database_id(api_key, "MEALS_DB_ID")
    if env_id:
        return env_id
    title_to_id = _databases_under_page(api_key, page_id)
    return title_to_id.get(MEALS_DB_TITLE) or title_to_id.get("Meals")


def get_database_property_names(api_key: str, database_id: str) -> set[str]:
    r = requests.get(
        f"https://api.notion.com/v1/databases/{database_id}",
        headers=_headers(api_key),
        timeout=30,
    )
    _raise_for_status_with_body(r)
    return set((r.json().get("properties") or {}).keys())


def get_database_property_types(api_key: str, database_id: str) -> dict[str, str]:
    r = requests.get(
        f"https://api.notion.com/v1/databases/{database_id}",
        headers=_headers(api_key),
        timeout=30,
    )
    _raise_for_status_with_body(r)
    props = (r.json().get("properties") or {})
    out: dict[str, str] = {}
    for name, meta in props.items():
        if isinstance(meta, dict) and isinstance(meta.get("type"), str):
            out[name] = meta["type"]
    return out


def main():
    notion_key = os.environ.get("NOTION_API_KEY", "").strip()
    page_id = os.environ.get("NOTION_PAGE_ID", "").strip()
    if not notion_key:
        print("Set NOTION_API_KEY in .env")
        return

    # If DB IDs are explicitly provided, we can run without creating/searching under a parent page.
    has_direct_db_ids = bool(os.environ.get("GARMIN_DB_ID", "").strip()) and (
        (not RUN_MEAL_ANALYSIS) or bool(os.environ.get("MEALS_DB_ID", "").strip())
    )
    if not page_id and not has_direct_db_ids:
        print("Set NOTION_PAGE_ID in .env (or set GARMIN_DB_ID/MEALS_DB_ID to skip creation).")
        return

    print("Ensuring databases exist…")
    if page_id:
        get_or_create_garmin_db(notion_key, page_id)
    if RUN_MEAL_ANALYSIS:
        if page_id:
            get_or_create_meals_db(notion_key, page_id)
    print("Running Garmin sync…")
    from sync_garmin import main as sync_garmin_main

    sync_garmin_main()
    if RUN_MEAL_ANALYSIS:
        print("Running Meals analysis…")
        from sync_meals import main as sync_meals_main

        sync_meals_main()
    else:
        print("Meals analysis skipped (RUN_MEAL_ANALYSIS is False in params.py).")


def _sync_interval_seconds() -> float:
    """Seconds to sleep between runs, based on SYNC_INTERVAL_MINUTES in params.py (clamped to 1–1440 minutes)."""
    minutes = SYNC_INTERVAL_MINUTES
    if not isinstance(minutes, int):
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            minutes = 60
    minutes = max(1, min(1440, minutes))
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
