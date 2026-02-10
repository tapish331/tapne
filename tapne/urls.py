# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from accounts import views as accounts_views
from django.contrib import admin
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import URLPattern, URLResolver, include, path


def health(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok", "service": "tapne-placeholder"})


def activity_page(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/activity/index.html")


def settings_page(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/settings/index.html")


urlpatterns: list[URLPattern | URLResolver] = [
    path("", include("feed.urls")),
    path("health/", health, name="health"),
    path("search/", include("search.urls")),
    path("accounts/", include("accounts.urls")),
    path("trips/", include("trips.urls")),
    path("blogs/", include("blogs.urls")),
    path("social/", include("social.urls")),
    path("enroll/", include("enrollment.urls")),
    path("interactions/", include("interactions.urls")),
    path("reviews/", include("reviews.urls")),
    path("u/<slug:username>/", accounts_views.public_profile_view, name="public-profile"),
    path("activity/", activity_page, name="activity"),
    path("settings/", settings_page, name="settings"),
    path("admin/", admin.site.urls),
]
