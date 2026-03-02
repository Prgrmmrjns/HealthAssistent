import json
from datetime import date, timedelta

from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from fitness.models import SPORT_CHOICES
from .db import get_db


# ---------------------------------------------------------------------------
# Garmin sync
# ---------------------------------------------------------------------------

@require_POST
def sync_now(request):
    """Trigger an immediate Garmin sync in the background and redirect back."""
    from fitness.background import trigger_sync
    full = request.POST.get("full") == "1"
    trigger_sync(days=30, full_history=full)
    return redirect(request.POST.get("next") or "fitness:profile")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def dashboard(request):
    db = get_db()
    profile = db.get_profile()
    recent_workouts = db.get_workouts(limit=8)
    total_workouts = db.count_workouts()
    sports = db.workout_sports_breakdown()
    strength_count = db.count_workouts(sport="Strength Training")
    total_sets = db.count_active_sets()
    avg_duration = db.avg_workout_duration()

    latest_stats = db.get_latest_stats()
    latest_weight = db.get_latest_with_field("weight_kg")
    latest_vo2 = db.get_latest_with_field("vo2_max")
    steps_7d = db.get_steps_last_n_days(7)

    today_checkin = db.get_checkin_today()
    today_meals = db.get_meals_today()
    today_cals = sum(m.calories_est or 0 for m in today_meals)

    return render(request, "fitness/dashboard.html", {
        "profile": profile,
        "recent_workouts": recent_workouts,
        "total_workouts": total_workouts,
        "sports": sports,
        "strength_count": strength_count,
        "total_sets": total_sets,
        "avg_duration": avg_duration,
        "latest_stats": latest_stats,
        "latest_weight": latest_weight,
        "latest_vo2": latest_vo2,
        "steps_7d": steps_7d,
        "today_checkin": today_checkin,
        "today_meals": today_meals,
        "today_cals": today_cals,
    })


# ---------------------------------------------------------------------------
# Workouts
# ---------------------------------------------------------------------------

def workout_list(request):
    db = get_db()
    sport_filter = request.GET.get("sport", "")
    workouts = db.get_workouts_with_set_count(sport=sport_filter if sport_filter else None)
    sports = db.get_sport_choices()
    return render(request, "fitness/workout_list.html", {
        "workouts": workouts,
        "sports": sports,
        "current_sport": sport_filter,
    })


def workout_detail(request, pk):
    db = get_db()
    workout = db.get_workout(pk)
    if workout is None:
        raise Http404("Workout not found")

    sets = workout.sets.exclude(set_type="Rest")

    exercise_summary = {}
    for s in sets:
        key = s.exercise
        if key not in exercise_summary:
            exercise_summary[key] = {"sets": 0, "total_reps": 0, "max_weight": None}
        exercise_summary[key]["sets"] += 1
        if s.reps:
            exercise_summary[key]["total_reps"] += s.reps
        if s.weight_kg is not None:
            cur = exercise_summary[key]["max_weight"]
            if cur is None or s.weight_kg > cur:
                exercise_summary[key]["max_weight"] = s.weight_kg

    return render(request, "fitness/workout_detail.html", {
        "workout": workout,
        "sets": sets,
        "exercise_summary": exercise_summary,
    })


# ---------------------------------------------------------------------------
# Exercises
# ---------------------------------------------------------------------------

def exercise_list(request):
    db = get_db()
    category_filter = request.GET.get("category", "")
    muscle_filter = request.GET.get("muscle", "")
    q = request.GET.get("q", "")

    exercises = db.get_exercises(
        category=category_filter or None,
        muscle=muscle_filter or None,
        q=q or None,
    )
    total = db.count_exercises(
        category=category_filter or None,
        muscle=muscle_filter or None,
        q=q or None,
    )
    categories = db.get_exercise_categories()
    muscles = db.get_exercise_muscles()

    return render(request, "fitness/exercise_list.html", {
        "exercises": exercises,
        "total": total,
        "categories": categories,
        "muscles": muscles,
        "current_category": category_filter,
        "current_muscle": muscle_filter,
        "q": q,
    })


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------

