from django.urls import path

from . import views

app_name = "fitness"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("workouts/", views.workout_list, name="workout_list"),
    path("workouts/<int:pk>/", views.workout_detail, name="workout_detail"),
    path("exercises/", views.exercise_list, name="exercise_list"),
    path("progress/", views.progress, name="progress"),
    path("templates/", views.template_list, name="template_list"),
    path("templates/new/", views.template_create, name="template_create"),
    path("templates/<int:pk>/", views.template_detail, name="template_detail"),
    path("templates/<int:pk>/edit/", views.template_edit, name="template_edit"),
    path("templates/<int:pk>/delete/", views.template_delete, name="template_delete"),
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
]
