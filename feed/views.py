from __future__ import annotations

from typing import Final

from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.db.models.functions import Lower

from tapne.seo import build_absolute_url, build_seo_meta_context
from trips.models import Trip

from .models import build_home_payload_for_user

VERBOSE_FLAGS: Final[set[str]] = {"1", "true", "yes", "on"}
UserModel = get_user_model()


def _is_verbose_request(request: HttpRequest) -> bool:
    candidate = (
        request.GET.get("verbose")
        or request.POST.get("verbose")
        or request.headers.get("X-Tapne-Verbose")
        or ""
    )
    return candidate.strip().lower() in VERBOSE_FLAGS


def _vprint(request: HttpRequest, message: str) -> None:
    if _is_verbose_request(request):
        print(f"[feed][verbose] {message}", flush=True)


def _home_totals() -> dict[str, int]:
    total_trips_created = int(Trip.objects.count())
    total_unique_destinations = int(
        Trip.objects.exclude(destination__isnull=True)
        .exclude(destination__exact="")
        .annotate(destination_normalized=Lower("destination"))
        .values("destination_normalized")
        .distinct()
        .count()
    )
    total_authenticated_users = int(UserModel.objects.filter(is_active=True).count())
    return {
        "total_unique_destinations": total_unique_destinations,
        "total_authenticated_users": total_authenticated_users,
        "total_trips_created": total_trips_created,
    }


def home(request: HttpRequest) -> HttpResponse:
    viewer_state = "member" if request.user.is_authenticated else "guest"
    _vprint(request, f"Rendering home feed for viewer_state={viewer_state}")

    payload = build_home_payload_for_user(request.user)
    _vprint(
        request,
        (
            "Feed mode={mode}; reason={reason}; counts trips={trip_count}, profiles={profile_count}, blogs={blog_count}"
            .format(
                mode=payload["mode"],
                reason=payload["reason"],
                trip_count=len(payload["trips"]),
                profile_count=len(payload["profiles"]),
                blog_count=len(payload["blogs"]),
            )
        ),
    )

    context: dict[str, object] = {
        "trips": payload["trips"],
        "profiles": payload["profiles"],
        "blogs": payload["blogs"],
        "feed_mode": payload["mode"],
        "feed_reason": payload["reason"],
        **_home_totals(),
    }
    home_description = "Host trips, publish stories, and build your audience with tapne."
    home_json_ld: dict[str, object] = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "tapne",
        "url": build_absolute_url(request, "/"),
        "potentialAction": {
            "@type": "SearchAction",
            "target": build_absolute_url(request, "/search/?q={search_term_string}"),
            "query-input": "required name=search_term_string",
        },
    }
    context.update(
        build_seo_meta_context(
            request,
            title="tapne | Home",
            description=home_description,
            json_ld_payload=home_json_ld,
        )
    )
    return render(request, "pages/home.html", context)
