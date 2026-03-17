"""
Vercel Python entrypoint (FastAPI).

- Serves a small UI at `/` so you can see status and trigger runs.
- Exposes `/api/run` to manually trigger a sync.
- Exposes `/api/cron` for Vercel Cron Jobs to call periodically.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI()

# Best-effort in-memory status (serverless instances are ephemeral).
_LAST_RUN_UTC: datetime | None = None
_LAST_RESULT: dict | None = None
_RUNNING: bool = False


def _interval_minutes() -> int:
    raw = (os.environ.get("SYNC_INTERVAL_MINUTES") or "").strip()
    if raw:
        try:
            return max(1, min(1440, int(raw)))
        except ValueError:
            pass
    return 30


def _next_run_utc(now: datetime) -> datetime:
    mins = _interval_minutes()
    # next boundary: ceil(now/mins)*mins
    epoch = int(now.timestamp())
    bucket = mins * 60
    next_epoch = ((epoch // bucket) + 1) * bucket
    return datetime.fromtimestamp(next_epoch, tz=timezone.utc)


def _env_ok() -> dict:
    keys = [
        "NOTION_API_KEY",
        "GARMIN_EMAIL",
        "GARMIN_PASSWORD",
        "GARMIN_DB_ID",
        "MEALS_DB_ID",
        "MISTRAL_AI_API_KEY",
    ]
    present = {k: bool((os.environ.get(k) or "").strip()) for k in keys}
    return {
        "present": present,
        "missing": [k for k, v in present.items() if not v],
    }


def _run_sync() -> dict:
    global _LAST_RUN_UTC, _LAST_RESULT, _RUNNING
    if _RUNNING:
        raise HTTPException(status_code=409, detail="Sync already running")
    _RUNNING = True
    try:
        os.environ["RUN_ONCE"] = "1"
        import main as sync_main

        sync_main.main()
        _LAST_RUN_UTC = datetime.now(timezone.utc)
        _LAST_RESULT = {"ok": True}
        return _LAST_RESULT
    except Exception as e:
        _LAST_RUN_UTC = datetime.now(timezone.utc)
        _LAST_RESULT = {"ok": False, "error": str(e)}
        return _LAST_RESULT
    finally:
        _RUNNING = False


@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(
        """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Garmin → Notion Sync</title>
    <style>
      body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; max-width: 760px; margin: 40px auto; padding: 0 16px; }
      .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; margin: 12px 0; }
      button { padding: 10px 14px; border-radius: 10px; border: 1px solid #111827; background: #111827; color: white; cursor: pointer; }
      button:disabled { opacity: .6; cursor: not-allowed; }
      code { background: #f3f4f6; padding: 2px 6px; border-radius: 6px; }
      .muted { color: #6b7280; }
      .bad { color: #b91c1c; }
      .good { color: #065f46; }
    </style>
  </head>
  <body>
    <h2>Garmin → Notion Sync</h2>
    <div class="card">
      <div><strong>Status</strong></div>
      <div id="status" class="muted">Loading…</div>
      <div style="margin-top:12px;">
        <button id="runBtn" onclick="runNow()">Run now</button>
      </div>
      <div id="result" style="margin-top:12px;"></div>
    </div>

    <div class="card">
      <div><strong>API</strong></div>
      <div class="muted">Manual trigger: <code>/api/run</code> • Cron trigger: <code>/api/cron</code></div>
    </div>

    <script>
      async function refresh() {
        const r = await fetch('/api/status', { cache: 'no-store' });
        const j = await r.json();
        const s = document.getElementById('status');
        const missing = j.env.missing || [];
        const envLine = missing.length ? `<span class="bad">Missing env: ${missing.join(', ')}</span>` : `<span class="good">All required env vars present</span>`;
        s.innerHTML = `
          ${envLine}<br/>
          Now (UTC): <code>${j.now_utc}</code><br/>
          Next run (UTC): <code>${j.next_run_utc}</code><br/>
          Last run (UTC): <code>${j.last_run_utc || '—'}</code><br/>
          Running: <code>${j.running}</code>
        `;
        document.getElementById('runBtn').disabled = !!j.running;
      }

      async function runNow() {
        document.getElementById('runBtn').disabled = true;
        document.getElementById('result').innerHTML = '<span class="muted">Running…</span>';
        const r = await fetch('/api/run', { method: 'POST' });
        const j = await r.json();
        document.getElementById('result').innerHTML = j.ok
          ? '<span class="good">OK: sync executed</span>'
          : '<span class="bad">Error: ' + (j.error || 'unknown') + '</span>';
        await refresh();
      }

      refresh();
      setInterval(refresh, 10000);
    </script>
  </body>
</html>
"""
    )


@app.get("/api/status")
def status():
    now = datetime.now(timezone.utc)
    return {
        "ok": True,
        "now_utc": now.isoformat(),
        "next_run_utc": _next_run_utc(now).isoformat(),
        "last_run_utc": _LAST_RUN_UTC.isoformat() if _LAST_RUN_UTC else None,
        "running": _RUNNING,
        "env": _env_ok(),
    }


@app.post("/api/run")
def run():
    return JSONResponse(_run_sync())


@app.get("/api/cron")
def cron():
    # Vercel Cron will call this path per vercel.json schedule.
    return JSONResponse(_run_sync())