def progress(request):
    db = get_db()
    days = int(request.GET.get("days", 30))
    from_date = date.today() - timedelta(days=days)
    stats = db.get_stats_range(from_date)

    def _iso(v):
        return v.isoformat() if hasattr(v, "isoformat") else str(v)

    chart_data = {
        "dates": [_iso(s.date) for s in stats],
        "steps": [getattr(s, "steps", None) for s in stats],
        "weight": [getattr(s, "weight_kg", None) for s in stats],
        "resting_hr": [getattr(s, "resting_hr", None) for s in stats],
        "sleep": [getattr(s, "sleep_hours", None) for s in stats],
        "vo2_max": [getattr(s, "vo2_max", None) for s in stats],
        "stress": [getattr(s, "avg_stress", None) for s in stats],
        "body_battery_high": [getattr(s, "body_battery_high", None) for s in stats],
        "body_battery_low": [getattr(s, "body_battery_low", None) for s in stats],
        "calories": [getattr(s, "total_calories", None) for s in stats],
        "hrv": [getattr(s, "hrv", None) for s in stats],
    }

    return render(request, "fitness/progress.html", {
        "chart_data": json.dumps(chart_data),
        "days": days,
    })


# ---------------------------------------------------------------------------
# Planner (templates + scheduled workouts)
# ---------------------------------------------------------------------------

def planner_list(request):
    """Planner overview: templates, exercises, schedule."""
    db = get_db()
    total_exercises = db.count_exercises()
    return render(request, "fitness/planner_list.html", {"total_exercises": total_exercises})


def template_list(request):
    db = get_db()
    templates = db.get_templates()
    return render(request, "fitness/template_list.html", {"templates": templates})


def template_create(request):
    db = get_db()
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        sport = request.POST.get("sport", "Strength Training")
        if not name:
            return render(request, "fitness/template_form.html", {
                "error": "Name is required.",
                "exercises": db.get_exercises_for_template(),
                "sport_choices": SPORT_CHOICES,
            })
        template = db.create_template(name, description, sport=sport)
        _save_template_exercises(request, template.id if hasattr(template, "id") else template.pk, db)
        pk = template.id if hasattr(template, "id") else template.pk
        return redirect("fitness:template_detail", pk=pk)

    return render(request, "fitness/template_form.html", {
        "exercises": db.get_exercises_for_template(),
        "sport_choices": SPORT_CHOICES,
    })


def template_edit(request, pk):
    db = get_db()
    template = db.get_template(pk)
    if template is None:
        raise Http404("Template not found")

    if request.method == "POST":
        name = request.POST.get("name", "").strip() or getattr(template, "name", "")
        description = request.POST.get("description", "").strip()
        sport = request.POST.get("sport", getattr(template, "sport", "Strength Training"))
        db.update_template(pk, name, description, sport=sport)
        db.delete_template_exercises(pk)
        _save_template_exercises(request, pk, db)
        return redirect("fitness:template_detail", pk=pk)

    return render(request, "fitness/template_form.html", {
        "template": template,
        "exercises": db.get_exercises_for_template(),
        "sport_choices": SPORT_CHOICES,
    })


def template_detail(request, pk):
    db = get_db()
    template = db.get_template(pk)
    if template is None:
        raise Http404("Template not found")
    exercises = template.exercises.select_related("exercise").all()
    return render(request, "fitness/template_detail.html", {
        "template": template,
        "exercises": exercises,
    })


@require_POST
def template_delete(request, pk):
    db = get_db()
    db.delete_template(pk)
    return redirect("fitness:template_list")


# --- Scheduled workouts (date + time, Garmin sync) ---

def planned_list(request):
    db = get_db()
    today = date.today()
    from_date = today - timedelta(days=7)
    to_date = today + timedelta(days=90)
    planned = db.get_planned_workouts(from_date=from_date, to_date=to_date)
    profile = db.get_profile()
    return render(request, "fitness/planned_list.html", {
        "planned_workouts": planned,
        "has_garmin": getattr(profile, "garmin_connected", False),
    })


