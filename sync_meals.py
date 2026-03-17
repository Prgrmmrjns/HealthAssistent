"""
Meals: analyze pages with Image but empty Intake via Mistral Pixtral; update with name, macros, kcals, Meal components.
Run main.py first to create the Meals database. Env: NOTION_API_KEY, NOTION_PAGE_ID, MISTRAL_AI_API_KEY, optional MISTRAL_MODEL.
"""

from __future__ import annotations

import base64
import json
import os
import re

import requests
from dotenv import load_dotenv

from main import _headers, get_database_property_names, get_database_property_types, get_meals_db_id
from params import MEAL_INSTRUCTIONS, model

load_dotenv()

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"

FOOD_ANALYSIS_PROMPT = """Analyze this food image and estimate the macronutrients.

Return a JSON object with these fields:
- "description": A brief description of the food items you see (use as the meal name)
- "meal_components": An array of strings listing each main component (e.g. ["plant-based protein", "rice", "steamed broccoli"])
- "calories": Estimated total calories (integer)
- "protein_g": Estimated protein in grams (float, 1 decimal)
- "carbs_g": Estimated carbohydrates in grams (float, 1 decimal)
- "fat_g": Estimated fat in grams (float, 1 decimal)
- "fiber_g": Estimated dietary fiber in grams (float, 1 decimal)

Be realistic with portion sizes.

CRITICAL DIET / USER CONSTRAINTS (HIGHEST PRIORITY):
- You MUST follow the instructions below even if the image looks ambiguous.
- If the instructions imply vegan/vegetarian constraints, do NOT label items as animal products (e.g. "chicken", "beef", "cheese", "milk", "egg").
  Instead, use plant-based alternatives in the wording (e.g. "plant-based chicken alternative", "vegan cheese", "plant milk").

User instructions:
{MEAL_INSTRUCTIONS}

Return ONLY valid JSON, no markdown."""


def _parse_ai_response(text: str) -> dict | None:
    text = (text or "").strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    elif not text.startswith("{"):
        match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if match:
            text = match.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def query_meals_to_analyze(api_key: str, database_id: str) -> list[dict]:
    """Pages where Image is not empty and Intake is empty."""
    out = []
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    payload = {
        "filter": {
            "and": [
                {"property": "Image", "files": {"is_not_empty": True}},
                {"property": "Intake", "title": {"is_empty": True}},
            ]
        },
        "page_size": 100,
    }
    while True:
        r = requests.post(url, json=payload, headers=_headers(api_key), timeout=30)
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("results") or [])
        if not data.get("next_cursor"):
            break
        payload["start_cursor"] = data["next_cursor"]
    return out


def get_image_url_from_page(api_key: str, page_id: str) -> str | None:
    r = requests.get(f"https://api.notion.com/v1/pages/{page_id}", headers=_headers(api_key), timeout=30)
    r.raise_for_status()
    files = ((r.json().get("properties") or {}).get("Image") or {}).get("files") or []
    if not files:
        return None
    first = files[0]
    if "file" in first and first["file"].get("url"):
        return first["file"]["url"]
    if "external" in first and first["external"].get("url"):
        return first["external"]["url"]
    return None


def fetch_image_as_base64(url: str, notion_api_key: str) -> tuple[str, str] | None:
    try:
        r = requests.get(url, timeout=30)
        if r.status_code in (401, 403):
            r = requests.get(
                url,
                headers={"Authorization": f"Bearer {notion_api_key}", "Notion-Version": "2022-06-28"},
                timeout=30,
            )
        r.raise_for_status()
        data = r.content
        ctype = r.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        if not ctype.startswith("image/"):
            ctype = "image/jpeg"
        return base64.b64encode(data).decode("utf-8"), ctype
    except Exception:
        return None


