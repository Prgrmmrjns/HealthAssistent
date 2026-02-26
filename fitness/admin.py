from django.contrib import admin

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


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ["name", "garmin_category", "muscle_group", "equipment", "exercise_type"]
    list_filter = ["garmin_category", "muscle_group", "exercise_type"]
    search_fields = ["name", "garmin_name"]


class WorkoutSetInline(admin.TabularInline):
    model = WorkoutSet
    extra = 0


@admin.register(Workout)
class WorkoutAdmin(admin.ModelAdmin):
    list_display = ["name", "date", "sport", "duration_min", "calories", "avg_hr"]
    list_filter = ["sport", "date"]
    search_fields = ["name"]
    inlines = [WorkoutSetInline]


@admin.register(WorkoutSet)
class WorkoutSetAdmin(admin.ModelAdmin):
    list_display = ["workout", "order", "exercise", "set_type", "reps", "weight_kg"]
    list_filter = ["set_type"]


@admin.register(DailyStats)
class DailyStatsAdmin(admin.ModelAdmin):
    list_display = ["date", "steps", "weight_kg", "resting_hr", "sleep_hours", "vo2_max", "avg_stress"]
    list_filter = ["date"]


class TemplateExerciseInline(admin.TabularInline):
    model = TemplateExercise
    extra = 0


@admin.register(WorkoutTemplate)
class WorkoutTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "exercise_count", "total_sets", "updated_at"]
    inlines = [TemplateExerciseInline]


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["name", "age", "gender", "profession", "garmin_connected"]


@admin.register(DailyCheckin)
class DailyCheckinAdmin(admin.ModelAdmin):
    list_display = ["date", "mood", "energy", "stress", "sleep_quality", "hydration_litres"]
    list_filter = ["date", "stress"]


@admin.register(Meal)
class MealAdmin(admin.ModelAdmin):
    list_display = ["date", "meal_type", "description", "calories_est", "protein_g", "carbs_g", "fat_g"]
    list_filter = ["meal_type", "date"]
    search_fields = ["description"]
