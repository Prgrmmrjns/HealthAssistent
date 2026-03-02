"""Supabase Storage helper for uploading images."""

import os
import uuid

import requests
from django.conf import settings


def _supabase_creds():
    url = getattr(settings, "SUPABASE_URL", "") or os.environ.get("SUPABASE_URL", "")
    key = getattr(settings, "SUPABASE_API_KEY", "") or os.environ.get("SUPABASE_API_KEY", "")
    return url.strip().strip('"'), key.strip().strip('"')


def upload_image(file_obj, folder="uploads") -> str:
    """
    Upload an in-memory file to Supabase Storage.
    Returns the public URL on success, or '' on failure.
    Falls back gracefully if Supabase credentials are not set.
    """
    url, key = _supabase_creds()
    if not url or not key:
        return ""

    ext = os.path.splitext(getattr(file_obj, "name", "") or "upload.jpg")[1].lower() or ".jpg"
    filename = f"{folder}/{uuid.uuid4().hex}{ext}"
    content_type = getattr(file_obj, "content_type", None) or "image/jpeg"

    try:
        # Auto-create the media bucket the first time
        _ensure_bucket(url, key)

        file_obj.seek(0)
        data = file_obj.read()
        r = requests.post(
            f"{url}/storage/v1/object/media/{filename}",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": content_type,
            },
            data=data,
            timeout=30,
        )
        if r.status_code in (200, 201):
            return f"{url}/storage/v1/object/public/media/{filename}"
        return ""
    except Exception:
        return ""


def _ensure_bucket(url, key):
    """Create the 'media' bucket if it doesn't exist yet (called once per upload)."""
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    try:
        r = requests.get(f"{url}/storage/v1/bucket/media", headers=headers, timeout=5)
        if r.status_code == 200:
            return  # already exists
        requests.post(
            f"{url}/storage/v1/bucket",
            headers=headers,
            json={"id": "media", "name": "media", "public": True},
            timeout=10,
        )
    except Exception:
        pass


def ensure_bucket_exists():
    """Create the 'media' bucket in Supabase Storage if it doesn't exist."""
    url, key = _supabase_creds()
    if not url or not key:
        return False

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    # Check if bucket exists
    r = requests.get(f"{url}/storage/v1/bucket", headers=headers, timeout=10)
    if r.ok:
        existing = [b["name"] for b in r.json()]
        if "media" in existing:
            return True

    # Create public bucket
    r = requests.post(
        f"{url}/storage/v1/bucket",
        headers=headers,
        json={"id": "media", "name": "media", "public": True},
        timeout=10,
    )
    return r.status_code in (200, 201)