def planned_add(request):
    db = get_db()
    templates = db.get_templates()
    pre_template_id = request.GET.get("template_id", "").strip()
    pre_template = None
    if pre_template_id:
        try:
            pre_template = db.get_template(int(pre_template_id))
        except (ValueError, TypeError):
            pass

    if request.method == "POST":
        d = request.POST.get("date", str(date.today()))
        t = request.POST.get("time", "").strip()
        sport = request.POST.get("sport", "Other")
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        duration = request.POST.get("duration_min", "").strip()
        distance = request.POST.get("distance_km", "").strip()
        template_id = request.POST.get("template_id", "").strip()
        notes = request.POST.get("notes", "").strip()
        if not name:
            return render(request, "fitness/planned_form.html", {
                "error": "Name is required.",
                "sport_choices": SPORT_CHOICES,
                "templates": templates,
                "today": date.today(),
            })
        data = {"date": d, "sport": sport, "name": name, "description": description, "notes": notes}
        if t:
            data["time"] = t
        if duration:
            data["duration_min"] = int(duration)
        if distance:
            data["distance_km"] = float(distance)
        if template_id:
            data["template_id"] = int(template_id)
        pw = db.create_planned_workout(data)
        pk = getattr(pw, "id", None) or getattr(pw, "pk", None)
        return redirect("fitness:planned_detail", pk=pk)

    # Pre-fill from template when scheduling from template_detail
    initial = {}
    pre_selected_template_id = None
    if pre_template:
        initial = {
            "name": getattr(pre_template, "name", ""),
            "sport": getattr(pre_template, "sport", "Strength Training"),
            "description": getattr(pre_template, "description", ""),
        }
        try:
            pre_selected_template_id = int(pre_template_id)
        except (ValueError, TypeError):
            pass

    return render(request, "fitness/planned_form.html", {
        "sport_choices": SPORT_CHOICES,
        "templates": templates,
        "today": date.today(),
        "initial": initial,
        "pre_selected_template_id": pre_selected_template_id or None,
    })


def planned_detail(request, pk):
    db = get_db()
    pw = db.get_planned_workout(pk)
    if pw is None:
        raise Http404("Planned workout not found")
    profile = db.get_profile()
    return render(request, "fitness/planned_detail.html", {
        "planned": pw,
        "has_garmin": getattr(profile, "garmin_connected", False),
    })


def planned_edit(request, pk):
    db = get_db()
    pw = db.get_planned_workout(pk)
    if pw is None:
        raise Http404("Planned workout not found")
    templates = db.get_templates()
    if request.method == "POST":
        data = {
            "date": request.POST.get("date", str(getattr(pw, "date", date.today()))),
            "sport": request.POST.get("sport", getattr(pw, "sport", "Other")),
            "name": request.POST.get("name", "").strip(),
            "description": request.POST.get("description", "").strip(),
            "notes": request.POST.get("notes", "").strip(),
        }
        t = request.POST.get("time", "").strip()
        data["time"] = t if t else None
        d = request.POST.get("duration_min", "").strip()
        data["duration_min"] = int(d) if d else None
        dist = request.POST.get("distance_km", "").strip()
        data["distance_km"] = float(dist) if dist else None
        tid = request.POST.get("template_id", "").strip()
        data["template_id"] = int(tid) if tid else None
        db.update_planned_workout(pk, data)
        return redirect("fitness:planned_detail", pk=pk)
    return render(request, "fitness/planned_form.html", {
        "planned": pw,
        "sport_choices": SPORT_CHOICES,
        "templates": templates,
        "today": date.today(),
        "initial": {},
        "pre_selected_template_id": None,
    })


@require_POST
def planned_delete(request, pk):
    db = get_db()
    db.delete_planned_workout(pk)
    return redirect("fitness:planned_list")


def planned_sync_garmin(request, pk):
    db = get_db()
    pw = db.get_planned_workout(pk)
    if pw is None:
        raise Http404("Planned workout not found")
    from fitness.garmin_schedule import schedule_to_garmin
    ok, msg = schedule_to_garmin(pw)
    if ok:
        db.update_planned_workout(pk, {"garmin_synced": True, "garmin_workout_id": str(msg)})
        from django.contrib import messages
        messages.success(request, "Synced to Garmin Connect.")
    else:
        from django.contrib import messages
        messages.warning(request, msg)
    return redirect("fitness:planned_detail", pk=pk)


