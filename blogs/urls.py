from __future__ import annotations

from django.urls import path

from . import views

app_name = "blogs"

urlpatterns = [
    path("", views.blog_list_view, name="list"),
    path("create/", views.blog_create_view, name="create"),
    path("<slug:slug>/", views.blog_detail_view, name="detail"),
    path("<slug:slug>/edit/", views.blog_edit_view, name="edit"),
    path("<slug:slug>/delete/", views.blog_delete_view, name="delete"),
]
