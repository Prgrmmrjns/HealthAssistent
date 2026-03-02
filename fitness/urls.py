from django.urls import path

from . import views

app_name = "fitness"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("workouts/", views.workout_list, name="workout_list"),
    path("workouts/<int:pk>/", views.workout_detail, name="workout_detail"),
    path("progress/", views.progress, name="progress"),
    # Planner (templates, exercises, scheduled workouts)
    path("planner/", views.planner_list, name="planner_list"),
    path("planner/exercises/", views.exercise_list, name="exercise_list"),
    path("planner/templates/", views.template_list, name="template_list"),
    path("planner/templates/new/", views.template_create, name="template_create"),
    path("planner/templates/<int:pk>/", views.template_detail, name="template_detail"),
    path("planner/templates/<int:pk>/edit/", views.template_edit, name="template_edit"),
    path("planner/templates/<int:pk>/delete/", views.template_delete, name="template_delete"),
    path("planner/schedule/", views.planned_list, name="planned_list"),
    path("planner/schedule/add/", views.planned_add, name="planned_add"),
    path("planner/schedule/<int:pk>/", views.planned_detail, name="planned_detail"),
    path("planner/schedule/<int:pk>/edit/", views.planned_edit, name="planned_edit"),
    path("planner/schedule/<int:pk>/delete/", views.planned_delete, name="planned_delete"),
    path("planner/schedule/<int:pk>/sync-garmin/", views.planned_sync_garmin, name="planned_sync_garmin"),
    path("api/exercises/search/", views.exercise_search_api, name="exercise_search_api"),
    # LISA features
    path("profile/", views.profile_view, name="profile"),
    path("checkin/", views.checkin_list, name="checkin_list"),
    path("checkin/today/", views.checkin_form, name="checkin_today"),
    path("checkin/<str:date_str>/", views.checkin_form, name="checkin_date"),
    path("meals/", views.meal_list, name="meal_list"),
    path("meals/add/", views.meal_add, name="meal_add"),
    path("meals/<int:pk>/", views.meal_detail, name="meal_detail"),
    path("meals/<int:pk>/delete/", views.meal_delete, name="meal_delete"),
    path("sync/", views.sync_now, name="sync_now"),
    # Goals & Milestones
    path("goals/", views.goals_list, name="goals_list"),
    path("goals/add/", views.goal_add, name="goal_add"),
    path("goals/<int:pk>/", views.goal_detail, name="goal_detail"),
    path("goals/<int:pk>/edit/", views.goal_edit, name="goal_edit"),
    path("goals/<int:pk>/delete/", views.goal_delete, name="goal_delete"),
    path("goals/<int:goal_pk>/milestones/add/", views.milestone_add, name="milestone_add"),
    path("milestones/<int:pk>/edit/", views.milestone_edit, name="milestone_edit"),
    path("milestones/<int:pk>/delete/", views.milestone_delete, name="milestone_delete"),
    # Habits
    path("habits/", views.habits_list, name="habits_list"),
    path("habits/add/", views.habit_add, name="habit_add"),
    path("habits/<int:pk>/edit/", views.habit_edit, name="habit_edit"),
    path("habits/<int:pk>/delete/", views.habit_delete, name="habit_delete"),
]