def exercise_search_api(request):
    """JSON endpoint for live exercise search in the workout builder."""
    db = get_db()
    q = request.GET.get("q", "")
    if len(q) < 2:
        return JsonResponse({"results": []})
    results = db.search_exercises(q, exercise_type="Strength", limit=20)
    # Ensure we return plain dicts
    if results and hasattr(results[0], "__dict__"):
        results = [{"id": r.id, "name": r.name, "muscle_group": getattr(r, "muscle_group", "")} for r in results]
    return JsonResponse({"results": list(results)})


def _save_template_exercises(request, template_id, db):
    """Parse exercise rows from the POST and save them."""
    idx = 0
    while True:
        prefix = f"ex_{idx}_"
        exercise_id = request.POST.get(f"{prefix}exercise_id", "")
        custom_name = request.POST.get(f"{prefix}custom_name", "").strip()

        if not exercise_id and not custom_name:
            if idx > 50:
                break
            idx += 1
            if (not request.POST.get(f"ex_{idx}_exercise_id", "")
                    and not request.POST.get(f"ex_{idx}_custom_name", "")):
                break
            continue

        db.create_template_exercise({
            "template_id": template_id,
            "exercise_id": int(exercise_id) if exercise_id else None,
            "custom_name": custom_name if not exercise_id else "",
            "sets": int(request.POST.get(f"{prefix}sets", 3) or 3),
            "reps": int(request.POST.get(f"{prefix}reps", 10) or 10),
            "weight_kg": float(request.POST.get(f"{prefix}weight", 0) or 0) or None,
            "rest_sec": int(request.POST.get(f"{prefix}rest", 90) or 90),
            "notes": request.POST.get(f"{prefix}notes", "").strip(),
            "order": idx,
        })
        idx += 1


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def profile_view(request):
    db = get_db()
    profile = db.get_profile()
    if request.method == "POST":
        data = {
            "name": request.POST.get("name", "").strip(),
            "age": int(request.POST.get("age") or 0) or None,
            "gender": request.POST.get("gender", ""),
            "height_cm": float(request.POST.get("height_cm") or 0) or None,
            "weight_kg": float(request.POST.get("weight_kg") or 0) or None,
            "profession": request.POST.get("profession", "").strip(),
            "activity_level": request.POST.get("activity_level", ""),
            "health_conditions": request.POST.get("health_conditions", "").strip(),
            "goals": request.POST.get("goals", "").strip(),
        }
        if request.FILES.get("profile_image"):
            from .storage import upload_image
            url = upload_image(request.FILES["profile_image"], folder="profile")
            if url:
                data["profile_image"] = url
        db.save_profile(profile.pk, data)
        return redirect("fitness:profile")
    from fitness.background import last_sync_time
    return render(request, "fitness/profile.html", {
        "profile": profile,
        "last_sync": last_sync_time(),
    })


# ---------------------------------------------------------------------------
# Goals & Milestones
# ---------------------------------------------------------------------------

def goals_list(request):
    db = get_db()
    status = request.GET.get("status", "")
    goals = db.get_goals(status=status if status else None)
    return render(request, "fitness/goals_list.html", {"goals": goals, "current_status": status})


def goal_add(request):
    db = get_db()
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        target = request.POST.get("target_date", "").strip()
        if not name:
            return render(request, "fitness/goal_form.html", {"error": "Name is required.", "goal": None})
        g = db.create_goal({
            "name": name,
            "description": description,
            "target_date": target or None,
            "status": "active",
        })
        if g:
            return redirect("fitness:goal_detail", pk=g.pk or g.id)
    return render(request, "fitness/goal_form.html", {"goal": None})


def goal_detail(request, pk):
    db = get_db()
    goal = db.get_goal(pk)
    if goal is None:
        raise Http404("Goal not found")
    milestones = goal.milestones if hasattr(goal, "milestones") else getattr(goal, "_milestones", [])
    return render(request, "fitness/goal_detail.html", {"goal": goal, "milestones": milestones})


def goal_edit(request, pk):
    db = get_db()
    goal = db.get_goal(pk)
    if goal is None:
        raise Http404("Goal not found")
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        target = request.POST.get("target_date", "").strip()
        status = request.POST.get("status", "active")
        if name:
            db.update_goal(pk, {"name": name, "description": description, "target_date": target or None, "status": status})
            return redirect("fitness:goal_detail", pk=pk)
    return render(request, "fitness/goal_form.html", {"goal": goal})


