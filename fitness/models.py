from django.db import models


class Exercise(models.Model):
    name = models.CharField(max_length=200, unique=True)
    garmin_category = models.CharField(max_length=100, db_index=True)
    garmin_name = models.CharField(max_length=200, db_index=True)
    muscle_group = models.CharField(max_length=100, blank=True, default="")
    equipment = models.CharField(max_length=100, blank=True, default="Other")
    exercise_type = models.CharField(
        max_length=20,
        choices=[("Strength", "Strength"), ("Cardio", "Cardio"), ("Stretch", "Stretch")],
        default="Strength",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Workout(models.Model):
    garmin_activity_id = models.BigIntegerField(unique=True, null=True, blank=True)
    name = models.CharField(max_length=200)
    date = models.DateField(db_index=True)
    sport = models.CharField(max_length=50, db_index=True)
    duration_min = models.FloatField(null=True, blank=True)
    distance_km = models.FloatField(null=True, blank=True)
    calories = models.FloatField(null=True, blank=True)
    avg_hr = models.FloatField(null=True, blank=True)
    max_hr = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.name} ({self.date})"

    @property
    def active_sets(self):
        return self.sets.exclude(set_type="Rest")


class WorkoutSet(models.Model):
    workout = models.ForeignKey(Workout, on_delete=models.CASCADE, related_name="sets")
    exercise = models.CharField(max_length=200)
    set_type = models.CharField(
        max_length=20,
        choices=[("Active", "Active"), ("Warmup", "Warmup"), ("Rest", "Rest")],
        default="Active",
    )
    reps = models.IntegerField(null=True, blank=True)
    weight_kg = models.FloatField(null=True, blank=True)
    duration_sec = models.FloatField(null=True, blank=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        parts = [self.exercise]
        if self.reps is not None:
            parts.append(f"{self.reps} reps")
        if self.weight_kg is not None:
            parts.append(f"{self.weight_kg} kg")
        return " — ".join(parts)


class DailyStats(models.Model):
    date = models.DateField(unique=True, db_index=True)
    steps = models.IntegerField(null=True, blank=True)
    total_calories = models.IntegerField(null=True, blank=True)
    active_calories = models.IntegerField(null=True, blank=True)
    resting_hr = models.IntegerField(null=True, blank=True)
    avg_stress = models.IntegerField(null=True, blank=True)
    body_battery_high = models.IntegerField(null=True, blank=True)
    body_battery_low = models.IntegerField(null=True, blank=True)
    sleep_hours = models.FloatField(null=True, blank=True)
    hrv = models.FloatField(null=True, blank=True)
    weight_kg = models.FloatField(null=True, blank=True)
    vo2_max = models.FloatField(null=True, blank=True)
    floors_climbed = models.IntegerField(null=True, blank=True)
    intensity_minutes = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "Daily stats"

    def __str__(self):
        return f"Stats {self.date}"


# Sport types for Planner (matches Garmin activity types)
SPORT_CHOICES = [
    ("Strength Training", "Strength Training"),
    ("Running", "Running"),
    ("Cycling", "Cycling"),
    ("Swimming", "Swimming"),
    ("Walking", "Walking"),
    ("Hiking", "Hiking"),
    ("Yoga", "Yoga"),
    ("Other", "Other"),
]


class WorkoutTemplate(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    sport = models.CharField(max_length=50, choices=SPORT_CHOICES, default="Strength Training")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name

    @property
    def exercise_count(self):
        return self.exercises.count()

    @property
    def total_sets(self):
        return sum(e.sets for e in self.exercises.all())


class PlannedWorkout(models.Model):
    """Scheduled workout for a specific date and time (synced to Garmin when possible)."""
    date = models.DateField(db_index=True)
    time = models.TimeField(null=True, blank=True, help_text="Optional scheduled time")
    sport = models.CharField(max_length=50, choices=SPORT_CHOICES)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    duration_min = models.IntegerField(null=True, blank=True, help_text="Planned duration in minutes")
    distance_km = models.FloatField(null=True, blank=True, help_text="Planned distance (e.g. for Running)")
    template = models.ForeignKey(
        WorkoutTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name="planned"
    )
    garmin_synced = models.BooleanField(default=False)
    garmin_workout_id = models.CharField(max_length=100, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "time", "created_at"]

    def __str__(self):
        return f"{self.name} — {self.date}"


class TemplateExercise(models.Model):
    template = models.ForeignKey(WorkoutTemplate, on_delete=models.CASCADE, related_name="exercises")
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, null=True, blank=True)
    custom_name = models.CharField(max_length=200, blank=True, default="")
    sets = models.IntegerField(default=3)
    reps = models.IntegerField(default=10)
    weight_kg = models.FloatField(null=True, blank=True)
    rest_sec = models.IntegerField(default=90)
    notes = models.CharField(max_length=300, blank=True, default="")
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        if self.exercise:
            return self.exercise.name
        return self.custom_name or "Unnamed"


# ---------------------------------------------------------------------------
# LISA: Lifestyle features
# ---------------------------------------------------------------------------

GENDER_CHOICES = [("M", "Male"), ("F", "Female"), ("O", "Other"), ("", "Prefer not to say")]
ACTIVITY_CHOICES = [
    ("sedentary", "Sedentary"), ("light", "Lightly Active"),
    ("moderate", "Moderately Active"), ("active", "Very Active"),
]


class UserProfile(models.Model):
    """Singleton profile — only one row ever exists."""
    name = models.CharField(max_length=120, blank=True, default="")
    age = models.IntegerField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True, default="")
    height_cm = models.FloatField(null=True, blank=True)
    weight_kg = models.FloatField(null=True, blank=True)
    profession = models.CharField(max_length=200, blank=True, default="")
    activity_level = models.CharField(max_length=20, choices=ACTIVITY_CHOICES, blank=True, default="")
    health_conditions = models.TextField(blank=True, default="", help_text="Allergies, chronic conditions, medications, etc.")
    goals = models.TextField(blank=True, default="", help_text="Weight loss, muscle gain, better sleep, etc.")
    profile_image = models.CharField(max_length=500, blank=True, default="")
    garmin_connected = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "User profile"

    def __str__(self):
        return self.name or "My Profile"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


