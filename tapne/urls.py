# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from typing import NotRequired, TypedDict

from django.contrib import admin
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import URLPattern, URLResolver, path


class TripData(TypedDict):
    id: int
    title: str
    summary: NotRequired[str]
    description: NotRequired[str]
    destination: NotRequired[str]
    host_username: NotRequired[str]
    traffic_score: NotRequired[int]
    url: NotRequired[str]


class ProfileData(TypedDict):
    username: str
    id: NotRequired[int]
    bio: NotRequired[str]
    followers_count: NotRequired[int]
    trips_count: NotRequired[int]
    url: NotRequired[str]


class BlogData(TypedDict):
    slug: str
    title: str
    id: NotRequired[int]
    excerpt: NotRequired[str]
    summary: NotRequired[str]
    author_username: NotRequired[str]
    reads: NotRequired[int]
    reviews_count: NotRequired[int]
    url: NotRequired[str]
    body: NotRequired[str]


DEMO_TRIPS: list[TripData] = [
    {
        "id": 101,
        "title": "Kyoto food lanes weekend",
        "summary": "A compact culinary walk through Nishiki, neighborhood izakaya spots, and hidden tea counters.",
        "destination": "Kyoto, Japan",
        "host_username": "mei",
        "traffic_score": 92,
        "url": "/trips/101/",
    },
    {
        "id": 102,
        "title": "Patagonia first-light trekking camp",
        "summary": "Five-day route with sunrise ridge points, weather-safe camps, and a photographer-friendly pace.",
        "destination": "El Chalten, Argentina",
        "host_username": "arun",
        "traffic_score": 87,
        "url": "/trips/102/",
    },
    {
        "id": 103,
        "title": "Morocco souk to desert circuit",
        "summary": "Markets in Marrakech, Atlas crossings, and a two-night Sahara camp for first-time route builders.",
        "destination": "Marrakech to Merzouga",
        "host_username": "sahar",
        "traffic_score": 81,
        "url": "/trips/103/",
    },
]

DEMO_PROFILES: list[ProfileData] = [
    {
        "id": 201,
        "username": "mei",
        "bio": "Street-food mapper, small group host, and blog writer focused on local micro-itineraries.",
        "followers_count": 4810,
        "trips_count": 18,
        "url": "/u/mei/",
    },
    {
        "id": 202,
        "username": "arun",
        "bio": "Mountain route host sharing alpine planning templates for mixed-experience groups.",
        "followers_count": 2980,
        "trips_count": 11,
        "url": "/u/arun/",
    },
]

DEMO_BLOGS: list[BlogData] = [
    {
        "id": 301,
        "slug": "packing-for-swing-weather",
        "title": "Packing for swing-weather trips without overloading",
        "excerpt": "A practical split-list approach for weather shifts when you only want one carry-on setup.",
        "author_username": "mei",
        "reads": 9500,
        "reviews_count": 142,
        "url": "/blogs/packing-for-swing-weather/",
        "body": "Use a modular layer stack, then reserve one slot for location-specific gear.",
    },
    {
        "id": 302,
        "slug": "first-group-trip-ops-checklist",
        "title": "First group-trip operations checklist",
        "excerpt": "Pre-trip ops that prevent most host-side issues: permissions, comms windows, and pacing handoffs.",
        "author_username": "arun",
        "reads": 7200,
        "reviews_count": 98,
        "url": "/blogs/first-group-trip-ops-checklist/",
        "body": "Map operational failure points first, then assign one fallback per checkpoint.",
    },
]


def _matches(query: str, *values: object) -> bool:
    normalized = query.strip().lower()
    if not normalized:
        return True

    for value in values:
        if normalized in str(value or "").lower():
            return True
    return False


def health(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok", "service": "tapne-placeholder"})


def home(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "pages/home.html",
        {"trips": DEMO_TRIPS, "profiles": DEMO_PROFILES, "blogs": DEMO_BLOGS},
    )


def search(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "")
    result_type = request.GET.get("type", "all").lower()

    trips: list[TripData] = [
        trip for trip in DEMO_TRIPS
        if _matches(query, trip.get("title"), trip.get("summary"), trip.get("destination"))
    ]
    profiles: list[ProfileData] = [
        profile for profile in DEMO_PROFILES
        if _matches(query, profile.get("username"), profile.get("bio"))
    ]
    blogs: list[BlogData] = [
        blog for blog in DEMO_BLOGS
        if _matches(query, blog.get("title"), blog.get("excerpt"), blog.get("author_username"))
    ]

    if result_type == "trips":
        profiles = []
        blogs = []
    elif result_type == "users":
        trips = []
        blogs = []
    elif result_type == "blogs":
        trips = []
        profiles = []

    return render(request, "pages/search.html", {"trips": trips, "profiles": profiles, "blogs": blogs})


def trip_list(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/trips/list.html", {"trips": DEMO_TRIPS})


def trip_detail(request: HttpRequest, trip_id: int) -> HttpResponse:
    trip_match = next((item for item in DEMO_TRIPS if item["id"] == trip_id), None)
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


def user_profile(request: HttpRequest, username: str) -> HttpResponse:
    profile_match = next((item for item in DEMO_PROFILES if item["username"] == username), None)
    profile: ProfileData = (
        profile_match
        if profile_match is not None
        else {
            "username": username,
            "bio": "Profile record not found in demo dataset.",
        }
    )
    return render(request, "pages/users/profile.html", {"profile": profile})


def blog_list(request: HttpRequest) -> HttpResponse:
    return render(request, "pages/blogs/list.html", {"blogs": DEMO_BLOGS})


def blog_detail(request: HttpRequest, slug: str) -> HttpResponse:
    blog_match = next((item for item in DEMO_BLOGS if item["slug"] == slug), None)
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
    path("", home, name="home"),
    path("health/", health, name="health"),
    path("search/", search, name="search"),
    path("trips/", trip_list, name="trip-list"),
    path("trips/<int:trip_id>/", trip_detail, name="trip-detail"),
    path("blogs/", blog_list, name="blog-list"),
    path("u/<slug:username>/", user_profile, name="public-profile"),
    path("blogs/<slug:slug>/", blog_detail, name="blog-detail"),
    path("activity/", activity_page, name="activity"),
    path("settings/", settings_page, name="settings"),
    path("admin/", admin.site.urls),
]
