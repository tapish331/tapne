from __future__ import annotations

from django.urls import path

from . import views

app_name = "reviews"

urlpatterns = [
    path("create/", views.review_create_view, name="create"),
    path("<slug:target_type>/<str:target_id>/", views.review_target_list_view, name="target-list"),
]
