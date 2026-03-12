"""Notion database creation and lookup. Used by main.py (create) and sync scripts (lookup)."""

from __future__ import annotations

import requests

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


def _databases_under_page(api_key: str, page_id: str) -> dict[str, str]:
    page_id = (page_id or "").replace("-", "").strip()
    out = {}
    r = requests.post(
        "https://api.notion.com/v1/search",
        json={"filter": {"property": "object", "value": "database"}, "page_size": 100},
        headers=_headers(api_key),
        timeout=30,
    )
    r.raise_for_status()
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
        "Meal components": {"rich_text": {}},
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
    r.raise_for_status()
    return r.json()["id"]


def get_or_create_garmin_db(api_key: str, page_id: str) -> str:
    """Ensure Garmin Daily DB exists; create only if missing. Return database_id."""
    title_to_id = _databases_under_page(api_key, page_id)
    db_id = title_to_id.get(GARMIN_DB_TITLE) or title_to_id.get("Garmin Daily")
    if not db_id:
        db_id = _create_database(api_key, page_id, GARMIN_DB_TITLE, _garmin_schema())
        print(f"  Created database: {GARMIN_DB_TITLE}")
    return db_id


def get_or_create_meals_db(api_key: str, page_id: str) -> str:
    """Ensure Meals DB exists; create only if missing. Return database_id."""
    title_to_id = _databases_under_page(api_key, page_id)
    db_id = title_to_id.get(MEALS_DB_TITLE) or title_to_id.get("Meals")
    if not db_id:
        db_id = _create_database(api_key, page_id, MEALS_DB_TITLE, _meals_schema())
        print(f"  Created database: {MEALS_DB_TITLE}")
    return db_id


def get_garmin_db_id(api_key: str, page_id: str) -> str | None:
    """Return Garmin Daily database_id if it exists under the page; else None."""
    title_to_id = _databases_under_page(api_key, page_id)
    return title_to_id.get(GARMIN_DB_TITLE) or title_to_id.get("Garmin Daily")


def get_meals_db_id(api_key: str, page_id: str) -> str | None:
    """Return Meals database_id if it exists under the page; else None."""
    title_to_id = _databases_under_page(api_key, page_id)
    return title_to_id.get(MEALS_DB_TITLE) or title_to_id.get("Meals")


def get_database_property_names(api_key: str, database_id: str) -> set[str]:
    """Return the set of property names (keys) in the database schema."""
    r = requests.get(
        f"https://api.notion.com/v1/databases/{database_id}",
        headers=_headers(api_key),
        timeout=30,
    )
    r.raise_for_status()
    return set((r.json().get("properties") or {}).keys())
