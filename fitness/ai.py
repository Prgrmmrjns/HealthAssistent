"""Mistral AI integration for food image analysis."""

import base64
import json
import re

import requests
from django.conf import settings

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"

FOOD_ANALYSIS_PROMPT = """Analyze this food image and estimate the macronutrients.

Return a JSON object with these fields:
- "description": A brief description of the food items you see
- "calories": Estimated total calories (integer)
- "protein_g": Estimated protein in grams (float, 1 decimal)
- "carbs_g": Estimated carbohydrates in grams (float, 1 decimal)
- "fat_g": Estimated fat in grams (float, 1 decimal)
- "fiber_g": Estimated dietary fiber in grams (float, 1 decimal)

Be realistic with portion sizes. Return ONLY valid JSON, no markdown."""

FOOD_TEXT_PROMPT = """The user described their meal as: "{description}"

Estimate the macronutrients for this meal.

Return a JSON object with these fields:
- "description": A brief standardized description of the food
- "calories": Estimated total calories (integer)
- "protein_g": Estimated protein in grams (float, 1 decimal)
- "carbs_g": Estimated carbohydrates in grams (float, 1 decimal)
- "fat_g": Estimated fat in grams (float, 1 decimal)
- "fiber_g": Estimated dietary fiber in grams (float, 1 decimal)

Be realistic with portion sizes. Return ONLY valid JSON, no markdown."""


def _parse_ai_response(text):
    """Extract JSON from AI response, handling markdown code blocks."""
    text = text.strip()
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        text = match.group(1)
    elif text.startswith('{'):
        pass
    else:
        match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if match:
            text = match.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def analyze_food_image(image_path):
    """Send a food image to Mistral Pixtral and get macronutrient estimates."""
    api_key = settings.MISTRAL_AI_API_KEY
    if not api_key:
        return {"error": "MISTRAL_AI_API_KEY not set"}

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    ext = str(image_path).rsplit(".", 1)[-1].lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")

    payload = {
        "model": "pixtral-12b-2409",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": FOOD_ANALYSIS_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                ],
            }
        ],
        "max_tokens": 500,
        "temperature": 0.2,
    }

    r = requests.post(
        MISTRAL_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    parsed = _parse_ai_response(text)
    if parsed:
        parsed["_raw"] = text
    return parsed or {"error": "Could not parse AI response", "_raw": text}


def analyze_food_text(description):
    """Use Mistral to estimate macros from a text description."""
    api_key = settings.MISTRAL_AI_API_KEY
    if not api_key:
        return {"error": "MISTRAL_AI_API_KEY not set"}

    payload = {
        "model": "mistral-small-latest",
        "messages": [
            {"role": "user", "content": FOOD_TEXT_PROMPT.format(description=description)},
        ],
        "max_tokens": 500,
        "temperature": 0.2,
    }

    r = requests.post(
        MISTRAL_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    parsed = _parse_ai_response(text)
    if parsed:
        parsed["_raw"] = text
    return parsed or {"error": "Could not parse AI response", "_raw": text}
