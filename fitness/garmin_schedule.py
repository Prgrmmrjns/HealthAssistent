"""
Schedule a planned workout to Garmin Connect calendar via garminconnect.

Uses garth/connectapi to add workouts to the Garmin calendar.
"""

import logging

logger = logging.getLogger(__name__)


def schedule_to_garmin(planned_workout):
    """
    Attempt to add a planned workout to Garmin Connect calendar.
    Returns (success: bool, message: str).

    planned_workout: object with .date, .time, .sport, .name, .duration_min, .distance_km
    """
    from django.conf import settings

    email = getattr(settings, "GARMIN_EMAIL", "")
    password = getattr(settings, "GARMIN_PASSWORD", "")
    if not (email and password):
        return False, "Garmin credentials not configured"

    try:
        import garminconnect
        gc = garminconnect.Garmin(email=email, password=password)
        gc.login()
    except Exception as exc:
        logger.warning("Garmin login failed for schedule sync: %s", exc)
        return False, f"Garmin login failed: {exc}"

    date_str = str(getattr(planned_workout, "date", ""))
    time_str = ""
    t = getattr(planned_workout, "time", None)
    if t:
        time_str = t.strftime("%H:%M") if hasattr(t, "strftime") else str(t)[:5]

    # Build datetime for Garmin (ISO format)
    if time_str:
        dt_iso = f"{date_str}T{time_str}:00"
    else:
        dt_iso = f"{date_str}T09:00:00"  # default 9:00

    name = getattr(planned_workout, "name", "Planned workout")
    sport = getattr(planned_workout, "sport", "Other")
    duration_min = getattr(planned_workout, "duration_min", None)
    distance_km = getattr(planned_workout, "distance_km", None)

    # Garmin activity type keys (approximate mapping)
    sport_key_map = {
        "Strength Training": "strength_training",
        "Running": "running",
        "Cycling": "cycling",
        "Swimming": "swimming",
        "Walking": "walking",
        "Hiking": "hiking",
        "Yoga": "yoga",
        "Other": "other",
    }
    sport_key = sport_key_map.get(sport, "other")

    try:
        # Use garth to POST to Garmin Connect workout/calendar API
        # The garminconnect library doesn't expose workout creation directly;
        # we try the connectapi endpoint used by the Garmin web UI.
        r = gc.garth.post(
            "connectapi",
            "/workout-service/workout",
            api=True,
            json={
                "workoutName": name[:80],
                "sportType": {"sportTypeKey": sport_key},
                "startDate": dt_iso,
                "description": (getattr(planned_workout, "description", "") or "")[:500],
            },
        )
        if r and getattr(r, "status_code", 0) in (200, 201, 204):
            data = r.json() if hasattr(r, "json") else {}
            workout_id = data.get("workoutId") or data.get("id") or ""
            return True, workout_id
    except Exception as exc:
        logger.warning("Garmin workout creation failed: %s", exc)

    # Fallback: create a calendar event (simpler endpoint)
    try:
        r = gc.garth.post(
            "connectapi",
            "/calendar-service/event",
            api=True,
            json={
                "type": "WORKOUT",
                "startDate": dt_iso,
                "title": name[:80],
                "notes": (getattr(planned_workout, "description", "") or "")[:500],
            },
        )
        if r and getattr(r, "status_code", 0) in (200, 201, 204):
            return True, "Event added"
    except Exception as exc:
        logger.warning("Garmin calendar event creation failed: %s", exc)

    return False, "Garmin API does not support workout creation from this app. Use the Garmin Connect web or mobile app to add workouts, or try the Chrome extension 'Share your Garmin Connect workout'."
