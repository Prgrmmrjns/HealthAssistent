"""
Fetch Garmin activities and daily stats, store locally.

Usage:
    python manage.py sync_garmin            # last 30 days
    python manage.py sync_garmin --days 7   # last 7 days
"""

from datetime import datetime, timedelta

import garminconnect
from django.conf import settings
from django.core.management.base import BaseCommand

from fitness.models import DailyStats, UserProfile, Workout, WorkoutSet

GARMIN_TO_SPORT = {
    "running": "Running",
    "cycling": "Cycling",
    "swimming": "Swimming",
    "strength_training": "Strength Training",
    "walking": "Walking",
    "hiking": "Hiking",
    "yoga": "Yoga",
    "other": "Other",
    "indoor_cycling": "Cycling",
    "trail_running": "Running",
    "treadmill_running": "Running",
    "lap_swimming": "Swimming",
    "open_water_swimming": "Swimming",
    "elliptical": "Other",
    "indoor_walking": "Walking",
    "mountaineering": "Hiking",
    "gym": "Strength Training",
}


def _safe_float(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _safe_int(v):
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _fetch_exercise_sets(garmin_client, activity_id):
    try:
        r = garmin_client.garth.get(
            "connectapi",
            f"/activity-service/activity/{activity_id}/exerciseSets",
            api=True,
        )
        data = r.json() if hasattr(r, "json") else r
    except Exception:
        return []

    out = []
    for i, s in enumerate(data.get("exerciseSets") or []):
        set_type_raw = (s.get("setType") or "ACTIVE").upper()

        if set_type_raw == "REST":
            continue

        if set_type_raw == "ACTIVE":
            exs = s.get("exercises") or []
            if exs and (exs[0].get("category") or "") == "CARDIO" and not exs[0].get("name"):
                set_type = "Warmup"
                exercise = "Warmup"
            else:
                set_type = "Active"
                ex = exs[0] if exs else {}
                exercise = ex.get("name") or ex.get("category") or "Unknown"
        else:
            set_type = set_type_raw.title()
            exercise = set_type

        reps = s.get("repetitionCount")
        if reps is not None:
            reps = int(reps)

        weight = s.get("weight")
        if weight is not None:
            weight = round(float(weight) / 1000, 1)
        else:
            weight = None

        duration = _safe_float(s.get("duration"))
        if duration is not None:
            duration = round(duration, 1)

        out.append({
            "exercise": exercise,
            "set_type": set_type,
            "reps": reps,
            "weight_kg": weight,
            "duration_sec": duration,
            "order": i + 1,
        })
    return out


def _sync_daily_stats(garmin, days, stdout):
    """Fetch daily summary, weight, and VO2max for each day."""
    today = datetime.now().date()
    created = 0
    updated = 0

    for offset in range(days):
        d = today - timedelta(days=offset)
        ds = d.strftime("%Y-%m-%d")

        defaults = {}

        try:
            summary = garmin.get_stats(ds)
            if summary:
                defaults["steps"] = _safe_int(summary.get("totalSteps"))
                defaults["total_calories"] = _safe_int(summary.get("totalKilocalories"))
                defaults["active_calories"] = _safe_int(summary.get("activeKilocalories"))
                defaults["resting_hr"] = _safe_int(summary.get("restingHeartRate"))
                defaults["avg_stress"] = _safe_int(summary.get("averageStressLevel"))
                defaults["body_battery_high"] = _safe_int(summary.get("bodyBatteryChargedValue"))
                defaults["body_battery_low"] = _safe_int(summary.get("bodyBatteryDrainedValue"))
                defaults["floors_climbed"] = _safe_int(summary.get("floorsAscended"))
                defaults["intensity_minutes"] = _safe_int(
                    (summary.get("moderateIntensityMinutes") or 0)
                    + (summary.get("vigorousIntensityMinutes") or 0)
                )
        except Exception:
            pass

        try:
            sleep_data = garmin.get_sleep_data(ds)
            if sleep_data:
                total_sleep = sleep_data.get("dailySleepDTO", {}).get("sleepTimeSeconds")
                if total_sleep:
                    defaults["sleep_hours"] = round(total_sleep / 3600, 1)
        except Exception:
            pass

        try:
            hrv_data = garmin.get_hrv_data(ds)
            if hrv_data:
                hrv_summary = hrv_data.get("hrvSummary", {})
                defaults["hrv"] = _safe_float(
                    hrv_summary.get("weeklyAvg") or hrv_summary.get("lastNightAvg")
                )
        except Exception:
            pass

        try:
            weight_data = garmin.get_body_composition(ds)
            if weight_data:
                w = weight_data.get("weight")
                if w and w > 0:
                    defaults["weight_kg"] = round(w / 1000, 1)
        except Exception:
            pass

        try:
            vo2 = garmin.get_max_metrics(ds)
            if vo2:
                generic = vo2.get("generic", {})
                vo2_val = generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue")
                if vo2_val:
                    defaults["vo2_max"] = round(float(vo2_val), 1)
        except Exception:
            pass

        if not any(v is not None for v in defaults.values()):
            continue

        _, is_new = DailyStats.objects.update_or_create(date=d, defaults=defaults)
        if is_new:
            created += 1
        else:
            updated += 1

    stdout.write(f"  Daily stats: {created} created, {updated} updated.")


class Command(BaseCommand):
    help = "Sync Garmin activities + daily stats to local database"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)

    def handle(self, *args, **options):
        email = settings.GARMIN_EMAIL
        password = settings.GARMIN_PASSWORD
        profile = UserProfile.get()

        if not email or not password:
            self.stdout.write(self.style.WARNING(
                "GARMIN_EMAIL / GARMIN_PASSWORD not set — running without Garmin."
            ))
            profile.garmin_connected = False
            profile.save(update_fields=["garmin_connected"])
            return

        self.stdout.write("Logging in to Garmin Connect...")
        try:
            garmin = garminconnect.Garmin(email=email, password=password)
            garmin.login()
        except Exception as exc:
            self.stderr.write(self.style.WARNING(
                f"Garmin login failed ({exc}). Running without Garmin."
            ))
            profile.garmin_connected = False
            profile.save(update_fields=["garmin_connected"])
            return

        profile.garmin_connected = True
        profile.save(update_fields=["garmin_connected"])

        days = options["days"]
        today = datetime.now().date()
        start = (today - timedelta(days=days)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")

        # 1. Daily stats
        self.stdout.write(f"Syncing daily stats ({days} days)...")
        _sync_daily_stats(garmin, days, self.stdout)

        # 2. Activities
        self.stdout.write(f"Fetching activities ({start} to {end})...")
        activities = garmin.get_activities_by_date(start, end) or []
        self.stdout.write(f"  Found {len(activities)} activities.")

        created_count = 0
        sets_count = 0

        for a in activities:
            activity_id = a.get("activityId")
            if not activity_id:
                continue

            if Workout.objects.filter(garmin_activity_id=activity_id).exists():
                continue

            atype = a.get("activityType", {})
            type_key = atype.get("typeKey", "other") if isinstance(atype, dict) else str(atype)
            dur = _safe_float(a.get("duration"))
            dist = _safe_float(a.get("distance"))
            date_str = (a.get("startTimeLocal") or "")[:10]
            if not date_str:
                continue

            sport = GARMIN_TO_SPORT.get(type_key, "Other")

            workout = Workout.objects.create(
                garmin_activity_id=activity_id,
                name=a.get("activityName") or type_key.replace("_", " ").title(),
                date=date_str,
                sport=sport,
                duration_min=round(dur / 60, 1) if dur else None,
                distance_km=round(dist / 1000, 2) if dist else None,
                calories=_safe_float(a.get("calories")),
                avg_hr=_safe_float(a.get("averageHR")),
                max_hr=_safe_float(a.get("maxHR")),
            )
            created_count += 1

            if sport == "Strength Training":
                sets_data = _fetch_exercise_sets(garmin, activity_id)
                for s in sets_data:
                    WorkoutSet.objects.create(
                        workout=workout,
                        exercise=s["exercise"],
                        set_type=s["set_type"],
                        reps=s["reps"],
                        weight_kg=s["weight_kg"],
                        duration_sec=s["duration_sec"],
                        order=s["order"],
                    )
                    sets_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. {created_count} new workouts, {sets_count} sets. "
            f"({len(activities) - created_count} already existed.)"
        ))
