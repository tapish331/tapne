from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Any, Final, cast

from django.http import HttpRequest

VERBOSE_FLAGS: Final[set[str]] = {"1", "true", "yes", "on"}

# Profile completion bars (RULES-aligned with the product spec).
TRAVELER_REQUIRED_FIELDS: Final[tuple[str, ...]] = ("avatar_url", "bio", "location")
HOST_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "avatar_url",
    "bio",
    "location",
    "travel_tags",
    "gallery_photos",
)
HOST_MIN_TRAVEL_TAGS: Final[int] = 3
HOST_MIN_GALLERY_PHOTOS: Final[int] = 3


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
        print(f"[accounts][verbose] {message}", flush=True)


def _profile_trip_sections_for_member(member: object) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """
    Build created/joined trip payloads for a member's public profile.

    Used by the SPA profile endpoint to populate trip carousels. Kept after
    the SPA cutover because `frontend.views` imports the public wrapper
    below; lives here (rather than being inlined into frontend.views) to
    avoid a circular dependency between `frontend` and the `enrollment` /
    `trips` / `feed` apps.
    """

    try:
        from enrollment.models import EnrollmentRequest
        from feed.models import enrich_trip_preview_fields
        from trips.models import Trip
    except Exception:
        return [], []

    created_trip_rows = (
        Trip.objects.select_related("host")
        .filter(host=cast(Any, member), is_published=True)
        .order_by("-starts_at", "-pk")[:12]
    )
    created_trips = [dict(enrich_trip_preview_fields(item.to_trip_data())) for item in created_trip_rows]

    approved_join_rows = (
        EnrollmentRequest.objects.select_related("trip", "trip__host")
        .filter(
            requester=cast(Any, member),
            status=EnrollmentRequest.STATUS_APPROVED,
            trip__is_published=True,
        )
        .order_by("-updated_at", "-pk")
    )

    joined_trips: list[dict[str, object]] = []
    seen_trip_ids: set[int] = set()
    for row in approved_join_rows:
        trip = getattr(row, "trip", None)
        trip_id = int(getattr(trip, "pk", 0) or 0)
        if trip is None or trip_id <= 0 or trip_id in seen_trip_ids:
            continue
        seen_trip_ids.add(trip_id)
        try:
            joined_trips.append(dict(enrich_trip_preview_fields(trip.to_trip_data())))
        except Exception:
            continue
        if len(joined_trips) >= 12:
            break

    return created_trips, joined_trips


