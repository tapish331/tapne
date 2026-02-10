from __future__ import annotations

from django.urls import path

from . import views

app_name = "media"

urlpatterns = [
    path("upload/", views.media_upload_view, name="upload"),
    path("delete/<int:attachment_id>/", views.media_delete_view, name="delete"),
]
