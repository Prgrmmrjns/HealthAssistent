"""Sync Garmin daily metrics to Notion (Garmin Daily DB). Run main.py first to create the database."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import garminconnect
import requests
from dotenv import load_dotenv

from notion_db import GARMIN_NUMBER_KEYS, _headers, get_garmin_db_id

load_dotenv()


def fetch_daily_stats(garmin, date_str: str) -> dict:
    def num(v, cast=int):
        x = cast(v)
        return None if cast == float and x != x else x

    out = {}
    summary = garmin.get_stats(date_str)
    out["steps"] = num(summary.get("totalSteps"))
    out["total_calories"] = num(summary.get("totalKilocalories"))
    out["active_calories"] = num(summary.get("activeKilocalories"))
    out["resting_hr"] = num(summary.get("restingHeartRate"))
    out["avg_stress"] = num(summary.get("averageStressLevel"))
    out["body_battery_high"] = num(summary.get("bodyBatteryChargedValue"))
    out["body_battery_low"] = num(summary.get("bodyBatteryDrainedValue"))
    mod = num(summary.get("moderateIntensityMinutes")) or 0
    vig = num(summary.get("vigorousIntensityMinutes")) or 0
    out["intensity_minutes"] = mod + vig
    sleep = garmin.get_sleep_data(date_str)
    secs = sleep.get("dailySleepDTO", {}).get("sleepTimeSeconds")
    out["sleep_hours"] = round(secs / 3600, 1) if secs else None
    hrv = garmin.get_hrv_data(date_str)
    s = hrv.get("hrvSummary", {}) if hrv else {}
    out["hrv"] = num(s.get("weeklyAvg") or s.get("lastNightAvg"), float)
    body = garmin.get_body_composition(date_str)
    out["weight_kg"] = body.get("weight") if body else None
    return out


def _garmin_props(date_str: str, stats: dict, with_date: bool) -> dict:
    p = {}
    if with_date:
        p["Date"] = {"title": [{"text": {"content": date_str}}]}
        p["date"] = {"date": {"start": date_str}}
    for k in GARMIN_NUMBER_KEYS:
        v = stats.get(k)
        if v is None:
            continue
        p[k] = {"number": v if isinstance(v, (int, float)) else float(v)}
    return p


def _query_page_by_date(api_key: str, database_id: str, date_str: str) -> str | None:
    r = requests.post(
        f"https://api.notion.com/v1/databases/{database_id}/query",
        json={"filter": {"property": "date", "date": {"equals": date_str}}, "page_size": 1},
        headers=_headers(api_key),
        timeout=30,
    )
    r.raise_for_status()
    results = r.json().get("results") or []
    return results[0]["id"] if results else None


def _create_page(api_key: str, database_id: str, date_str: str, stats: dict):
    requests.post(
        "https://api.notion.com/v1/pages",
        json={
            "parent": {"database_id": database_id},
            "properties": _garmin_props(date_str, stats, True),
        },
        headers=_headers(api_key),
        timeout=30,
    ).raise_for_status()


def _update_page(api_key: str, page_id: str, stats: dict):
    p = _garmin_props("", stats, False)
    if p:
        requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            json={"properties": p},
            headers=_headers(api_key),
            timeout=30,
        ).raise_for_status()


def main():
    email = os.environ.get("GARMIN_EMAIL", "").strip()
    password = os.environ.get("GARMIN_PASSWORD", "").strip()
    notion_key = os.environ.get("NOTION_API_KEY", "").strip()
    page_id = os.environ.get("NOTION_PAGE_ID", "").strip()

    database_id = get_garmin_db_id(notion_key, page_id)
    if not database_id:
        print("Garmin Daily database not found. Run main.py first to create databases.")
        return

    requests.post(
        f"https://api.notion.com/v1/databases/{database_id}/query",
        json={"page_size": 1},
        headers=_headers(notion_key),
        timeout=30,
    ).raise_for_status()

    print("Logging in to Garmin Connect…")
    garmin = garminconnect.Garmin(email=email, password=password)
    garmin.login()

    # Only sync today's date; no historical backfill here.
    today = datetime.now().date()
    ds = today.strftime("%Y-%m-%d")
    stats = fetch_daily_stats(garmin, ds)
    if not any(v is not None for v in stats.values()):
        print(f"No data for {ds}, nothing to write.")
        return

    page_id_res = _query_page_by_date(notion_key, database_id, ds)
    if page_id_res:
        _update_page(notion_key, page_id_res, stats)
        print(f"Updated {ds}")
    else:
        _create_page(notion_key, database_id, ds, stats)
        print(f"Created {ds}")


if __name__ == "__main__":
    main()