@require_POST
def goal_delete(request, pk):
    db = get_db()
    db.delete_goal(pk)
    return redirect("fitness:goals_list")


def milestone_add(request, goal_pk):
    db = get_db()
    goal = db.get_goal(goal_pk)
    if goal is None:
        raise Http404("Goal not found")
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        target = request.POST.get("target_date", "").strip()
        if name:
            db.create_milestone({"goal_id": goal_pk, "name": name, "target_date": target or None})
            return redirect("fitness:goal_detail", pk=goal_pk)
    return render(request, "fitness/milestone_form.html", {"goal": goal})


def milestone_edit(request, pk):
    db = get_db()
    ms = db.get_milestone(pk)
    if ms is None:
        raise Http404("Milestone not found")
    goal = db.get_goal(getattr(ms, "goal_id", None))
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        target = request.POST.get("target_date", "").strip()
        completed = request.POST.get("completed") == "1"
        if name:
            from django.utils import timezone
            data = {"name": name, "target_date": target or None}
            data["completed_at"] = timezone.now() if completed else None
            db.update_milestone(pk, data)
            return redirect("fitness:goal_detail", pk=getattr(ms, "goal_id", 1))
    return render(request, "fitness/milestone_form.html", {"goal": goal, "milestone": ms})


@require_POST
def milestone_delete(request, pk):
    db = get_db()
    ms = db.get_milestone(pk)
    goal_pk = getattr(ms, "goal_id", 1) if ms else 1
    db.delete_milestone(pk)
    return redirect("fitness:goal_detail", pk=goal_pk)


# ---------------------------------------------------------------------------
# Habits
# ---------------------------------------------------------------------------

def habits_list(request):
    db = get_db()
    db.seed_default_habits()  # ensure defaults exist
    habits = db.get_habits()
    return render(request, "fitness/habits_list.html", {"habits": habits})


def habit_add(request):
    db = get_db()
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        if not name:
            return render(request, "fitness/habit_form.html", {"error": "Name is required.", "habit": None})
        h = db.create_habit({"name": name, "description": description, "is_suggested": False})
        if h:
            return redirect("fitness:habits_list")
    return render(request, "fitness/habit_form.html", {"habit": None})


def habit_edit(request, pk):
    db = get_db()
    habit = db.get_habit(pk)
    if habit is None:
        raise Http404("Habit not found")
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        if name:
            db.update_habit(pk, {"name": name, "description": description})
            return redirect("fitness:habits_list")
    return render(request, "fitness/habit_form.html", {"habit": habit})


@require_POST
def habit_delete(request, pk):
    db = get_db()
    db.delete_habit(pk)
    return redirect("fitness:habits_list")


# ---------------------------------------------------------------------------
# Daily Check-in
# ---------------------------------------------------------------------------

def checkin_list(request):
    db = get_db()
    checkins = db.get_checkins(limit=30)
    profile = db.get_profile()
    return render(request, "fitness/checkin_list.html", {
        "checkins": checkins,
        "has_garmin": getattr(profile, "garmin_connected", False),
    })


def checkin_form(request, date_str=None):
    db = get_db()
    target_date = date.fromisoformat(date_str) if date_str else date.today()
    profile = db.get_profile()
    checkin = db.get_or_create_checkin(target_date)
    db.seed_default_habits()  # ensure default habits exist
    habits = db.get_habits()
    habitlogs = {getattr(h, "habit_id", None): h for h in db.get_habitlogs_for_date(target_date)}

    if request.method == "POST":
        has_garmin = getattr(profile, "garmin_connected", False)
        update_data = {
            "mood": int(request.POST.get("mood") or 0) or None,
            "energy": int(request.POST.get("energy") or 0) or None,
            "stress": request.POST.get("stress", ""),
            "sleep_quality": int(request.POST.get("sleep_quality") or 0) or None,
            "hydration_litres": float(request.POST.get("hydration_litres") or 0) or None,
            "notes": request.POST.get("notes", "").strip(),
        }
        if not has_garmin:
            update_data.update({
                "sleep_hours_manual": float(request.POST.get("sleep_hours_manual") or 0) or None,
                "exercise_minutes": int(request.POST.get("exercise_minutes") or 0) or None,
                "steps_estimate": int(request.POST.get("steps_estimate") or 0) or None,
                "exercise_description": request.POST.get("exercise_description", "").strip(),
            })
        db.save_checkin(getattr(checkin, "id", None), update_data)
        # Save habit completions
        date_str_val = str(target_date)
        checked_ids = set(request.POST.getlist("habit"))
        for h in habits:
            hid = getattr(h, "id", None) or getattr(h, "pk", None)
            if hid:
                db.upsert_habitlog(hid, date_str_val, completed=(str(hid) in checked_ids))
        return redirect("fitness:checkin_list")

    return render(request, "fitness/checkin_form.html", {
        "checkin": checkin,
        "target_date": target_date,
        "has_garmin": getattr(profile, "garmin_connected", False),
        "habits": habits,
        "habitlogs": habitlogs,
    })


