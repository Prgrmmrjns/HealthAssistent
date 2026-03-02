"""Seed default habits (Go to sleep before 23:00, Read a book, Meditate)."""
from django.core.management.base import BaseCommand
from fitness.db import get_db


class Command(BaseCommand):
    help = "Seed default suggested habits"

    def handle(self, *args, **options):
        db = get_db()
        db.seed_default_habits()
        self.stdout.write(self.style.SUCCESS("Default habits seeded."))
