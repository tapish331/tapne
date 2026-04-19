from __future__ import annotations

from django.urls import path

from . import views

app_name = "trips"

# Django-rendered trip pages (list/detail/form/mine/delete) were retired in
# the SPA cutover — the SPA serves them via /frontend-api/trips/*. The URLs
# below are backend-only: file serving for trip banners and the destination
# autocomplete/details APIs consumed by the SPA create/edit forms.
urlpatterns = [
    path("api/destination/autocomplete/", views.trip_destination_autocomplete_view, name="destination-autocomplete"),
    path("api/destination/details/", views.trip_destination_details_view, name="destination-details"),
    path("<int:trip_id>/banner/", views.trip_banner_view, name="banner"),
]
