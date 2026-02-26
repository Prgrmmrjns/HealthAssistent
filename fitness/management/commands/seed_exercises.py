"""
Seed the Exercise table from Garmin Connect's public exercise catalogue.

Usage:
    python manage.py seed_exercises
"""

import requests
from django.core.management.base import BaseCommand

from fitness.models import Exercise

GARMIN_EXERCISES_URL = "https://connect.garmin.com/web-data/exercises/Exercises.json"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

CARDIO_CATEGORIES = {"CARDIO", "RUN", "RUN_INDOOR", "BIKE_OUTDOOR", "INDOOR_BIKE", "ELLIPTICAL"}


class Command(BaseCommand):
    help = "Seed exercises from Garmin Connect web-data catalogue"

    def handle(self, *args, **options):
        self.stdout.write("Fetching exercises from Garmin Connect...")
        r = requests.get(GARMIN_EXERCISES_URL, timeout=30, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        data = r.json()

        categories = data.get("categories", {})
        created = 0
        skipped = 0

        for cat_id, cat_data in categories.items():
            exercises = cat_data.get("exercises", {})
            for ex_id, ex_info in exercises.items():
                display_name = ex_id.replace("_", " ").title()
                muscles = ex_info.get("primaryMuscles") or ex_info.get("secondaryMuscles") or []
                muscle = muscles[0].replace("_", " ").title() if muscles else "Full Body"

                if cat_id in CARDIO_CATEGORIES:
                    ex_type = "Cardio"
                elif cat_id == "WARM_UP":
                    ex_type = "Stretch"
                else:
                    ex_type = "Strength"

                _, is_new = Exercise.objects.get_or_create(
                    name=display_name,
                    defaults={
                        "garmin_category": cat_id,
                        "garmin_name": ex_id,
                        "muscle_group": muscle,
                        "equipment": "Other",
                        "exercise_type": ex_type,
                    },
                )
                if is_new:
                    created += 1
                else:
                    skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. {created} exercises created, {skipped} already existed."
        ))
