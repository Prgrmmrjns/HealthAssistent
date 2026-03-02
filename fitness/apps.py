import sys

from django.apps import AppConfig

# Don't spin up the background thread for these management commands
_SKIP_BG = {
    "migrate", "makemigrations", "collectstatic", "createsuperuser",
    "seed_exercises", "sync_garmin", "check", "shell", "dbshell",
    "showmigrations", "sqlmigrate", "flush", "loaddata", "dumpdata",
    "inspectdb", "test", "setup_supabase",
}


class FitnessConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fitness"

    def ready(self):
        cmd = sys.argv[1] if len(sys.argv) > 1 else ""
        if cmd in _SKIP_BG:
            return
        from fitness.background import start
        start()
