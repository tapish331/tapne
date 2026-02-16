from __future__ import annotations

from datetime import datetime
from typing import Final, TypedDict
from urllib.parse import quote_plus

from django.contrib.auth import get_user_model
from django.db.models.functions import Lower
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from tapne.seo import build_absolute_url, build_seo_meta_context
from trips.models import Trip

from .models import TripData, build_home_payload_for_user

VERBOSE_FLAGS: Final[set[str]] = {"1", "true", "yes", "on"}
HOME_SECTION_LIMIT: Final[int] = 8
UserModel = get_user_model()


class DestinationData(TypedDict):
    key: str
    name: str
    trip_count: int
    featured_trip_title: str
    featured_trip_url: str
    featured_trip_date_label: str
    search_url: str


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


def _as_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        normalized = f"{text[:-1]}+00:00" if text.endswith("Z") else text
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
    return None


def _as_aware_datetime(value: object) -> datetime | None:
    candidate = _as_datetime(value)
    if candidate is None:
        return None
    if timezone.is_naive(candidate):
        try:
            return timezone.make_aware(candidate, timezone.get_current_timezone())
        except Exception:
            return None
    return candidate


def _upcoming_trip_rows(trips: list[TripData], *, limit: int = HOME_SECTION_LIMIT) -> list[TripData]:
    now = timezone.now()
    upcoming: list[TripData] = []

    for trip in trips:
        starts_at = _as_aware_datetime(trip.get("starts_at"))
        if starts_at is not None and starts_at < now:
            continue
        upcoming.append(trip)
        if len(upcoming) >= limit:
            return upcoming

    return upcoming[:limit]


def _destination_rows_from_trips(
    trips: list[TripData],
    *,
    limit: int = HOME_SECTION_LIMIT,
) -> list[DestinationData]:
    rows_by_key: dict[str, DestinationData] = {}
    ordered_keys: list[str] = []

    for trip in trips:
        destination_name = str(trip.get("destination", "") or "").strip()
        if not destination_name:
            continue

        destination_key = destination_name.lower()
        if destination_key not in rows_by_key:
            row: DestinationData = {
                "key": destination_key.replace(" ", "-"),
                "name": destination_name,
                "trip_count": 0,
                "featured_trip_title": str(trip.get("title", "") or "").strip() or "Upcoming trip",
                "featured_trip_url": str(trip.get("url", "") or "").strip(),
                "featured_trip_date_label": str(trip.get("date_label", "") or "").strip() or "Dates announced soon",
                "search_url": f"/search/?type=trips&q={quote_plus(destination_name)}",
            }
            rows_by_key[destination_key] = row
            ordered_keys.append(destination_key)

        rows_by_key[destination_key]["trip_count"] += 1

    return [rows_by_key[key] for key in ordered_keys[:limit]]


def _annotate_bookmark_state_for_trips(user: object, trips: list[TripData]) -> list[TripData]:
    for trip in trips:
        trip["is_bookmarked"] = False

    if not bool(getattr(user, "is_authenticated", False)):
        return trips

    viewer_id = int(getattr(user, "pk", 0) or 0)
    if viewer_id <= 0:
        return trips

    trip_ids = sorted(
        {
            int(trip.get("id", 0) or 0)
            for trip in trips
            if int(trip.get("id", 0) or 0) > 0
        }
    )
    if not trip_ids:
        return trips

    try:
        from social.models import Bookmark
    except Exception:
        return trips

    trip_keys = [str(trip_id) for trip_id in trip_ids]
    bookmarked_keys = set(
        Bookmark.objects.filter(
            member_id=viewer_id,
            target_type=Bookmark.TARGET_TRIP,
            target_key__in=trip_keys,
        ).values_list("target_key", flat=True)
    )

    for trip in trips:
        trip_id = int(trip.get("id", 0) or 0)
        if trip_id > 0:
            trip["is_bookmarked"] = str(trip_id) in bookmarked_keys
    return trips


def home(request: HttpRequest) -> HttpResponse:
    viewer_state = "member" if request.user.is_authenticated else "guest"
    _vprint(request, f"Rendering home feed for viewer_state={viewer_state}")

    payload = build_home_payload_for_user(request.user, limit_per_section=HOME_SECTION_LIMIT)
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

    upcoming_trips = _annotate_bookmark_state_for_trips(
        request.user,
        _upcoming_trip_rows(payload["trips"]),
    )
    destinations = _destination_rows_from_trips(upcoming_trips)

    context: dict[str, object] = {
        "trips": upcoming_trips,
        "destinations": destinations,
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
