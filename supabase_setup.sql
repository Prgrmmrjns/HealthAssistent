-- =============================================================================
-- Health Assistant – Supabase SQL Setup
-- Paste this into: Supabase → SQL Editor → New query → Run
-- =============================================================================

-- Exercises catalogue
CREATE TABLE IF NOT EXISTS fitness_exercise (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(200) NOT NULL UNIQUE,
    garmin_category VARCHAR(100) NOT NULL DEFAULT '',
    garmin_name VARCHAR(200) NOT NULL DEFAULT '',
    muscle_group VARCHAR(100) NOT NULL DEFAULT '',
    equipment   VARCHAR(100) NOT NULL DEFAULT 'Other',
    exercise_type VARCHAR(20) NOT NULL DEFAULT 'Strength'
);
CREATE INDEX IF NOT EXISTS fitness_exercise_garmin_category ON fitness_exercise (garmin_category);
CREATE INDEX IF NOT EXISTS fitness_exercise_garmin_name     ON fitness_exercise (garmin_name);

-- Workouts (synced from Garmin)
CREATE TABLE IF NOT EXISTS fitness_workout (
    id                  BIGSERIAL PRIMARY KEY,
    garmin_activity_id  BIGINT UNIQUE,
    name                VARCHAR(200) NOT NULL,
    date                DATE NOT NULL,
    sport               VARCHAR(50) NOT NULL,
    duration_min        DOUBLE PRECISION,
    distance_km         DOUBLE PRECISION,
    calories            DOUBLE PRECISION,
    avg_hr              DOUBLE PRECISION,
    max_hr              DOUBLE PRECISION,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS fitness_workout_date  ON fitness_workout (date);
CREATE INDEX IF NOT EXISTS fitness_workout_sport ON fitness_workout (sport);

-- Workout sets (exercises inside a workout)
CREATE TABLE IF NOT EXISTS fitness_workoutset (
    id           BIGSERIAL PRIMARY KEY,
    exercise     VARCHAR(200) NOT NULL,
    set_type     VARCHAR(20) NOT NULL DEFAULT 'Active',
    reps         INTEGER,
    weight_kg    DOUBLE PRECISION,
    duration_sec DOUBLE PRECISION,
    "order"      INTEGER NOT NULL DEFAULT 0,
    workout_id   BIGINT NOT NULL REFERENCES fitness_workout(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS fitness_workoutset_workout_id ON fitness_workoutset (workout_id);

-- Daily stats (synced from Garmin)
CREATE TABLE IF NOT EXISTS fitness_dailystats (
    id                  BIGSERIAL PRIMARY KEY,
    date                DATE NOT NULL UNIQUE,
    steps               INTEGER,
    total_calories      INTEGER,
    active_calories     INTEGER,
    resting_hr          INTEGER,
    avg_stress          INTEGER,
    body_battery_high   INTEGER,
    body_battery_low    INTEGER,
    sleep_hours         DOUBLE PRECISION,
    hrv                 DOUBLE PRECISION,
    weight_kg           DOUBLE PRECISION,
    vo2_max             DOUBLE PRECISION,
    floors_climbed      INTEGER,
    intensity_minutes   INTEGER
);

-- Workout templates (Planner)
CREATE TABLE IF NOT EXISTS fitness_workouttemplate (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    sport       VARCHAR(50) NOT NULL DEFAULT 'Strength Training',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE fitness_workouttemplate ADD COLUMN IF NOT EXISTS sport VARCHAR(50) NOT NULL DEFAULT 'Strength Training';

-- Planned workouts (scheduled for date/time, Garmin sync)
CREATE TABLE IF NOT EXISTS fitness_plannedworkout (
    id                BIGSERIAL PRIMARY KEY,
    date              DATE NOT NULL,
    time              TIME,
    sport             VARCHAR(50) NOT NULL,
    name              VARCHAR(200) NOT NULL,
    description       TEXT NOT NULL DEFAULT '',
    duration_min      INTEGER,
    distance_km       DOUBLE PRECISION,
    template_id       BIGINT REFERENCES fitness_workouttemplate(id) ON DELETE SET NULL,
    garmin_synced     BOOLEAN NOT NULL DEFAULT FALSE,
    garmin_workout_id VARCHAR(100) NOT NULL DEFAULT '',
    notes             TEXT NOT NULL DEFAULT '',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS fitness_plannedworkout_date ON fitness_plannedworkout (date);

-- Goals
CREATE TABLE IF NOT EXISTS fitness_goal (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    target_date DATE,
    status      VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS fitness_goal_status ON fitness_goal (status);

-- Milestones (linked to goals)
CREATE TABLE IF NOT EXISTS fitness_milestone (
    id          BIGSERIAL PRIMARY KEY,
    goal_id     BIGINT NOT NULL REFERENCES fitness_goal(id) ON DELETE CASCADE,
    name        VARCHAR(200) NOT NULL,
    target_date DATE,
    completed_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS fitness_milestone_goal_id ON fitness_milestone (goal_id);

-- Habits (user-defined + suggested defaults)
CREATE TABLE IF NOT EXISTS fitness_habit (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_suggested BOOLEAN NOT NULL DEFAULT FALSE,
    "order"     INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Habit completions per day (logged from check-in)
CREATE TABLE IF NOT EXISTS fitness_habitlog (
    id          BIGSERIAL PRIMARY KEY,
    habit_id    BIGINT NOT NULL REFERENCES fitness_habit(id) ON DELETE CASCADE,
    date        DATE NOT NULL,
    completed   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(habit_id, date)
);
CREATE INDEX IF NOT EXISTS fitness_habitlog_habit_date ON fitness_habitlog (habit_id, date);

-- Exercises inside a template
CREATE TABLE IF NOT EXISTS fitness_templateexercise (
    id          BIGSERIAL PRIMARY KEY,
    custom_name VARCHAR(200) NOT NULL DEFAULT '',
    sets        INTEGER NOT NULL DEFAULT 3,
    reps        INTEGER NOT NULL DEFAULT 10,
    weight_kg   DOUBLE PRECISION,
    rest_sec    INTEGER NOT NULL DEFAULT 90,
    notes       VARCHAR(300) NOT NULL DEFAULT '',
    "order"     INTEGER NOT NULL DEFAULT 0,
    exercise_id BIGINT REFERENCES fitness_exercise(id) ON DELETE SET NULL,
    template_id BIGINT NOT NULL REFERENCES fitness_workouttemplate(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS fitness_templateexercise_exercise_id ON fitness_templateexercise (exercise_id);
CREATE INDEX IF NOT EXISTS fitness_templateexercise_template_id ON fitness_templateexercise (template_id);

-- User profile (single row)
CREATE TABLE IF NOT EXISTS fitness_userprofile (
    id                 BIGSERIAL PRIMARY KEY,
    name               VARCHAR(120) NOT NULL DEFAULT '',
    age                INTEGER,
    gender             VARCHAR(1) NOT NULL DEFAULT '',
    height_cm          DOUBLE PRECISION,
    weight_kg          DOUBLE PRECISION,
    profession         VARCHAR(200) NOT NULL DEFAULT '',
    activity_level     VARCHAR(20) NOT NULL DEFAULT '',
    health_conditions  TEXT NOT NULL DEFAULT '',
    goals              TEXT NOT NULL DEFAULT '',
    profile_image      VARCHAR(500) NOT NULL DEFAULT '',
    garmin_connected   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Daily check-ins
CREATE TABLE IF NOT EXISTS fitness_dailycheckin (
    id                   BIGSERIAL PRIMARY KEY,
    date                 DATE NOT NULL UNIQUE,
    mood                 INTEGER,
    energy               INTEGER,
    stress               VARCHAR(20) NOT NULL DEFAULT '',
    sleep_quality        INTEGER,
    sleep_hours_manual   DOUBLE PRECISION,
    hydration_litres     DOUBLE PRECISION,
    notes                TEXT NOT NULL DEFAULT '',
    exercise_minutes     INTEGER,
    steps_estimate       INTEGER,
    exercise_description TEXT NOT NULL DEFAULT '',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS fitness_dailycheckin_date ON fitness_dailycheckin (date);

-- Meals
CREATE TABLE IF NOT EXISTS fitness_meal (
    id          BIGSERIAL PRIMARY KEY,
    date        DATE NOT NULL,
    meal_type   VARCHAR(20) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image       VARCHAR(500) NOT NULL DEFAULT '',
    calories_est INTEGER,
    protein_g   DOUBLE PRECISION,
    carbs_g     DOUBLE PRECISION,
    fat_g       DOUBLE PRECISION,
    fiber_g     DOUBLE PRECISION,
    ai_analysis TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS fitness_meal_date ON fitness_meal (date);

-- Django system tables (required for admin, sessions, auth)
CREATE TABLE IF NOT EXISTS django_content_type (
    id        SERIAL PRIMARY KEY,
    app_label VARCHAR(100) NOT NULL,
    model     VARCHAR(100) NOT NULL,
    UNIQUE (app_label, model)
);

CREATE TABLE IF NOT EXISTS auth_permission (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    content_type_id INTEGER NOT NULL REFERENCES django_content_type(id) ON DELETE CASCADE,
    codename        VARCHAR(100) NOT NULL,
    UNIQUE (content_type_id, codename)
);

CREATE TABLE IF NOT EXISTS auth_group (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS auth_group_permissions (
    id            BIGSERIAL PRIMARY KEY,
    group_id      INTEGER NOT NULL REFERENCES auth_group(id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES auth_permission(id) ON DELETE CASCADE,
    UNIQUE (group_id, permission_id)
);

CREATE TABLE IF NOT EXISTS auth_user (
    id           SERIAL PRIMARY KEY,
    password     VARCHAR(128) NOT NULL,
    last_login   TIMESTAMPTZ,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    username     VARCHAR(150) NOT NULL UNIQUE,
    first_name   VARCHAR(150) NOT NULL DEFAULT '',
    last_name    VARCHAR(150) NOT NULL DEFAULT '',
    email        VARCHAR(254) NOT NULL DEFAULT '',
    is_staff     BOOLEAN NOT NULL DEFAULT FALSE,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    date_joined  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auth_user_groups (
    id       BIGSERIAL PRIMARY KEY,
    user_id  INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
    group_id INTEGER NOT NULL REFERENCES auth_group(id) ON DELETE CASCADE,
    UNIQUE (user_id, group_id)
);

CREATE TABLE IF NOT EXISTS auth_user_user_permissions (
    id            BIGSERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES auth_permission(id) ON DELETE CASCADE,
    UNIQUE (user_id, permission_id)
);

CREATE TABLE IF NOT EXISTS django_admin_log (
    id              SERIAL PRIMARY KEY,
    action_time     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    object_id       TEXT,
    object_repr     VARCHAR(200) NOT NULL,
    action_flag     SMALLINT NOT NULL CHECK (action_flag > 0),
    change_message  TEXT NOT NULL DEFAULT '',
    content_type_id INTEGER REFERENCES django_content_type(id) ON DELETE SET NULL,
    user_id         INTEGER NOT NULL REFERENCES auth_user(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS django_session (
    session_key  VARCHAR(40) PRIMARY KEY,
    session_data TEXT NOT NULL,
    expire_date  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS django_session_expire_date ON django_session (expire_date);

CREATE TABLE IF NOT EXISTS django_migrations (
    id      BIGSERIAL PRIMARY KEY,
    app     VARCHAR(255) NOT NULL,
    name    VARCHAR(255) NOT NULL,
    applied TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