def analyze_food_image(image_b64: str, mime: str, mistral_key: str, model_name: str | None = None) -> dict | None:
    model_name = (model_name or model or "").strip() or "pixtral-12b-2409"
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": FOOD_ANALYSIS_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                ],
            }
        ],
        "max_tokens": 500,
    }
    r = requests.post(
        MISTRAL_API_URL,
        headers={"Authorization": f"Bearer {mistral_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    text = r.json().get("choices", [{}])[0].get("message", {}).get("content") or ""
    return _parse_ai_response(text)


def _kcals_from_macros(protein_g: float, carbs_g: float, fat_g: float, fiber_g: float) -> int:
    """4 kcal/g protein, 4 kcal/g carbs, 9 kcal/g fat, 2 kcal/g fiber."""
    return round(4 * protein_g + 4 * carbs_g + 9 * fat_g + 2 * fiber_g)


def update_meal_page(api_key: str, page_id: str, result: dict, database_id: str) -> None:
    """Update page with AI result; only send properties that exist in the database (so kcals and Meal components are set when present)."""
    description = (result.get("description") or "").strip() or "Meal"
    p = float(result.get("protein_g") or 0)
    c = float(result.get("carbs_g") or 0)
    f = float(result.get("fat_g") or 0)
    fiber = float(result.get("fiber_g") or 0)
    kcals = _kcals_from_macros(p, c, f, fiber)
    components = result.get("meal_components")
    if isinstance(components, list):
        components_list = [str(x).strip() for x in components if str(x).strip()]
    elif isinstance(components, str) and components.strip():
        # Best-effort split if the model returns a single string.
        components_list = [x.strip() for x in components.split(",") if x.strip()]
    else:
        components_list = []

    all_props = {
        "Intake": {"title": [{"type": "text", "text": {"content": description[:2000]}}]},
        "kcals": {"number": kcals},
        "Proteins": {"number": round(p, 1)},
        "Fats": {"number": round(f, 1)},
        "Carbohydrates": {"number": round(c, 1)},
        "Sugars": {"number": 0},
        "Dietary Fibers": {"number": round(fiber, 1)},
    }
    existing = get_database_property_names(api_key, database_id)
    types = get_database_property_types(api_key, database_id)

    # Meal components: write as multi_select when configured; fall back to rich_text for older DBs.
    if "Meal components" in existing and components_list:
        if types.get("Meal components") == "multi_select":
            all_props["Meal components"] = {"multi_select": [{"name": x[:100]} for x in components_list[:25]]}
        elif types.get("Meal components") == "rich_text":
            joined = ", ".join(components_list)[:2000]
            all_props["Meal components"] = {"rich_text": [{"type": "text", "text": {"content": joined}}]}

    props = {k: v for k, v in all_props.items() if v is not None and k in existing}
    if not props:
        return
    r = requests.patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=_headers(api_key),
        json={"properties": props},
        timeout=30,
    )
    r.raise_for_status()


def main():
    notion_key = os.environ.get("NOTION_API_KEY", "").strip()
    page_id = os.environ.get("NOTION_PAGE_ID", "").strip()
    mistral_key = os.environ.get("MISTRAL_AI_API_KEY", "").strip()

    if not notion_key:
        print("Set NOTION_API_KEY in .env")
        return

    db_id = get_meals_db_id(notion_key, page_id)
    if not db_id:
        print("Meals database not found. Set MEALS_DB_ID or run main.py to create databases.")
        return

    if not mistral_key:
        print("Set MISTRAL_AI_API_KEY to analyze meal images.")
        return

    pages = query_meals_to_analyze(notion_key, db_id)
    if not pages:
        print("No meals to analyze (no pages with Image set and Intake empty).")
        return

    print(f"Found {len(pages)} meal(s) to analyze.")
    for i, page in enumerate(pages):
        page_id_val = page["id"]
        img_url = get_image_url_from_page(notion_key, page_id_val)
        if not img_url:
            print(f"  [{i+1}] Skip: no image URL")
            continue
        b64_mime = fetch_image_as_base64(img_url, notion_key)
        if not b64_mime:
            print(f"  [{i+1}] Skip: could not fetch image")
            continue
        b64, mime = b64_mime
        result = analyze_food_image(b64, mime, mistral_key)
        if not result or result.get("error"):
            print(f"  [{i+1}] Skip: AI failed or could not parse")
            continue
        update_meal_page(notion_key, page_id_val, result, db_id)
        kcals = _kcals_from_macros(
            float(result.get("protein_g") or 0),
            float(result.get("carbs_g") or 0),
            float(result.get("fat_g") or 0),
            float(result.get("fiber_g") or 0),
        )
        print(f"  [{i+1}] Updated: \"{result.get('description', '')[:50]}\" – {kcals} kcal, P/C/F g")
    print("Done.")


if __name__ == "__main__":
    main()