def profile_trip_sections_for_member(member: object) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Public wrapper around `_profile_trip_sections_for_member` — imported
    by `frontend.views` to populate SPA profile responses."""

    return _profile_trip_sections_for_member(member)


def _hosted_trip_ids_for_user(user: object) -> list[int]:
    """Numeric primary keys of every published trip this user has hosted."""

    user_id = int(getattr(user, "pk", 0) or 0)
    if user_id <= 0:
        return []

    try:
        from trips.models import Trip
    except Exception:
        return []

    return list(
        Trip.objects.filter(host_id=user_id, is_published=True).values_list("pk", flat=True)
    )


def host_metrics_for_user(user: object) -> dict[str, Any]:
    """
    Compute the host-trust metric strip for a user's profile.

    Returns a dict shaped for the frontend profile payload. All numeric
    fields default to 0 (not None) so the frontend can render the strip
    without null-guarding every tile.
    """

    user_id = int(getattr(user, "pk", 0) or 0)
    if user_id <= 0:
        return {
            "average_rating": 0.0,
            "reviews_count": 0,
            "trips_hosted": 0,
            "travelers_hosted": 0,
            "repeat_travelers_count": 0,
            "median_response_hours": None,
        }

    hosted_trip_ids = _hosted_trip_ids_for_user(user)

    average_rating = 0.0
    reviews_count = 0
    if hosted_trip_ids:
        try:
            from django.db.models import Avg
            from reviews.models import Review

            review_qs = Review.objects.filter(
                target_type=Review.TARGET_TRIP,
                target_key__in=[str(trip_id) for trip_id in hosted_trip_ids],
            )
            reviews_count = int(review_qs.count())
            if reviews_count:
                avg_value = review_qs.aggregate(average=Avg("rating")).get("average") or 0.0
                average_rating = round(float(avg_value), 2)
        except Exception:
            reviews_count = 0
            average_rating = 0.0

    travelers_hosted = 0
    repeat_travelers_count = 0
    median_response_hours: float | None = None
    if hosted_trip_ids:
        try:
            from django.db.models import Count
            from enrollment.models import EnrollmentRequest

            approved_qs = EnrollmentRequest.objects.filter(
                trip_id__in=hosted_trip_ids,
                status=EnrollmentRequest.STATUS_APPROVED,
            )
            travelers_hosted = int(approved_qs.count())

            requester_counts = (
                approved_qs.values("requester_id")
                .annotate(approved_count=Count("id"))
                .filter(approved_count__gte=2)
            )
            repeat_travelers_count = int(requester_counts.count())

            response_rows = (
                EnrollmentRequest.objects.filter(
                    trip_id__in=hosted_trip_ids,
                    reviewed_at__isnull=False,
                    reviewed_by_id__isnull=False,
                )
                .values_list("created_at", "reviewed_at")
            )
            deltas: list[float] = []
            for created_at, reviewed_at in response_rows:
                if not isinstance(created_at, datetime) or not isinstance(reviewed_at, datetime):
                    continue
                seconds = (reviewed_at - created_at).total_seconds()
                if seconds < 0:
                    continue
                deltas.append(seconds / 3600.0)
            if deltas:
                median_response_hours = round(float(median(deltas)), 1)
        except Exception:
            pass

    return {
        "average_rating": average_rating,
        "reviews_count": reviews_count,
        "trips_hosted": len(hosted_trip_ids),
        "travelers_hosted": travelers_hosted,
        "repeat_travelers_count": repeat_travelers_count,
        "median_response_hours": median_response_hours,
    }


def review_distribution_for_host(user: object) -> dict[str, float]:
    """
    Return the percentage breakdown of star ratings across all reviews on
    trips this user has hosted, keyed by string rating value '5'..'1'.

    Percentages sum to 100.0 (rounded to one decimal) when there is at
    least one review; an empty histogram returns all-zero buckets so the
    frontend can render the bar without null-guarding.
    """

    buckets = {str(rating): 0.0 for rating in range(5, 0, -1)}
    hosted_trip_ids = _hosted_trip_ids_for_user(user)
    if not hosted_trip_ids:
        return buckets

    try:
        from django.db.models import Count
        from reviews.models import Review

        rows = (
            Review.objects.filter(
                target_type=Review.TARGET_TRIP,
                target_key__in=[str(trip_id) for trip_id in hosted_trip_ids],
            )
            .values("rating")
            .annotate(count=Count("id"))
        )
        counts = {int(item["rating"]): int(item["count"]) for item in rows}
    except Exception:
        return buckets

    total = sum(counts.values())
    if total <= 0:
        return buckets

    for rating_value in range(5, 0, -1):
        pct = (counts.get(rating_value, 0) / total) * 100.0
        buckets[str(rating_value)] = round(pct, 1)
    return buckets


def reviews_received_for_host(user: object, *, limit: int = 50) -> list[dict[str, Any]]:
    """
    Chronological feed (newest first) of every review left on trips this
    user has hosted. Each entry carries enough context for the host-profile
    review card: rating, headline, body, the trip the review was for, and
    the reviewer's identity.
    """

    hosted_trip_ids = _hosted_trip_ids_for_user(user)
    if not hosted_trip_ids:
        return []

    try:
        from reviews.models import Review
        from trips.models import Trip
    except Exception:
        return []

    review_rows = (
        Review.objects.select_related("author", "author__account_profile")
        .filter(
            target_type=Review.TARGET_TRIP,
            target_key__in=[str(trip_id) for trip_id in hosted_trip_ids],
        )
        .order_by("-created_at", "-pk")[: max(1, int(limit or 50))]
    )

    trip_label_by_id: dict[int, dict[str, str]] = {}
    for trip_id in hosted_trip_ids:
        trip_label_by_id[int(trip_id)] = {"title": "", "url": f"/trips/{int(trip_id)}/"}
    try:
        for trip_row in Trip.objects.filter(pk__in=hosted_trip_ids).only("pk", "title"):
            trip_label_by_id[int(trip_row.pk)] = {
                "title": str(getattr(trip_row, "title", "") or "").strip(),
                "url": f"/trips/{int(trip_row.pk)}/",
            }
    except Exception:
        pass

    payload: list[dict[str, Any]] = []
    for row in review_rows:
        try:
            trip_id = int(row.target_key) if str(row.target_key).isdigit() else 0
        except Exception:
            trip_id = 0
        trip_meta = trip_label_by_id.get(trip_id, {"title": "", "url": ""})
        author = getattr(row, "author", None)
        author_username = str(getattr(author, "username", "") or "").strip()
        author_profile = getattr(author, "account_profile", None) if author is not None else None
        author_display = (
            author_profile.effective_display_name
            if author_profile is not None
            else author_username
        )
        author_avatar = str(getattr(author_profile, "avatar_url", "") or "") if author_profile else ""

        payload.append(
            {
                "id": int(row.pk or 0),
                "rating": int(row.rating or 0),
                "headline": str(row.headline or "").strip(),
                "body": str(row.body or "").strip(),
                "created_at": row.created_at,
                "trip_id": trip_id,
                "trip_title": trip_meta.get("title", ""),
                "trip_url": trip_meta.get("url", ""),
                "author_username": author_username,
                "author_display_name": author_display,
                "author_avatar_url": author_avatar,
            }
        )
    return payload


def reviews_written_by_user(user: object, *, limit: int = 50) -> list[dict[str, Any]]:
    """Chronological feed of reviews this user has authored — surfaced on the traveler profile."""

    user_id = int(getattr(user, "pk", 0) or 0)
    if user_id <= 0:
        return []

    try:
        from reviews.models import Review
    except Exception:
        return []

    rows = (
        Review.objects.filter(author_id=user_id).order_by("-created_at", "-pk")[
            : max(1, int(limit or 50))
        ]
    )
    payload: list[dict[str, Any]] = []
    for row in rows:
        payload.append(
            {
                "id": int(row.pk or 0),
                "rating": int(row.rating or 0),
                "headline": str(row.headline or "").strip(),
                "body": str(row.body or "").strip(),
                "created_at": row.created_at,
                "target_type": str(row.target_type or "").strip(),
                "target_key": str(row.target_key or "").strip(),
                "target_label": str(row.target_label or "").strip(),
                "target_url": str(row.target_url or "").strip(),
            }
        )
    return payload


def profile_completeness_for_user(user: object, *, is_host: bool) -> dict[str, Any]:
    """
    Return `{ is_complete, missing_fields }` for the completion banner.

    The bar differs by role: travelers must fill avatar + bio + location;
    hosts additionally need 3+ travel tags and 3+ gallery photos.
    """

    try:
        from accounts.models import ensure_profile

        profile = ensure_profile(user)
    except Exception:
        return {"is_complete": False, "missing_fields": list(HOST_REQUIRED_FIELDS if is_host else TRAVELER_REQUIRED_FIELDS)}

    missing: list[str] = []
    avatar_url = str(getattr(profile, "avatar_url", "") or "").strip()
    bio = str(getattr(profile, "bio", "") or "").strip()
    location = str(getattr(profile, "location", "") or "").strip()
    travel_tags = list(getattr(profile, "travel_tags", []) or [])
    gallery_photos = list(getattr(profile, "gallery_photos", []) or [])

    if not avatar_url:
        missing.append("avatar_url")
    if not bio:
        missing.append("bio")
    if not location:
        missing.append("location")
    if is_host:
        if len([tag for tag in travel_tags if str(tag).strip()]) < HOST_MIN_TRAVEL_TAGS:
            missing.append("travel_tags")
        if len([url for url in gallery_photos if str(url).strip()]) < HOST_MIN_GALLERY_PHOTOS:
            missing.append("gallery_photos")

    return {"is_complete": not missing, "missing_fields": missing}
