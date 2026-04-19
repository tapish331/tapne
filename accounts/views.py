from __future__ import annotations

from typing import Any, Final, cast

from django.http import HttpRequest

VERBOSE_FLAGS: Final[set[str]] = {"1", "true", "yes", "on"}


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
