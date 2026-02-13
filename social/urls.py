from __future__ import annotations

from django.urls import path

from . import views

app_name = "social"

urlpatterns = [
    path("follow/<str:username>/", views.follow_user_view, name="follow"),
    path("unfollow/<str:username>/", views.unfollow_user_view, name="unfollow"),
    path("bookmark/", views.bookmark_view, name="bookmark"),
    path("unbookmark/", views.unbookmark_view, name="unbookmark"),
    path("bookmarks/", views.bookmarks_view, name="bookmarks"),
]
