# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from accounts import views as accounts_views
from django.contrib import admin
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import URLPattern, URLResolver, include, path

from feed.models import (
    BlogData,
    TripData,
    get_blog_by_slug,
    get_demo_blogs,
    get_demo_trips,
    get_trip_by_id,
)


def health(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok", "service": "tapne-placeholder"})


def trip_list(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/trips/list.html", {"trips": get_demo_trips()})


def trip_detail(request: HttpRequest, trip_id: int) -> HttpResponse:
    trip_match = get_trip_by_id(trip_id)
    trip: TripData = (
        trip_match
        if trip_match is not None
        else {
            "id": trip_id,
            "title": f"Trip #{trip_id}",
            "description": "Trip record not found in demo dataset.",
        }
    )
    return render(request, "pages/trips/detail.html", {"trip": trip})


def blog_list(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/blogs/list.html", {"blogs": get_demo_blogs()})


def blog_detail(request: HttpRequest, slug: str) -> HttpResponse:
    blog_match = get_blog_by_slug(slug)
    blog: BlogData = (
        blog_match
        if blog_match is not None
        else {
            "slug": slug,
            "title": slug.replace("-", " ").title(),
            "body": "Blog record not found in demo dataset.",
        }
    )
    return render(request, "pages/blogs/detail.html", {"blog": blog})


def activity_page(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/activity/index.html")


def settings_page(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/settings/index.html")


urlpatterns: list[URLPattern | URLResolver] = [
    path("", include("feed.urls")),
    path("health/", health, name="health"),
    path("search/", include("search.urls")),
    path("accounts/", include("accounts.urls")),
    path("trips/", trip_list, name="trip-list"),
    path("trips/<int:trip_id>/", trip_detail, name="trip-detail"),
    path("blogs/", blog_list, name="blog-list"),
    path("u/<slug:username>/", accounts_views.public_profile_view, name="public-profile"),
    path("blogs/<slug:slug>/", blog_detail, name="blog-detail"),
    path("activity/", activity_page, name="activity"),
    path("settings/", settings_page, name="settings"),
    path("admin/", admin.site.urls),
]
