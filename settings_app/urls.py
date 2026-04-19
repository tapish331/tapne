from __future__ import annotations

from django.urls import path

from . import views

app_name = "settings_app"

# Django-rendered settings page (settings_index_view) was retired in the SPA
# cutover — the SPA handles settings via /frontend-api/settings/. Only the
# appearance JSON-update endpoint remains for the live theme/appearance AJAX
# that the SPA triggers.
urlpatterns = [
    path("appearance/", views.settings_appearance_update_view, name="appearance-update"),
]
