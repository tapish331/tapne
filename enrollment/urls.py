from __future__ import annotations

from django.urls import path

from . import views

app_name = "enrollment"

urlpatterns = [
    path("trips/<int:trip_id>/request/", views.trip_request_view, name="trip-request"),
    path("hosting/inbox/", views.hosting_inbox_view, name="hosting-inbox"),
    path("requests/<int:request_id>/approve/", views.approve_request_view, name="approve"),
    path("requests/<int:request_id>/deny/", views.deny_request_view, name="deny"),
]
