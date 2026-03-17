"""Sync Garmin daily metrics to Notion (Garmin Daily DB). Run main.py first to create the database."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import garminconnect
import requests
from dotenv import load_dotenv

from main import GARMIN_NUMBER_KEYS, _headers, get_garmin_db_id
from params import SYNC_PRIOR_GARMIN_DAYS

load_dotenv()


def fetch_daily_stats(garmin, date_str: str) -> dict:
    def num(v, cast=int):
        if v is None:
            return None
        x = cast(v)
        return None if cast == float and x != x else x

    out = {}
    summary = garmin.get_stats(date_str)
    # Some metrics are not reliably present in get_stats() for all accounts/devices.
    # Fall back to dedicated endpoints where possible.
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

    # Stress: try dedicated endpoint if missing.
    if out["avg_stress"] is None:
        try:
            stress = garmin.get_stress_data(date_str) or {}
            # Typical shape: {"avgStressLevel": 23, ...}
            out["avg_stress"] = num(stress.get("avgStressLevel") or stress.get("averageStressLevel"))
        except Exception:
            pass

    # Body battery: try dedicated endpoint if missing.
    if out["body_battery_high"] is None or out["body_battery_low"] is None:
        try:
            bb = garmin.get_body_battery(date_str) or {}
            # Typical shape: {"bodyBatteryHighestValue": ..., "bodyBatteryLowestValue": ...}
            out["body_battery_high"] = out["body_battery_high"] or num(
                bb.get("bodyBatteryHighestValue") or bb.get("bodyBatteryChargedValue")
            )
            out["body_battery_low"] = out["body_battery_low"] or num(
                bb.get("bodyBatteryLowestValue") or bb.get("bodyBatteryDrainedValue")
            )
        except Exception:
            pass

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


def _existing_dates_since(api_key: str, database_id: str, start_date_str: str) -> set[str]:
    """Return set of YYYY-MM-DD dates already present in the DB since start (inclusive)."""
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    payload: dict = {
        "filter": {"property": "date", "date": {"on_or_after": start_date_str}},
        "page_size": 100,
    }
    out: set[str] = set()
    while True:
        r = requests.post(url, json=payload, headers=_headers(api_key), timeout=30)
        r.raise_for_status()
        data = r.json()
        for page in data.get("results") or []:
            props = page.get("properties") or {}
            d = ((props.get("date") or {}).get("date") or {}).get("start")
            if isinstance(d, str) and len(d) >= 10:
                out.add(d[:10])
        nxt = data.get("next_cursor")
        if not nxt:
            break
        payload["start_cursor"] = nxt
    return out


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

    if not notion_key:
        print("Set NOTION_API_KEY in .env")
        return

    database_id = get_garmin_db_id(notion_key, page_id)
    if not database_id:
        print("Garmin Daily database not found. Set GARMIN_DB_ID or run main.py to create databases.")
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

    # Backfill missing prior days (create only), then sync today (update/create).
    days = SYNC_PRIOR_GARMIN_DAYS
    if not isinstance(days, int):
        try:
            days = int(days)
        except (TypeError, ValueError):
            days = 0
    days = max(0, min(365, days))

    today = datetime.now().date()
    start = today - timedelta(days=days)
    start_str = start.strftime("%Y-%m-%d")
    existing_dates = _existing_dates_since(notion_key, database_id, start_str)

    # Create missing historical days (skip existing to minimize Notion calls).
    for i in range(days):
        d = start + timedelta(days=i)
        ds = d.strftime("%Y-%m-%d")
        if ds in existing_dates:
            continue
        stats = fetch_daily_stats(garmin, ds)
        _create_page(notion_key, database_id, ds, stats)
        if any(v is not None for v in stats.values()):
            print(f"Created {ds}")
        else:
            print(f"Created {ds} (no Garmin metrics returned)")

    # Today: update if exists, else create.
    ds_today = today.strftime("%Y-%m-%d")
    stats_today = fetch_daily_stats(garmin, ds_today)
    page_id_res = _query_page_by_date(notion_key, database_id, ds_today)
    if page_id_res:
        _update_page(notion_key, page_id_res, stats_today)
        print(f"Updated {ds_today}")
    else:
        _create_page(notion_key, database_id, ds_today, stats_today)
        if any(v is not None for v in stats_today.values()):
            print(f"Created {ds_today}")
        else:
            print(f"Created {ds_today} (no Garmin metrics returned)")


if __name__ == "__main__":
    main()
