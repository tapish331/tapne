from __future__ import annotations

from django.urls import path

from . import views

app_name = "interactions"

urlpatterns = [
    path("comment/", views.comment_view, name="comment"),
    path("reply/", views.reply_view, name="reply"),
    path("dm/open/", views.dm_open_view, name="dm-open"),
    path("dm/", views.dm_inbox_view, name="dm-inbox"),
    path("dm/<int:thread_id>/", views.dm_thread_view, name="dm-thread"),
    path("dm/<int:thread_id>/send/", views.dm_send_view, name="dm-send"),
]
