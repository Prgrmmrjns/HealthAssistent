import json
from datetime import date

from django.db.models import Avg, Count, Max, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import (
    DailyCheckin,
    DailyStats,
    Exercise,
    Meal,
    TemplateExercise,
    UserProfile,
    Workout,
    WorkoutSet,
    WorkoutTemplate,
)


def dashboard(request):
    profile = UserProfile.get()
    recent_workouts = Workout.objects.all()[:8]
    total_workouts = Workout.objects.count()
    sports = (
        Workout.objects.values("sport")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    strength_count = Workout.objects.filter(sport="Strength Training").count()
    total_sets = WorkoutSet.objects.filter(set_type="Active").count()
    avg_duration = Workout.objects.aggregate(avg=Avg("duration_min"))["avg"]

    latest_stats = DailyStats.objects.first()
    latest_weight = DailyStats.objects.exclude(weight_kg=None).order_by("-date").first()
    latest_vo2 = DailyStats.objects.exclude(vo2_max=None).order_by("-date").first()

    steps_7d = list(
        DailyStats.objects.exclude(steps=None)
        .order_by("-date")[:7]
        .values_list("date", "steps")
    )
    steps_7d.reverse()

    today_checkin = DailyCheckin.objects.filter(date=date.today()).first()
    today_meals = Meal.objects.filter(date=date.today())
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


def workout_list(request):
    sport_filter = request.GET.get("sport", "")
    workouts = Workout.objects.all()
    if sport_filter:
        workouts = workouts.filter(sport=sport_filter)

    sports = (
        Workout.objects.values_list("sport", flat=True)
        .distinct()
        .order_by("sport")
    )

    workouts = workouts.annotate(
        set_count=Count("sets", filter=~Q(sets__set_type="Rest")),
    )

    return render(request, "fitness/workout_list.html", {
        "workouts": workouts,
        "sports": sports,
        "current_sport": sport_filter,
    })


def workout_detail(request, pk):
    workout = get_object_or_404(Workout, pk=pk)
    sets = workout.sets.exclude(set_type="Rest")

    exercise_summary = {}
    for s in sets:
        if s.exercise not in exercise_summary:
            exercise_summary[s.exercise] = {"sets": 0, "total_reps": 0, "max_weight": None}
        exercise_summary[s.exercise]["sets"] += 1
        if s.reps:
            exercise_summary[s.exercise]["total_reps"] += s.reps
        if s.weight_kg is not None:
            cur = exercise_summary[s.exercise]["max_weight"]
            if cur is None or s.weight_kg > cur:
                exercise_summary[s.exercise]["max_weight"] = s.weight_kg

    return render(request, "fitness/workout_detail.html", {
        "workout": workout,
        "sets": sets,
        "exercise_summary": exercise_summary,
    })


def exercise_list(request):
    category_filter = request.GET.get("category", "")
    muscle_filter = request.GET.get("muscle", "")
    q = request.GET.get("q", "")

    exercises = Exercise.objects.all()
    if category_filter:
        exercises = exercises.filter(garmin_category=category_filter)
    if muscle_filter:
        exercises = exercises.filter(muscle_group=muscle_filter)
    if q:
        exercises = exercises.filter(name__icontains=q)

    categories = (
        Exercise.objects.values_list("garmin_category", flat=True)
        .distinct()
        .order_by("garmin_category")
    )
    muscles = (
        Exercise.objects.values_list("muscle_group", flat=True)
        .distinct()
        .order_by("muscle_group")
    )

    return render(request, "fitness/exercise_list.html", {
        "exercises": exercises[:200],
        "total": exercises.count(),
        "categories": categories,
        "muscles": muscles,
        "current_category": category_filter,
        "current_muscle": muscle_filter,
        "q": q,
    })


# ---------------------------------------------------------------------------
# Progress page
# ---------------------------------------------------------------------------

def progress(request):
    days = int(request.GET.get("days", 30))
    stats = list(
        DailyStats.objects.order_by("date")
        .filter(date__gte=__import__("datetime").date.today() - __import__("datetime").timedelta(days=days))
        .values()
    )

    chart_data = {
        "dates": [s["date"].isoformat() for s in stats],
        "steps": [s["steps"] for s in stats],
        "weight": [s["weight_kg"] for s in stats],
        "resting_hr": [s["resting_hr"] for s in stats],
        "sleep": [s["sleep_hours"] for s in stats],
        "vo2_max": [s["vo2_max"] for s in stats],
        "stress": [s["avg_stress"] for s in stats],
        "body_battery_high": [s["body_battery_high"] for s in stats],
        "body_battery_low": [s["body_battery_low"] for s in stats],
        "calories": [s["total_calories"] for s in stats],
        "hrv": [s["hrv"] for s in stats],
    }

    return render(request, "fitness/progress.html", {
        "chart_data": json.dumps(chart_data),
        "days": days,
    })


# ---------------------------------------------------------------------------
# Workout templates (builder)
# ---------------------------------------------------------------------------

def template_list(request):
    templates = WorkoutTemplate.objects.prefetch_related("exercises__exercise").all()
    return render(request, "fitness/template_list.html", {"templates": templates})


def template_create(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        if not name:
            return render(request, "fitness/template_form.html", {
                "error": "Name is required.",
                "exercises": Exercise.objects.filter(exercise_type="Strength")[:500],
            })

        template = WorkoutTemplate.objects.create(name=name, description=description)
        _save_template_exercises(request, template)
        return redirect("fitness:template_detail", pk=template.pk)

    return render(request, "fitness/template_form.html", {
        "exercises": Exercise.objects.filter(exercise_type="Strength")[:500],
    })


def template_edit(request, pk):
    template = get_object_or_404(WorkoutTemplate, pk=pk)

    if request.method == "POST":
        template.name = request.POST.get("name", "").strip() or template.name
        template.description = request.POST.get("description", "").strip()
        template.save()
        template.exercises.all().delete()
        _save_template_exercises(request, template)
        return redirect("fitness:template_detail", pk=template.pk)

    return render(request, "fitness/template_form.html", {
        "template": template,
        "exercises": Exercise.objects.filter(exercise_type="Strength")[:500],
    })


def template_detail(request, pk):
    template = get_object_or_404(WorkoutTemplate, pk=pk)
    exercises = template.exercises.select_related("exercise").all()
    return render(request, "fitness/template_detail.html", {
        "template": template,
        "exercises": exercises,
    })


@require_POST
def template_delete(request, pk):
    template = get_object_or_404(WorkoutTemplate, pk=pk)
    template.delete()
    return redirect("fitness:template_list")


def exercise_search_api(request):
    """JSON endpoint for live exercise search in the workout builder."""
    q = request.GET.get("q", "")
    if len(q) < 2:
        return JsonResponse({"results": []})
    exercises = Exercise.objects.filter(
        name__icontains=q, exercise_type="Strength"
    ).values("id", "name", "muscle_group")[:20]
    return JsonResponse({"results": list(exercises)})


def _save_template_exercises(request, template):
    """Parse exercise rows from the form POST and save them."""
    idx = 0
    while True:
        prefix = f"ex_{idx}_"
        exercise_id = request.POST.get(f"{prefix}exercise_id", "")
        custom_name = request.POST.get(f"{prefix}custom_name", "").strip()

        if not exercise_id and not custom_name:
            if idx > 50:
                break
            idx += 1
            # Check if there are more after a gap
            if not request.POST.get(f"ex_{idx}_exercise_id", "") and not request.POST.get(f"ex_{idx}_custom_name", ""):
                break
            continue

        exercise_obj = None
        if exercise_id:
            try:
                exercise_obj = Exercise.objects.get(pk=int(exercise_id))
            except (Exercise.DoesNotExist, ValueError):
                pass

        TemplateExercise.objects.create(
            template=template,
            exercise=exercise_obj,
            custom_name=custom_name if not exercise_obj else "",
            sets=int(request.POST.get(f"{prefix}sets", 3) or 3),
            reps=int(request.POST.get(f"{prefix}reps", 10) or 10),
            weight_kg=float(request.POST.get(f"{prefix}weight", 0) or 0) or None,
            rest_sec=int(request.POST.get(f"{prefix}rest", 90) or 90),
            notes=request.POST.get(f"{prefix}notes", "").strip(),
            order=idx,
        )
        idx += 1


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def profile_view(request):
    profile = UserProfile.get()
    if request.method == "POST":
        profile.name = request.POST.get("name", "").strip()
        profile.age = int(request.POST.get("age") or 0) or None
        profile.gender = request.POST.get("gender", "")
        profile.height_cm = float(request.POST.get("height_cm") or 0) or None
        profile.weight_kg = float(request.POST.get("weight_kg") or 0) or None
        profile.profession = request.POST.get("profession", "").strip()
        profile.activity_level = request.POST.get("activity_level", "")
        profile.health_conditions = request.POST.get("health_conditions", "").strip()
        profile.goals = request.POST.get("goals", "").strip()
        if request.FILES.get("profile_image"):
            profile.profile_image = request.FILES["profile_image"]
        profile.save()
        return redirect("fitness:profile")
    return render(request, "fitness/profile.html", {"profile": profile})


# ---------------------------------------------------------------------------
# Daily Check-in
# ---------------------------------------------------------------------------

def checkin_list(request):
    checkins = DailyCheckin.objects.all()[:30]
    profile = UserProfile.get()
    return render(request, "fitness/checkin_list.html", {
        "checkins": checkins,
        "has_garmin": profile.garmin_connected,
    })


def checkin_form(request, date_str=None):
    target_date = date.fromisoformat(date_str) if date_str else date.today()
    profile = UserProfile.get()
    checkin, _ = DailyCheckin.objects.get_or_create(date=target_date)

    if request.method == "POST":
        checkin.mood = int(request.POST.get("mood") or 0) or None
        checkin.energy = int(request.POST.get("energy") or 0) or None
        checkin.stress = request.POST.get("stress", "")
        checkin.sleep_quality = int(request.POST.get("sleep_quality") or 0) or None
        checkin.hydration_litres = float(request.POST.get("hydration_litres") or 0) or None
        checkin.notes = request.POST.get("notes", "").strip()
        if not profile.garmin_connected:
            checkin.sleep_hours_manual = float(request.POST.get("sleep_hours_manual") or 0) or None
            checkin.exercise_minutes = int(request.POST.get("exercise_minutes") or 0) or None
            checkin.steps_estimate = int(request.POST.get("steps_estimate") or 0) or None
            checkin.exercise_description = request.POST.get("exercise_description", "").strip()
        checkin.save()
        return redirect("fitness:checkin_list")

    return render(request, "fitness/checkin_form.html", {
        "checkin": checkin,
        "target_date": target_date,
        "has_garmin": profile.garmin_connected,
    })


# ---------------------------------------------------------------------------
# Meals
# ---------------------------------------------------------------------------

def meal_list(request):
    meals = Meal.objects.all()[:50]
    today_meals = Meal.objects.filter(date=date.today())
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
    if request.method == "POST":
        meal = Meal(
            date=request.POST.get("date") or date.today(),
            meal_type=request.POST.get("meal_type", "snack"),
            description=request.POST.get("description", "").strip(),
        )
        if request.FILES.get("image"):
            meal.image = request.FILES["image"]
        meal.save()

        # AI analysis
        from .ai import analyze_food_image, analyze_food_text
        result = None
        if meal.image:
            try:
                result = analyze_food_image(meal.image.path)
            except Exception:
                pass
        if not result and meal.description:
            try:
                result = analyze_food_text(meal.description)
            except Exception:
                pass

        if result and "error" not in result:
            meal.calories_est = result.get("calories")
            meal.protein_g = result.get("protein_g")
            meal.carbs_g = result.get("carbs_g")
            meal.fat_g = result.get("fat_g")
            meal.fiber_g = result.get("fiber_g")
            meal.ai_analysis = result.get("_raw", "")
            if not meal.description and result.get("description"):
                meal.description = result["description"]
            meal.save()

        return redirect("fitness:meal_detail", pk=meal.pk)

    return render(request, "fitness/meal_form.html", {"today": date.today()})


def meal_detail(request, pk):
    meal = get_object_or_404(Meal, pk=pk)
    return render(request, "fitness/meal_detail.html", {"meal": meal})


@require_POST
def meal_delete(request, pk):
    meal = get_object_or_404(Meal, pk=pk)
    meal.delete()
    return redirect("fitness:meal_list")
