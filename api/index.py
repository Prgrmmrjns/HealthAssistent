"""
Vercel Python entrypoint.

Vercel detects Python functions in the `api/` directory. This file exposes a
WSGI-compatible `app` callable so deployments succeed.
"""

from __future__ import annotations

import json
import os
from urllib.parse import parse_qs


def _json(start_response, status: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


def app(environ, start_response):
    """
    GET /api
      -> health/info

    GET /api?run=1
      -> runs one sync pass (equivalent to RUN_ONCE=1 python main.py)
    """

    qs = parse_qs(environ.get("QUERY_STRING", "") or "")
    run = (qs.get("run", ["0"])[0] or "").strip().lower() in ("1", "true", "yes", "on")

    if not run:
        return _json(
            start_response,
            "200 OK",
            {
                "ok": True,
                "service": "garmin-notion-connect",
                "hint": "Add ?run=1 to trigger a one-off sync.",
            },
        )

    os.environ["RUN_ONCE"] = "1"
    try:
        import main as sync_main

        sync_main.main()
        return _json(start_response, "200 OK", {"ok": True, "ran": True})
    except Exception as e:
        return _json(start_response, "500 Internal Server Error", {"ok": False, "error": str(e)})

