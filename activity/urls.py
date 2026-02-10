from __future__ import annotations

from django.urls import path

from . import views

app_name = "activity"

urlpatterns = [
    path("", views.activity_index_view, name="index"),
]
