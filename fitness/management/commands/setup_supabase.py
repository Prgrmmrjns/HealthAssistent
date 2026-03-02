"""
One-shot setup command: create Supabase Storage bucket + run Django migrations.

Usage:
    python manage.py setup_supabase

Requires in .env:
    SUPABASE_URL   - https://xxx.supabase.co
    SUPABASE_API_KEY - service role key (sb_secret_...)
    SUPABASE_DB_URL  - PostgreSQL connection string (Project Settings → Database → URI)
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create Supabase Storage bucket + run Django migrations against Supabase"

    def handle(self, *args, **options):
        from fitness.storage import ensure_bucket_exists, _supabase_creds

        url, key = _supabase_creds()

        # 1. Storage bucket
        self.stdout.write("1. Setting up Supabase Storage bucket 'media'...")
        if not url or not key:
            self.stdout.write(self.style.WARNING(
                "   SUPABASE_URL / SUPABASE_API_KEY not set — skipping storage setup."
            ))
        elif ensure_bucket_exists():
            self.stdout.write(self.style.SUCCESS("   Bucket 'media' is ready (public)."))
        else:
            self.stdout.write(self.style.WARNING(
                "   Could not create bucket. Create it manually: Supabase → Storage → New Bucket → name 'media', public."
            ))

        # 2. Database migrations
        self.stdout.write("\n2. Running Django migrations against Supabase...")
        import os
        from django.conf import settings
        db_url = (
            os.environ.get("SUPABASE_DB_URL")
            or os.environ.get("DATABASE_URL")
        )
        if not db_url:
            self.stdout.write(self.style.ERROR(
                "   SUPABASE_DB_URL not set in .env — cannot run migrations.\n"
                "   Get it from: Supabase → Project Settings → Database → Connection string (URI)"
            ))
            return

        try:
            call_command("migrate", "--no-input", verbosity=1)
            self.stdout.write(self.style.SUCCESS("   Migrations complete."))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"   Migration failed: {exc}"))
            return

        self.stdout.write(self.style.SUCCESS(
            "\nAll done! Tables created in Supabase and storage bucket is ready."
        ))
