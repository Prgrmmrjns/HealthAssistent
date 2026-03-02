"""
Database abstraction layer.

- When SUPABASE_URL + SUPABASE_API_KEY are configured: uses Supabase REST API.
- Otherwise: falls back to Django ORM (SQLite for local development).
"""

from datetime import date as _date

# ---------------------------------------------------------------------------
# Display maps
# ---------------------------------------------------------------------------

MEAL_TYPE_DISPLAY = {
    "breakfast": "Breakfast", "lunch": "Lunch",
    "dinner": "Dinner", "snack": "Snack",
}
STRESS_DISPLAY = {
    "low": "Low", "medium": "Medium", "high": "High", "very_high": "Very High",
}


def _d(v):
    """Parse an ISO date string or return as-is if already a date."""
    if v is None:
        return None
    if isinstance(v, _date):
        return v
    try:
        return _date.fromisoformat(str(v)[:10])
    except Exception:
        return v


def _t(v):
    """Parse an ISO time string (HH:MM or HH:MM:SS) to time object."""
    if v is None:
        return None
    try:
        from datetime import time as _time
        if isinstance(v, _time):
            return v
        s = str(v)
        parts = s.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        sec = int(parts[2]) if len(parts) > 2 else 0
        return _time(h, m, sec)
    except Exception:
        return None


from fitness.models import SPORT_CHOICES  # Single source of truth for sport dropdowns


# ---------------------------------------------------------------------------
# Wrapper objects  (Supabase returns plain dicts; templates expect attributes)
# ---------------------------------------------------------------------------

class Obj:
    """Generic dict → object wrapper."""
    def __init__(self, data: dict):
        d = dict(data)
        if isinstance(d.get("date"), str):
            d["date"] = _d(d["date"])
        if isinstance(d.get("time"), str):
            d["time"] = _t(d["time"])
        self.__dict__.update(d)

    @property
    def pk(self):
        """Alias for id — mirrors Django model instances so templates work unchanged."""
        return getattr(self, "id", None)

    def __bool__(self):
        return True

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.__dict__}>"


class _RelatedMgr:
    """Minimal queryset-like manager for pre-fetched related objects."""
    def __init__(self, lst):
        self._lst = list(lst)

    def all(self):
        return self._lst

    def count(self):
        return len(self._lst)

    def exclude(self, **kw):
        result = self._lst
        for k, v in kw.items():
            result = [o for o in result if getattr(o, k, None) != v]
        return result

    def select_related(self, *args):
        return self  # return self so .all() / .count() chaining still works

    def __iter__(self):
        return iter(self._lst)

    def __len__(self):
        return len(self._lst)


class WorkoutObj(Obj):
    def __init__(self, data, sets=None):
        super().__init__(data)
        self._sets = [WorkoutSetObj(s) for s in (sets or [])]

    @property
    def sets(self):
        return _RelatedMgr(self._sets)

    @property
    def active_sets(self):
        return [s for s in self._sets if s.set_type != "Rest"]


class WorkoutSetObj(Obj):
    pass


class ExerciseObj(Obj):
    pass


class DailyStatsObj(Obj):
    pass


class WorkoutTemplateObj(Obj):
    def __init__(self, data, exercises=None):
        super().__init__(data)
        self._exercises = [TemplateExerciseObj(e) for e in (exercises or [])]

    @property
    def exercises(self):
        return _RelatedMgr(self._exercises)

    @property
    def exercise_count(self):
        return len(self._exercises)

    @property
    def total_sets(self):
        return sum(getattr(e, "sets", 0) for e in self._exercises)


class TemplateExerciseObj(Obj):
    def __init__(self, data):
        d = dict(data)
        ex = d.pop("exercise", None)
        super().__init__(d)
        self.exercise = ExerciseObj(ex) if isinstance(ex, dict) else None

    @property
    def display_name(self):
        ex = getattr(self, "exercise", None)
        if ex and hasattr(ex, "name"):
            return ex.name
        return getattr(self, "custom_name", "") or "Unnamed"


class ProfileObj(Obj):
    @property
    def pk(self):
        return getattr(self, "id", 1)  # default 1 for the singleton

    def save(self, update_fields=None):
        pass  # No-op; saving is done via db.save_profile()


