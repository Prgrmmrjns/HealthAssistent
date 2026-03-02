"""
Auto Garmin sync: runs at startup then every SYNC_HOURS hours in a daemon thread.

- First run: full history sync (if no workouts stored yet) + 30 days of daily stats
- Subsequent runs: last 30 days only
- Rate limited: at most once per hour (manual or auto)
"""

import logging
import threading
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

SYNC_HOURS = 1
MIN_SYNC_INTERVAL_HOURS = 1

_thread = None
_last_sync = None
_sync_lock = threading.Lock()


def _has_any_workouts():
    try:
        from fitness.db import get_db
        return get_db().count_workouts() > 0
    except Exception:
        return True  # assume data exists if check fails, to avoid accidental full syncs


def _run_sync(days=30, full_history=False):
    """Execute one Garmin sync cycle. Returns True on success. Rate-limited to once per hour."""
    global _last_sync
    from django.conf import settings

    email = getattr(settings, "GARMIN_EMAIL", "")
    password = getattr(settings, "GARMIN_PASSWORD", "")
    if not (email and password):
        logger.debug("Garmin credentials not configured — skipping auto-sync.")
        return False

    # Rate limit: at most once per hour
    if _last_sync is not None:
        cutoff = datetime.now() - timedelta(hours=MIN_SYNC_INTERVAL_HOURS)
        if _last_sync > cutoff:
            logger.debug("Garmin sync skipped — last sync %s was less than 1h ago.", _last_sync.strftime("%H:%M"))
            return False

    if not _sync_lock.acquire(blocking=False):
        logger.debug("Sync already in progress — skipping.")
        return False

    try:
        from django.core.management import call_command
        if full_history:
            logger.info("Garmin first-run sync: fetching full activity history…")
            call_command("sync_garmin", all=True, verbosity=1)
            # Also get recent daily stats
            logger.info("Garmin first-run sync: fetching daily stats (30 days)…")
            call_command("sync_garmin", days=30, verbosity=1)
        else:
            logger.info("Garmin auto-sync: last %d days…", days)
            call_command("sync_garmin", days=days, verbosity=1)

        _last_sync = datetime.now()
        logger.info("Garmin sync complete at %s.", _last_sync.strftime("%H:%M"))
        return True
    except Exception as exc:
        logger.warning("Garmin sync failed: %s", exc)
        return False
    finally:
        _sync_lock.release()


def _loop():
    time.sleep(8)  # let Django + DB finish initialising

    # First run: full history if the database is empty
    if not _has_any_workouts():
        logger.info("No workouts found — running full history sync on first startup.")
        _run_sync(full_history=True)
    else:
        _run_sync(days=30)

    while True:
        time.sleep(SYNC_HOURS * 3600)
        _run_sync(days=30)


def start():
    """Start the background daemon thread (idempotent)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _thread = threading.Thread(target=_loop, daemon=True, name="garmin-bg-sync")
    _thread.start()
    logger.info("Garmin background sync thread started (every %dh).", SYNC_HOURS)


def trigger_sync(days=30, full_history=False):
    """Fire an immediate sync in a background thread (for manual 'Sync Now' button)."""
    t = threading.Thread(
        target=_run_sync,
        kwargs={"days": days, "full_history": full_history},
        daemon=True,
        name="garmin-manual-sync",
    )
    t.start()
    return t


def last_sync_time():
    """Return the datetime of the last successful sync, or None."""
    return _last_sync