MOOD_CHOICES = [(i, str(i)) for i in range(1, 6)]
STRESS_CHOICES = [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("very_high", "Very High")]


class DailyCheckin(models.Model):
    date = models.DateField(unique=True, db_index=True)
    mood = models.IntegerField(choices=MOOD_CHOICES, null=True, blank=True, help_text="1 = very bad, 5 = great")
    energy = models.IntegerField(choices=MOOD_CHOICES, null=True, blank=True, help_text="1 = exhausted, 5 = energised")
    stress = models.CharField(max_length=20, choices=STRESS_CHOICES, blank=True, default="")
    sleep_quality = models.IntegerField(choices=MOOD_CHOICES, null=True, blank=True, help_text="1 = terrible, 5 = excellent")
    sleep_hours_manual = models.FloatField(null=True, blank=True, help_text="Only when Garmin not connected")
    hydration_litres = models.FloatField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    # Compensatory fields when no Garmin
    exercise_minutes = models.IntegerField(null=True, blank=True, help_text="Total exercise minutes (no Garmin)")
    steps_estimate = models.IntegerField(null=True, blank=True, help_text="Estimated steps (no Garmin)")
    exercise_description = models.TextField(blank=True, default="", help_text="What activity did you do?")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"Check-in {self.date}"


MEAL_TYPE_CHOICES = [
    ("breakfast", "Breakfast"), ("lunch", "Lunch"),
    ("dinner", "Dinner"), ("snack", "Snack"),
]


class Meal(models.Model):
    date = models.DateField(db_index=True)
    meal_type = models.CharField(max_length=20, choices=MEAL_TYPE_CHOICES)
    description = models.TextField(blank=True, default="")
    image = models.CharField(max_length=500, blank=True, default="")
    # AI-estimated macros
    calories_est = models.IntegerField(null=True, blank=True)
    protein_g = models.FloatField(null=True, blank=True)
    carbs_g = models.FloatField(null=True, blank=True)
    fat_g = models.FloatField(null=True, blank=True)
    fiber_g = models.FloatField(null=True, blank=True)
    ai_analysis = models.TextField(blank=True, default="", help_text="Full AI response")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.get_meal_type_display()} — {self.date}"


# ---------------------------------------------------------------------------
# Goals, Milestones, Habits
# ---------------------------------------------------------------------------

GOAL_STATUS_CHOICES = [
    ("active", "Active"),
    ("completed", "Completed"),
    ("archived", "Archived"),
]


class Goal(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    target_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=GOAL_STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Milestone(models.Model):
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="milestones")
    name = models.CharField(max_length=200)
    target_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["target_date", "created_at"]

    def __str__(self):
        return self.name


class Habit(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    is_suggested = models.BooleanField(default=False, help_text="Pre-defined suggested habit")
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class HabitLog(models.Model):
    habit = models.ForeignKey(Habit, on_delete=models.CASCADE, related_name="logs")
    date = models.DateField(db_index=True)
    completed = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        unique_together = [("habit", "date")]

    def __str__(self):
        return f"{self.habit.name} — {self.date}"