class DailyCheckinObj(Obj):
    def get_stress_display(self):
        return STRESS_DISPLAY.get(getattr(self, "stress", ""), "")


class MealObj(Obj):
    def get_meal_type_display(self):
        return MEAL_TYPE_DISPLAY.get(getattr(self, "meal_type", ""), "")


class PlannedWorkoutObj(Obj):
    pass


class GoalObj(Obj):
    @property
    def milestones(self):
        return getattr(self, "_milestones", [])


class MilestoneObj(Obj):
    pass


class HabitObj(Obj):
    pass


class HabitLogObj(Obj):
    pass


# ---------------------------------------------------------------------------
# Supabase backend
# ---------------------------------------------------------------------------

class SupabaseBackend:
    def __init__(self):
        from supabase import create_client
        from django.conf import settings
        self.sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_API_KEY)

    def _t(self, name):
        return self.sb.table(name)

    # --- UserProfile (singleton pk=1) ---

    def get_profile(self):
        r = self._t("fitness_userprofile").select("*").eq("id", 1).execute()
        if r.data:
            return ProfileObj(r.data[0])
        r = self._t("fitness_userprofile").insert({"id": 1, "name": "", "garmin_connected": False}).execute()
        return ProfileObj(r.data[0] if r.data else {"id": 1, "name": "", "garmin_connected": False})

    def save_profile(self, pk, data):
        self._t("fitness_userprofile").upsert({"id": pk, **data}).execute()

    # --- Workouts ---

    def get_workouts(self, sport=None, limit=None):
        q = self._t("fitness_workout").select("*").order("date", desc=True).order("created_at", desc=True)
        if sport:
            q = q.eq("sport", sport)
        if limit:
            q = q.limit(limit)
        return [WorkoutObj(d) for d in (q.execute().data or [])]

    def get_workouts_with_set_count(self, sport=None):
        workouts = self.get_workouts(sport=sport)
        for w in workouts:
            r = self._t("fitness_workoutset").select("*", count="exact").eq("workout_id", w.id).neq("set_type", "Rest").execute()
            w.set_count = r.count or 0
        return workouts

    def get_workout(self, pk):
        r = self._t("fitness_workout").select("*").eq("id", pk).execute()
        if not r.data:
            return None
        sets_r = self._t("fitness_workoutset").select("*").eq("workout_id", pk).order("order").execute()
        return WorkoutObj(r.data[0], sets=sets_r.data or [])

    def count_workouts(self, sport=None):
        q = self._t("fitness_workout").select("*", count="exact")
        if sport:
            q = q.eq("sport", sport)
        return q.execute().count or 0

    def workout_sports_breakdown(self):
        from collections import Counter
        r = self._t("fitness_workout").select("sport").execute()
        counts = Counter(d["sport"] for d in (r.data or []))
        return [{"sport": s, "count": c} for s, c in counts.most_common()]

    def avg_workout_duration(self):
        r = self._t("fitness_workout").select("duration_min").execute()
        vals = [d["duration_min"] for d in (r.data or []) if d.get("duration_min") is not None]
        return sum(vals) / len(vals) if vals else None

    def count_active_sets(self):
        r = self._t("fitness_workoutset").select("*", count="exact").neq("set_type", "Rest").execute()
        return r.count or 0

    def workout_exists(self, garmin_activity_id):
        r = self._t("fitness_workout").select("id", count="exact").eq("garmin_activity_id", garmin_activity_id).execute()
        return (r.count or 0) > 0

    def create_workout(self, data):
        r = self._t("fitness_workout").insert(data).execute()
        return WorkoutObj(r.data[0]) if r.data else None

    def create_workout_set(self, data):
        self._t("fitness_workoutset").insert(data).execute()

    # --- Daily stats ---

    def get_latest_stats(self):
        r = self._t("fitness_dailystats").select("*").order("date", desc=True).limit(1).execute()
        return DailyStatsObj(r.data[0]) if r.data else None

    def get_latest_with_field(self, field):
        r = self._t("fitness_dailystats").select("*").not_.is_(field, "null").order("date", desc=True).limit(1).execute()
        return DailyStatsObj(r.data[0]) if r.data else None

    def get_steps_last_n_days(self, n=7):
        r = self._t("fitness_dailystats").select("date,steps").not_.is_("steps", "null").order("date", desc=True).limit(n).execute()
        data = [(_d(d["date"]), d["steps"]) for d in (r.data or [])]
        data.reverse()
        return data

    def get_stats_range(self, from_date):
        r = self._t("fitness_dailystats").select("*").gte("date", str(from_date)).order("date").execute()
        return [DailyStatsObj(d) for d in (r.data or [])]

    def upsert_daily_stats(self, date_str, data):
        self._t("fitness_dailystats").upsert(
            {"date": date_str, **data}, on_conflict="date"
        ).execute()

    # --- Exercises ---

    def get_exercises(self, category=None, muscle=None, q=None, limit=200):
        qs = self._t("fitness_exercise").select("*")
        if category:
            qs = qs.eq("garmin_category", category)
        if muscle:
            qs = qs.eq("muscle_group", muscle)
        if q:
            qs = qs.ilike("name", f"%{q}%")
        r = qs.order("name").limit(limit).execute()
        return [ExerciseObj(d) for d in (r.data or [])]

    def count_exercises(self, category=None, muscle=None, q=None):
        qs = self._t("fitness_exercise").select("*", count="exact")
        if category:
            qs = qs.eq("garmin_category", category)
        if muscle:
            qs = qs.eq("muscle_group", muscle)
        if q:
            qs = qs.ilike("name", f"%{q}%")
        return qs.execute().count or 0

    def get_exercise_categories(self):
        r = self._t("fitness_exercise").select("garmin_category").execute()
        return sorted(set(d["garmin_category"] for d in (r.data or []) if d.get("garmin_category")))

    def get_exercise_muscles(self):
        r = self._t("fitness_exercise").select("muscle_group").execute()
        return sorted(set(d["muscle_group"] for d in (r.data or []) if d.get("muscle_group")))

    def search_exercises(self, q, exercise_type="Strength", limit=20):
        r = (self._t("fitness_exercise").select("id,name,muscle_group")
             .ilike("name", f"%{q}%").eq("exercise_type", exercise_type).limit(limit).execute())
        return r.data or []

    def get_exercises_by_type(self, exercise_type="Strength"):
        r = self._t("fitness_exercise").select("*").eq("exercise_type", exercise_type).order("name").limit(500).execute()
        return [ExerciseObj(d) for d in (r.data or [])]

    def upsert_exercise(self, data):
        self._t("fitness_exercise").upsert(data, on_conflict="name").execute()

    def get_existing_garmin_ids(self):
        """Return a set of all garmin_activity_ids already stored (for bulk dedup)."""
        r = self._t("fitness_workout").select("garmin_activity_id").execute()
        return {d["garmin_activity_id"] for d in (r.data or []) if d.get("garmin_activity_id")}

    # --- Workout templates ---

    def get_templates(self):
        r = self._t("fitness_workouttemplate").select("*").order("updated_at", desc=True).execute()
        result = []
        for d in (r.data or []):
            exs = self._t("fitness_templateexercise").select("*, exercise:exercise_id(*)").eq("template_id", d["id"]).order("order").execute()
            result.append(WorkoutTemplateObj(d, exercises=exs.data or []))
        return result

    def get_template(self, pk):
        r = self._t("fitness_workouttemplate").select("*").eq("id", pk).execute()
        if not r.data:
            return None
        exs = self._t("fitness_templateexercise").select("*, exercise:exercise_id(*)").eq("template_id", pk).order("order").execute()
        return WorkoutTemplateObj(r.data[0], exercises=exs.data or [])

    def create_template(self, name, description, sport="Strength Training"):
        r = self._t("fitness_workouttemplate").insert({"name": name, "description": description, "sport": sport}).execute()
        return WorkoutTemplateObj(r.data[0]) if r.data else None

    def update_template(self, pk, name, description, sport="Strength Training"):
        self._t("fitness_workouttemplate").update({"name": name, "description": description, "sport": sport}).eq("id", pk).execute()

    def delete_template(self, pk):
        self._t("fitness_templateexercise").delete().eq("template_id", pk).execute()
        self._t("fitness_workouttemplate").delete().eq("id", pk).execute()

    def delete_template_exercises(self, template_id):
        self._t("fitness_templateexercise").delete().eq("template_id", template_id).execute()

    def create_template_exercise(self, data):
        self._t("fitness_templateexercise").insert(data).execute()

    def get_exercises_for_template(self):
        return self.get_exercises_by_type("Strength")

    # --- Planned workouts ---

    def get_planned_workouts(self, from_date=None, to_date=None, limit=100):
        try:
            q = self._t("fitness_plannedworkout").select("*").order("date").order("time")
            if from_date:
                q = q.gte("date", str(from_date))
            if to_date:
                q = q.lte("date", str(to_date))
            r = q.limit(limit).execute()
            return [PlannedWorkoutObj(d) for d in (r.data or [])]
        except Exception:
            return []  # Table may not exist yet; run supabase_setup.sql

    def get_planned_workout(self, pk):
        try:
            r = self._t("fitness_plannedworkout").select("*").eq("id", pk).execute()
            return PlannedWorkoutObj(r.data[0]) if r.data else None
        except Exception:
            return None

    def create_planned_workout(self, data):
        r = self._t("fitness_plannedworkout").insert(data).execute()
        return PlannedWorkoutObj(r.data[0]) if r.data else None

    def update_planned_workout(self, pk, data):
        r = self._t("fitness_plannedworkout").update(data).eq("id", pk).execute()
        return PlannedWorkoutObj(r.data[0]) if r.data else None

    def delete_planned_workout(self, pk):
        self._t("fitness_plannedworkout").delete().eq("id", pk).execute()

    # --- Daily check-in ---

    def get_checkins(self, limit=30):
        r = self._t("fitness_dailycheckin").select("*").order("date", desc=True).limit(limit).execute()
        return [DailyCheckinObj(d) for d in (r.data or [])]

    def get_or_create_checkin(self, target_date):
        date_str = str(target_date)
        r = self._t("fitness_dailycheckin").select("*").eq("date", date_str).execute()
        if r.data:
            return DailyCheckinObj(r.data[0])
        r = self._t("fitness_dailycheckin").insert({"date": date_str}).execute()
        return DailyCheckinObj(r.data[0] if r.data else {"date": date_str, "id": None})

    def get_checkin_today(self):
        r = self._t("fitness_dailycheckin").select("*").eq("date", str(_date.today())).execute()
        return DailyCheckinObj(r.data[0]) if r.data else None

    def save_checkin(self, pk, data):
        if pk:
            self._t("fitness_dailycheckin").update(data).eq("id", pk).execute()
        else:
            self._t("fitness_dailycheckin").insert(data).execute()

    # --- Meals ---

    def get_meals(self, limit=50):
        r = self._t("fitness_meal").select("*").order("date", desc=True).order("created_at", desc=True).limit(limit).execute()
        return [MealObj(d) for d in (r.data or [])]

    def get_meals_today(self):
        r = self._t("fitness_meal").select("*").eq("date", str(_date.today())).execute()
        return [MealObj(d) for d in (r.data or [])]

    def get_meal(self, pk):
        r = self._t("fitness_meal").select("*").eq("id", pk).execute()
        return MealObj(r.data[0]) if r.data else None

    def create_meal(self, data):
        r = self._t("fitness_meal").insert(data).execute()
        return MealObj(r.data[0]) if r.data else None

    def update_meal(self, pk, data):
        r = self._t("fitness_meal").update(data).eq("id", pk).execute()
        return MealObj(r.data[0]) if r.data else None

    def delete_meal(self, pk):
        self._t("fitness_meal").delete().eq("id", pk).execute()

    def get_sport_choices(self):
        r = self._t("fitness_workout").select("sport").execute()
        return sorted(set(d["sport"] for d in (r.data or []) if d.get("sport")))

    # --- Goals & Milestones ---

    def get_goals(self, status=None):
        try:
            q = self._t("fitness_goal").select("*").order("created_at", desc=True)
            if status:
                q = q.eq("status", status)
            r = q.execute()
            return [GoalObj(d) for d in (r.data or [])]
        except Exception:
            return []

    def get_goal(self, pk):
        try:
            r = self._t("fitness_goal").select("*").eq("id", pk).execute()
            if not r.data:
                return None
            m = self._t("fitness_milestone").select("*").eq("goal_id", pk).order("target_date").order("created_at").execute()
            g = GoalObj(r.data[0])
            g._milestones = [MilestoneObj(d) for d in (m.data or [])]
            return g
        except Exception:
            return None

    def create_goal(self, data):
        try:
            r = self._t("fitness_goal").insert(data).execute()
            return GoalObj(r.data[0]) if r.data else None
        except Exception:
            return None

    def update_goal(self, pk, data):
        try:
            self._t("fitness_goal").update(data).eq("id", pk).execute()
        except Exception:
            pass

    def delete_goal(self, pk):
        try:
            self._t("fitness_goal").delete().eq("id", pk).execute()
        except Exception:
            pass

    def create_milestone(self, data):
        try:
            r = self._t("fitness_milestone").insert(data).execute()
            return MilestoneObj(r.data[0]) if r.data else None
        except Exception:
            return None

    def update_milestone(self, pk, data):
        try:
            self._t("fitness_milestone").update(data).eq("id", pk).execute()
        except Exception:
            pass

    def delete_milestone(self, pk):
        try:
            self._t("fitness_milestone").delete().eq("id", pk).execute()
        except Exception:
            pass

    def get_milestone(self, pk):
        try:
            r = self._t("fitness_milestone").select("*").eq("id", pk).execute()
            return MilestoneObj(r.data[0]) if r.data else None
        except Exception:
            return None

    # --- Habits ---

    def get_habits(self):
        try:
            r = self._t("fitness_habit").select("*").order("order").order("name").execute()
            return [HabitObj(d) for d in (r.data or [])]
        except Exception:
            return []

    def get_habit(self, pk):
        try:
            r = self._t("fitness_habit").select("*").eq("id", pk).execute()
            return HabitObj(r.data[0]) if r.data else None
        except Exception:
            return None

    def create_habit(self, data):
        try:
            r = self._t("fitness_habit").insert(data).execute()
            return HabitObj(r.data[0]) if r.data else None
        except Exception:
            return None

    def update_habit(self, pk, data):
        try:
            self._t("fitness_habit").update(data).eq("id", pk).execute()
        except Exception:
            pass

    def delete_habit(self, pk):
        try:
            self._t("fitness_habit").delete().eq("id", pk).execute()
        except Exception:
            pass

    def get_habitlogs_for_date(self, target_date):
        try:
            r = self._t("fitness_habitlog").select("*").eq("date", str(target_date)).execute()
            return [HabitLogObj(d) for d in (r.data or [])]
        except Exception:
            return []

    def upsert_habitlog(self, habit_id, date_str, completed):
        try:
            self._t("fitness_habitlog").upsert(
                {"habit_id": habit_id, "date": date_str, "completed": completed},
                on_conflict="habit_id,date",
            ).execute()
        except Exception:
            pass

    def seed_default_habits(self):
        defaults = [
            {"name": "Go to sleep before 23:00", "description": "Get enough rest for better recovery", "is_suggested": True, "order": 1},
            {"name": "Read a book", "description": "At least 15–30 minutes of reading", "is_suggested": True, "order": 2},
            {"name": "Meditate", "description": "Mindfulness or breathing exercise", "is_suggested": True, "order": 3},
        ]
        for d in defaults:
            try:
                r = self._t("fitness_habit").select("id").eq("name", d["name"]).execute()
                if not (r.data and len(r.data) > 0):
                    self._t("fitness_habit").insert(d).execute()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# ORM backend (local dev — no SUPABASE_URL configured)
