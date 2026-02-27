# Health Assistant

A Django fitness app that syncs Garmin data, tracks workouts, meals, and daily check-ins.

## Features

- **Dashboard** – Overview of workouts, daily stats, steps, and today’s meals
- **Garmin sync** – Import activities and daily stats from Garmin Connect
- **Workouts** – List and detail views for activities with exercise sets
- **Meals** – Meal logging with optional AI-powered nutrition estimates (Mistral)
- **Daily check-ins** – Mood, energy, sleep, and notes
- **Workout templates** – Reusable templates for strength training
- **Progress** – Track weight, VO2 max, and other metrics over time

## Setup

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/HealthAssistent.git
cd HealthAssistent
pip install -r requirements.txt
```

### 2. Environment variables

Copy the example env file and add your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `GARMIN_EMAIL` | Yes | Your Garmin Connect email |
| `GARMIN_PASSWORD` | Yes | Your Garmin Connect password |
| `DJANGO_SECRET_KEY` | For production | Secret key for Django (defaults to dev value if unset) |
| `MISTRAL_AI_API_KEY` | No | For AI meal analysis ([get key](https://console.mistral.ai/)) |

### 3. Database and run

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py sync_garmin --days 30
python manage.py runserver
```

Open http://127.0.0.1:8000 and log in. The fitness dashboard is at `/fitness/`.

## Management commands

| Command | Description |
|---------|-------------|
| `python manage.py sync_garmin` | Sync last 30 days from Garmin (use `--days N` for custom range) |
| `python manage.py seed_exercises` | Seed exercises from Garmin Connect catalogue |

## Deploy on Render

1. Create a **PostgreSQL** database in the Render dashboard.
2. Create a **Web Service** and connect your repo.
3. Link the PostgreSQL database to the web service (Render will set `DATABASE_URL` automatically).
4. Add environment variables: `GARMIN_EMAIL`, `GARMIN_PASSWORD`, and optionally `DJANGO_SECRET_KEY`, `MISTRAL_AI_API_KEY`.
5. Set these in the Render dashboard:
   - **Build Command:** `pip install -r requirements.txt && python manage.py collectstatic --no-input`
   - **Start Command:** `gunicorn config.wsgi:application`
   - **Release Command:** `python manage.py migrate --no-input`
6. Deploy.

## Project structure

- `config/` – Django project settings
- `fitness/` – Main app (models, views, templates, Garmin sync, AI helpers)
- `manage.py` – Django management script

## License

For personal use. Garmin Connect usage subject to Garmin’s Terms of Service.
