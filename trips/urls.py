from __future__ import annotations

from django.urls import path

from . import views

app_name = "trips"

urlpatterns = [
    path("", views.trip_list_view, name="list"),
    path("create/", views.trip_create_view, name="create"),
    path("mine/", views.trip_mine_view, name="mine"),
    path("<int:trip_id>/", views.trip_detail_view, name="detail"),
    path("<int:trip_id>/edit/", views.trip_edit_view, name="edit"),
    path("<int:trip_id>/delete/", views.trip_delete_view, name="delete"),
]