# ---------------------------------------------------------------------------

class ORMBackend:
    """All operations go through Django ORM → returns real model instances."""

    def get_profile(self):
        from fitness.models import UserProfile
        return UserProfile.get()

    def save_profile(self, pk, data):
        from fitness.models import UserProfile
        p = UserProfile.get()
        for k, v in data.items():
            setattr(p, k, v)
        p.save()

    def get_workouts(self, sport=None, limit=None):
        from fitness.models import Workout
        qs = Workout.objects.all()
        if sport:
            qs = qs.filter(sport=sport)
        return list(qs[:limit] if limit else qs)

    def get_workouts_with_set_count(self, sport=None):
        from fitness.models import Workout
        from django.db.models import Count, Q
        qs = Workout.objects.annotate(set_count=Count("sets", filter=~Q(sets__set_type="Rest")))
        if sport:
            qs = qs.filter(sport=sport)
        return list(qs)

    def get_workout(self, pk):
        from fitness.models import Workout
        try:
            return Workout.objects.get(pk=pk)
        except Workout.DoesNotExist:
            return None

    def count_workouts(self, sport=None):
        from fitness.models import Workout
        qs = Workout.objects.filter(sport=sport) if sport else Workout.objects.all()
        return qs.count()

    def workout_sports_breakdown(self):
        from fitness.models import Workout
        from django.db.models import Count
        return list(Workout.objects.values("sport").annotate(count=Count("id")).order_by("-count"))

    def avg_workout_duration(self):
        from fitness.models import Workout
        from django.db.models import Avg
        return Workout.objects.aggregate(avg=Avg("duration_min"))["avg"]

    def count_active_sets(self):
        from fitness.models import WorkoutSet
        return WorkoutSet.objects.exclude(set_type="Rest").count()

    def workout_exists(self, garmin_activity_id):
        from fitness.models import Workout
        return Workout.objects.filter(garmin_activity_id=garmin_activity_id).exists()

    def create_workout(self, data):
        from fitness.models import Workout
        return Workout.objects.create(**data)

    def create_workout_set(self, data):
        from fitness.models import WorkoutSet
        WorkoutSet.objects.create(**data)

    def get_latest_stats(self):
        from fitness.models import DailyStats
        return DailyStats.objects.first()

    def get_latest_with_field(self, field):
        from fitness.models import DailyStats
        return DailyStats.objects.exclude(**{field: None}).order_by("-date").first()

    def get_steps_last_n_days(self, n=7):
        from fitness.models import DailyStats
        data = list(DailyStats.objects.exclude(steps=None).order_by("-date")[:n].values_list("date", "steps"))
        data.reverse()
        return data

    def get_stats_range(self, from_date):
        from fitness.models import DailyStats
        return list(DailyStats.objects.filter(date__gte=from_date).order_by("date"))

    def upsert_daily_stats(self, date_str, data):
        from fitness.models import DailyStats
        d = _d(date_str)
        DailyStats.objects.update_or_create(date=d, defaults=data)

    def get_exercises(self, category=None, muscle=None, q=None, limit=200):
        from fitness.models import Exercise
        qs = Exercise.objects.all()
        if category:
            qs = qs.filter(garmin_category=category)
        if muscle:
            qs = qs.filter(muscle_group=muscle)
        if q:
            qs = qs.filter(name__icontains=q)
        return list(qs[:limit])

    def count_exercises(self, category=None, muscle=None, q=None):
        from fitness.models import Exercise
        qs = Exercise.objects.all()
        if category:
            qs = qs.filter(garmin_category=category)
        if muscle:
            qs = qs.filter(muscle_group=muscle)
        if q:
            qs = qs.filter(name__icontains=q)
        return qs.count()

    def get_exercise_categories(self):
        from fitness.models import Exercise
        return list(Exercise.objects.values_list("garmin_category", flat=True).distinct().order_by("garmin_category"))

    def get_exercise_muscles(self):
        from fitness.models import Exercise
        return list(Exercise.objects.values_list("muscle_group", flat=True).distinct().order_by("muscle_group"))

    def search_exercises(self, q, exercise_type="Strength", limit=20):
        from fitness.models import Exercise
        return list(Exercise.objects.filter(name__icontains=q, exercise_type=exercise_type).values("id", "name", "muscle_group")[:limit])

    def get_exercises_by_type(self, exercise_type="Strength"):
        from fitness.models import Exercise
        return list(Exercise.objects.filter(exercise_type=exercise_type)[:500])

    def upsert_exercise(self, data):
        from fitness.models import Exercise
        Exercise.objects.update_or_create(name=data["name"], defaults={k: v for k, v in data.items() if k != "name"})

    def get_existing_garmin_ids(self):
        from fitness.models import Workout
        return set(Workout.objects.values_list("garmin_activity_id", flat=True))

    def get_templates(self):
        from fitness.models import WorkoutTemplate
        return list(WorkoutTemplate.objects.prefetch_related("exercises__exercise").all())

    def get_template(self, pk):
        from fitness.models import WorkoutTemplate
        try:
            return WorkoutTemplate.objects.prefetch_related("exercises__exercise").get(pk=pk)
        except WorkoutTemplate.DoesNotExist:
            return None

    def create_template(self, name, description, sport="Strength Training"):
        from fitness.models import WorkoutTemplate
        return WorkoutTemplate.objects.create(name=name, description=description, sport=sport)

    def update_template(self, pk, name, description, sport="Strength Training"):
        from fitness.models import WorkoutTemplate
        t = WorkoutTemplate.objects.get(pk=pk)
        t.name = name
        t.description = description
        t.sport = sport
        t.save()

    def delete_template(self, pk):
        from fitness.models import WorkoutTemplate
        WorkoutTemplate.objects.filter(pk=pk).delete()

    def delete_template_exercises(self, template_id):
        from fitness.models import TemplateExercise
        TemplateExercise.objects.filter(template_id=template_id).delete()

    def create_template_exercise(self, data):
        from fitness.models import TemplateExercise, Exercise
        exercise_obj = None
        if data.get("exercise_id"):
            try:
                exercise_obj = Exercise.objects.get(pk=data["exercise_id"])
            except Exercise.DoesNotExist:
                pass
        TemplateExercise.objects.create(
            template_id=data["template_id"],
            exercise=exercise_obj,
            custom_name=data.get("custom_name", ""),
            sets=data.get("sets", 3),
            reps=data.get("reps", 10),
            weight_kg=data.get("weight_kg"),
            rest_sec=data.get("rest_sec", 90),
            notes=data.get("notes", ""),
            order=data.get("order", 0),
        )

    def get_exercises_for_template(self):
        return self.get_exercises_by_type("Strength")

    def get_planned_workouts(self, from_date=None, to_date=None, limit=100):
        from fitness.models import PlannedWorkout
        qs = PlannedWorkout.objects.all().order_by("date", "time")
        if from_date:
            qs = qs.filter(date__gte=from_date)
        if to_date:
            qs = qs.filter(date__lte=to_date)
        return list(qs[:limit])

    def get_planned_workout(self, pk):
        from fitness.models import PlannedWorkout
        try:
            return PlannedWorkout.objects.get(pk=pk)
        except PlannedWorkout.DoesNotExist:
            return None

    def create_planned_workout(self, data):
        from fitness.models import PlannedWorkout
        return PlannedWorkout.objects.create(**data)

    def update_planned_workout(self, pk, data):
        from fitness.models import PlannedWorkout
        PlannedWorkout.objects.filter(pk=pk).update(**data)
        return PlannedWorkout.objects.get(pk=pk)

    def delete_planned_workout(self, pk):
        from fitness.models import PlannedWorkout
        PlannedWorkout.objects.filter(pk=pk).delete()

    def get_goals(self, status=None):
        from fitness.models import Goal
        qs = Goal.objects.all().order_by("-created_at")
        if status:
            qs = qs.filter(status=status)
        return list(qs)

    def get_goal(self, pk):
        from fitness.models import Goal
        try:
            return Goal.objects.prefetch_related("milestones").get(pk=pk)
        except Goal.DoesNotExist:
            return None

    def create_goal(self, data):
        from fitness.models import Goal
        return Goal.objects.create(**data)

    def update_goal(self, pk, data):
        from fitness.models import Goal
        Goal.objects.filter(pk=pk).update(**data)

    def delete_goal(self, pk):
        from fitness.models import Goal
        Goal.objects.filter(pk=pk).delete()

    def create_milestone(self, data):
        from fitness.models import Milestone
        return Milestone.objects.create(**data)

    def update_milestone(self, pk, data):
        from fitness.models import Milestone
        Milestone.objects.filter(pk=pk).update(**data)

    def delete_milestone(self, pk):
        from fitness.models import Milestone
        Milestone.objects.filter(pk=pk).delete()

    def get_milestone(self, pk):
        from fitness.models import Milestone
        try:
            return Milestone.objects.get(pk=pk)
        except Milestone.DoesNotExist:
            return None

    def get_habits(self):
        from fitness.models import Habit
        return list(Habit.objects.all().order_by("order", "name"))

    def get_habit(self, pk):
        from fitness.models import Habit
        try:
            return Habit.objects.get(pk=pk)
        except Habit.DoesNotExist:
            return None

    def create_habit(self, data):
        from fitness.models import Habit
        return Habit.objects.create(**data)

    def update_habit(self, pk, data):
        from fitness.models import Habit
        Habit.objects.filter(pk=pk).update(**data)

    def delete_habit(self, pk):
        from fitness.models import Habit
        Habit.objects.filter(pk=pk).delete()

    def get_habitlogs_for_date(self, target_date):
        from fitness.models import HabitLog
        return list(HabitLog.objects.filter(date=target_date))

    def upsert_habitlog(self, habit_id, date_str, completed):
        from fitness.models import HabitLog
        from datetime import date as _date
        d = _d(date_str)
        HabitLog.objects.update_or_create(
            habit_id=habit_id,
            date=d,
            defaults={"completed": completed},
        )

    def seed_default_habits(self):
        from fitness.models import Habit
        defaults = [
            {"name": "Go to sleep before 23:00", "description": "Get enough rest for better recovery", "is_suggested": True, "order": 1},
            {"name": "Read a book", "description": "At least 15–30 minutes of reading", "is_suggested": True, "order": 2},
            {"name": "Meditate", "description": "Mindfulness or breathing exercise", "is_suggested": True, "order": 3},
        ]
        for d in defaults:
            Habit.objects.get_or_create(name=d["name"], defaults=d)

    def get_checkins(self, limit=30):
        from fitness.models import DailyCheckin
        return list(DailyCheckin.objects.all()[:limit])

    def get_or_create_checkin(self, target_date):
        from fitness.models import DailyCheckin
        checkin, _ = DailyCheckin.objects.get_or_create(date=target_date)
        return checkin

    def get_checkin_today(self):
        from fitness.models import DailyCheckin
        return DailyCheckin.objects.filter(date=_date.today()).first()

    def save_checkin(self, pk, data):
        from fitness.models import DailyCheckin
        if pk:
            DailyCheckin.objects.filter(pk=pk).update(**data)
        else:
            DailyCheckin.objects.create(**data)

    def get_meals(self, limit=50):
        from fitness.models import Meal
        return list(Meal.objects.all()[:limit])

    def get_meals_today(self):
        from fitness.models import Meal
        return list(Meal.objects.filter(date=_date.today()))

    def get_meal(self, pk):
        from fitness.models import Meal
        try:
            return Meal.objects.get(pk=pk)
        except Meal.DoesNotExist:
            return None

    def create_meal(self, data):
        from fitness.models import Meal
        return Meal.objects.create(**data)

    def update_meal(self, pk, data):
        from fitness.models import Meal
        Meal.objects.filter(pk=pk).update(**data)
        return Meal.objects.get(pk=pk)

    def delete_meal(self, pk):
        from fitness.models import Meal
        Meal.objects.filter(pk=pk).delete()

    def get_sport_choices(self):
        from fitness.models import Workout
        return list(Workout.objects.values_list("sport", flat=True).distinct().order_by("sport"))


# ---------------------------------------------------------------------------
# Factory — call get_db() anywhere in the app
# ---------------------------------------------------------------------------

_backend = None


def get_db():
    global _backend
    if _backend is None:
        from django.conf import settings
        if getattr(settings, "SUPABASE_URL", "") and getattr(settings, "SUPABASE_API_KEY", ""):
            _backend = SupabaseBackend()
        else:
            _backend = ORMBackend()
    return _backend