# ---------------------------------------------------------------------------
# Meals
# ---------------------------------------------------------------------------

def meal_list(request):
    db = get_db()
    meals = db.get_meals(limit=50)
    today_meals = db.get_meals_today()
    today_cals = sum(m.calories_est or 0 for m in today_meals)
    today_protein = sum(m.protein_g or 0 for m in today_meals)
    today_carbs = sum(m.carbs_g or 0 for m in today_meals)
    today_fat = sum(m.fat_g or 0 for m in today_meals)
    return render(request, "fitness/meal_list.html", {
        "meals": meals,
        "today_cals": today_cals,
        "today_protein": today_protein,
        "today_carbs": today_carbs,
        "today_fat": today_fat,
    })


def meal_add(request):
    db = get_db()
    if request.method == "POST":
        meal_date = request.POST.get("date") or str(date.today())
        meal_data = {
            "date": meal_date,
            "meal_type": request.POST.get("meal_type", "snack"),
            "description": request.POST.get("description", "").strip(),
        }

        # Read image bytes once; try to upload to storage, keep bytes for AI fallback
        image_bytes = None
        image_mime = "image/jpeg"
        image_url = None
        if request.FILES.get("image"):
            f = request.FILES["image"]
            image_bytes = f.read()
            image_mime = getattr(f, "content_type", "image/jpeg") or "image/jpeg"
            f.seek(0)
            from .storage import upload_image
            image_url = upload_image(f, folder="meals")
            if image_url:
                meal_data["image"] = image_url

        meal = db.create_meal(meal_data)
        if meal is None:
            return redirect("fitness:meal_list")

        meal_pk = getattr(meal, "id", None) or getattr(meal, "pk", None)

        # AI analysis — try URL first, then raw bytes, then text description
        from .ai import analyze_food_image, analyze_food_text
        result = None
        if image_url:
            try:
                result = analyze_food_image(image_url)
            except Exception:
                pass
        if not result and image_bytes:
            # Analyse directly from bytes (works even if storage upload failed)
            try:
                result = analyze_food_image(image_bytes, mime_hint=image_mime)
            except Exception:
                pass
        if not result and meal_data.get("description"):
            try:
                result = analyze_food_text(meal_data["description"])
            except Exception:
                pass

        if result and "error" not in result:
            update = {
                "calories_est": result.get("calories"),
                "protein_g": result.get("protein_g"),
                "carbs_g": result.get("carbs_g"),
                "fat_g": result.get("fat_g"),
                "fiber_g": result.get("fiber_g"),
                "ai_analysis": result.get("_raw", ""),
            }
            if not meal_data.get("description") and result.get("description"):
                update["description"] = result["description"]
            if meal_pk:
                meal = db.update_meal(meal_pk, update)

        if meal_pk:
            return redirect("fitness:meal_detail", pk=meal_pk)
        return redirect("fitness:meal_list")

    return render(request, "fitness/meal_form.html", {"today": date.today()})


def meal_detail(request, pk):
    db = get_db()
    meal = db.get_meal(pk)
    if meal is None:
        raise Http404("Meal not found")
    return render(request, "fitness/meal_detail.html", {"meal": meal})


@require_POST
def meal_delete(request, pk):
    db = get_db()
    db.delete_meal(pk)
    return redirect("fitness:meal_list")
