from __future__ import annotations

from django.urls import path

from . import views

app_name = "settings_app"

urlpatterns = [
    path("", views.settings_index_view, name="index"),
]
