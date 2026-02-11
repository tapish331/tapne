from __future__ import annotations

from django.urls import path

from . import views

app_name = "runtime"

urlpatterns = [
    path("health/", views.runtime_health_view, name="health"),
    path("cache-preview/", views.runtime_cache_preview_view, name="cache-preview"),
]
