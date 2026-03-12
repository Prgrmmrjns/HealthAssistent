# Garmin + Meals → Notion

Sync Garmin Connect daily metrics into a Notion database. Optionally analyze meal photos with Mistral AI (name, macros, kcals, meal components). **Modular:** you can run **Garmin-only** (no Meals, no LLM cost, works on Notion Free) or enable Meals via `params.py`.

- **Garmin sync** – Always runs. One database **📊 Garmin Daily** is created under your Notion page; one row per day.
- **Meals analysis** – Only if `RUN_MEAL_ANALYSIS=True`. Creates **🍽️ Meals** DB and uses Mistral to analyze meal images. Requires a **Notion Plus / Education Plus** plan (image uploads) and a **Mistral API key** (paid usage).

---

## 1. What to do in Notion first

### 1.1 Create a Notion integration

1. Go to [Notion Integrations](https://www.notion.so/my-integrations).
2. Click **+ New integration**.
3. Name it (e.g. “Garmin Meals Sync”), select your workspace, then click **Submit**.
4. Open the integration and copy the **Internal Integration Secret** (starts with `ntn_` or `secret_`). This is your **NOTION_API_KEY**.

### 1.2 Create a page that will hold the databases

1. In Notion, create a **new page** (e.g. “Health” or “Fitness”) where you want the Garmin and Meals databases to live.
2. Open that page and copy its URL, e.g.:
   ```
   https://www.notion.so/yournamehere/PageName-31b4205a2f858092bdcasfdffd3212f3?source=copy_link
   ```
3. The **page ID** is the part between `PageName-` and `?source=copy_link`:  
   e.g. here it would be `31b4205a2f858092bdcasfdffd3212f3`
   This is your **NOTION_PAGE_ID**.

### 1.3 Share the page with your integration

1. Open **the same page** in Notion.
2. Click **•••** (top right) → **Add connections** (or **Connections**).
3. Find your integration (e.g. “Garmin Meals Sync”) and select it.
4. Confirm. The integration can now create and edit databases and pages under this page.

You do **not** create the databases yourself. The script creates **📊 Garmin Daily** (and optionally **🍽️ Meals** when meal analysis is enabled in `params.py`) under this page when you run it, only if they don’t already exist.

---

## 2. Environment variables

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Description |
|----------|----------|-------------|
| `GARMIN_EMAIL` | Yes (for Garmin sync) | Garmin Connect login email |
| `GARMIN_PASSWORD` | Yes (for Garmin sync) | Garmin Connect password |
| `NOTION_API_KEY` | Yes | Notion integration secret (from step 1.1) |
| `NOTION_PAGE_ID` | Yes | Page ID where DBs live (from step 1.2) |
| `MISTRAL_AI_API_KEY` | Yes (if Meals) | Mistral API key for meal image analysis (only needed when Meals are enabled in `params.py`) |

**Garmin-only (no Meals):** leave `MISTRAL_AI_API_KEY` empty and keep `RUN_MEAL_ANALYSIS=False` in `params.py`. No Mistral key or Notion Plus needed.

Example `.env` (Garmin + Meals):

```env
GARMIN_EMAIL=you@example.com
GARMIN_PASSWORD=your_password
NOTION_API_KEY=ntn_xxxxxxxxxxxx
NOTION_PAGE_ID=31b4205a2f858092bdccf95ffd3212f3
MISTRAL_AI_API_KEY=your_mistral_key
```

Example `.env` (Garmin only, no LLM cost):

```env
GARMIN_EMAIL=you@example.com
GARMIN_PASSWORD=your_password
NOTION_API_KEY=ntn_xxxxxxxxxxxx
NOTION_PAGE_ID=31b4205a2f858092bdccf95ffd3212f3
```

---

## 2b. Mistral account and API budget (only if Meals are enabled)

1. Go to [Mistral AI](https://mistral.ai/) and sign up / log in.
2. Open [Console](https://console.mistral.ai/) → **API Keys** and create an API key. Copy it into `.env` as `MISTRAL_AI_API_KEY`.
3. Set a **usage budget** so you don’t overspend:
   - In the Mistral console, go to **Billing** or **Usage** and set a monthly budget or alert (e.g. €5 or $5). Meal image analysis uses the Pixtral model; cost depends on how many images you analyze per run and how often you run.
4. If you leave `MISTRAL_AI_API_KEY` empty and `RUN_MEAL_ANALYSIS=False` in `params.py`, you never call Mistral and incur no LLM cost.

---

## 3. Install and run

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your values (see above)
# Edit params.py to toggle Meals, choose model, and set sync interval
```

### Recommended: run everything (daemon, every full hour)

```bash
python main.py
```

This script:

1. **Runs immediately once**:
   - Ensures databases exist – creates **📊 Garmin Daily** (and **🍽️ Meals** only if `RUN_MEAL_ANALYSIS` in `params.py` is `True`) under your Notion page, only if they don’t already exist.
   - Syncs Garmin – logs into Garmin Connect and creates/updates one row per day in Garmin Daily.
   - If `RUN_MEAL_ANALYSIS` in `params.py` is `True`: analyzes Meals – finds rows with **Image** but empty **Intake**, sends the image to Mistral, and fills Intake, macros, kcals, and Meal components. If `False`, this step is skipped.
2. **Then repeats every `SYNC_INTERVAL_MINUTES` from `params.py`** (default 60). It sleeps that long between runs until you stop it (Ctrl+C).

### Run only one part (single run, no hourly loop)

- **Garmin sync only** (DB must already exist, e.g. after one `main.py` run):
  ```bash
  python sync_garmin.py
  ```
- **Meals analysis only** (when `RUN_MEAL_ANALYSIS=True`; DB must already exist):
  ```bash
  python sync_meals.py
  ```

If you run `sync_garmin.py` or `sync_meals.py` before ever running `main.py`, you’ll get a message to run `main.py` first so the databases are created.

---

## 4. Database schemas (created automatically)

When `main.py` creates the databases, they get these properties. **Garmin Daily** is always created; **Meals** is only created when `RUN_MEAL_ANALYSIS=True`. You don’t add properties by hand unless you use an old Meals DB and want kcals / Meal components.

### 📊 Garmin Daily

| Property | Type | Description |
|----------|------|-------------|
| Date | Title | Row label (e.g. date string) |
| date | Date | Same date; used for finding/updating rows |
| steps | Number | Total steps |
| total_calories | Number | Total kilocalories |
| active_calories | Number | Active kilocalories |
| resting_hr | Number | Resting heart rate |
| avg_stress | Number | Average stress level |
| body_battery_high | Number | Body Battery charged |
| body_battery_low | Number | Body Battery drained |
| intensity_minutes | Number | Moderate + vigorous activity minutes |
| sleep_hours | Number | Sleep duration (hours) |
| hrv | Number | HRV (e.g. last night avg) |
| weight_kg | Number | Weight in kg |

### 🍽️ Meals

| Property | Type | Description |
|----------|------|-------------|
| Intake | Title | Meal name (from AI or manual) |
| Time | Date | When you ate |
| Image | Files | Meal photo (optional) |
| Meal components | Rich text | AI: list of components (e.g. "chicken, rice, broccoli") |
| kcals | Number | Calculated: 4×P + 4×C + 9×F + 2×fiber |
| Proteins | Number | Grams |
| Fats | Number | Grams |
| Carbohydrates | Number | Grams |
| Sugars | Number | Grams (AI leaves 0) |
| Dietary Fibers | Number | Grams |

---

## 5. How to use Meals with AI (only when RUN_MEAL_ANALYSIS=True)

1. In the **🍽️ Meals** database (under your Notion page), add a **new row**.
2. Upload a photo in the **Image** property.
3. Leave **Intake** (and optionally the macro fields) empty.
4. Run `python main.py` or `python sync_meals.py`.
5. The script finds rows with Image set and Intake empty, sends the image to Mistral Pixtral, and fills **Intake**, **Meal components**, **kcals**, **Proteins**, **Fats**, **Carbohydrates**, **Dietary Fibers** (and **Sugars** = 0).

**kcals** is always computed from macros (4 kcal/g protein, 4 kcal/g carbs, 9 kcal/g fat, 2 kcal/g fiber), not taken from the AI.

---

## 6. Deploy with GitHub Actions

The workflow runs on a **cron schedule** (default: once per day at 06:00 UTC). Each run ensures DBs exist, syncs Garmin, and optionally runs Meals analysis. **GitHub allows a minimum schedule of every 5 minutes** – you can run as often as every 5 minutes by changing the cron (see 6.3).

### 6.1 Add repository secrets

1. In your GitHub repo go to **Settings → Secrets and variables → Actions**.
2. Click **New repository secret** and add:

   | Secret | Required | Value |
   |--------|----------|--------|
   | `GARMIN_EMAIL` | Yes | Your Garmin Connect email |
   | `GARMIN_PASSWORD` | Yes | Your Garmin Connect password |
   | `NOTION_API_KEY` | Yes | Notion integration secret (from step 1.1) |
   | `NOTION_PAGE_ID` | Yes | Page ID where the DBs live (from step 1.2) |
   | `MISTRAL_AI_API_KEY` | If Meals | Mistral API key (only if you enable Meals in `params.py`) |

3. Push the repo (the workflow file is already in `.github/workflows/sync-garmin-notion.yml`). The workflow uses `RUN_ONCE=1` so it runs `main.py` once and exits (no hourly loop).

### 6.2 Run the workflow

- **Automatic:** according to the cron in the workflow file (default: daily at 06:00 UTC).
- **Manual:** **Actions** tab → **Sync Garmin to Notion** → **Run workflow**.

### 6.3 Schedule frequency (cron)

GitHub Actions **minimum interval is 5 minutes**. To run every 5 minutes, edit `.github/workflows/sync-garmin-notion.yml` and set:

```yaml
schedule:
  - cron: "*/5 * * * *"   # Every 5 minutes
```

Other examples: `0 * * * *` = every hour on the hour; `0 6 * * *` = once daily at 06:00 UTC. The daemon interval (`SYNC_INTERVAL_MINUTES` in `.env`) only applies when you run `python main.py` locally; in Actions, frequency is controlled only by the workflow cron.

Garmin Connect login does not support 2FA for this type of access; use an app password or a dedicated account if your main account has 2FA.

---

## 7. Summary checklist

- [ ] Notion integration created; **NOTION_API_KEY** copied.
- [ ] Notion page created; **NOTION_PAGE_ID** copied from URL.
- [ ] Page shared with the integration (**••• → Add connections**).
- [ ] `.env` filled with Garmin, Notion, and (optionally) Mistral keys.
- [ ] `params.py` edited: set `RUN_MEAL_ANALYSIS`, `model`, and `SYNC_INTERVAL_MINUTES` as desired.
- [ ] `pip install -r requirements.txt` and `python main.py` run at least once so **📊 Garmin Daily** (and **🍽️ Meals** if enabled) are created under that page.
