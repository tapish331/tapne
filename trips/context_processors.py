from __future__ import annotations

from typing import Any, cast

from django.http import HttpRequest

from feed.models import enrich_trip_preview_fields

from .models import Trip


def nav_trip_drafts(request: HttpRequest) -> dict[str, object]:
    """
    Provide recent unpublished trips so the shared navbar can mirror Lovable's
    create-trip launcher with a "continue draft" section.
    """

    if not request.user.is_authenticated:
        return {
            "nav_recent_trip_drafts": [],
            "nav_recent_trip_draft_count": 0,
        }

    draft_rows = list(
        Trip.objects.select_related("host")
        .filter(host=cast(Any, request.user), is_published=False)
        .order_by("-updated_at", "-pk")[:4]
    )

    recent_drafts: list[dict[str, object]] = []
    for trip in draft_rows:
        trip_preview = dict(enrich_trip_preview_fields(trip.to_trip_data()))
        trip_preview["edit_url"] = f"/trips/{int(trip.pk)}/edit/"
        recent_drafts.append(trip_preview)

    draft_count = Trip.objects.filter(host=cast(Any, request.user), is_published=False).count()
    return {
        "nav_recent_trip_drafts": recent_drafts,
        "nav_recent_trip_draft_count": draft_count,
    }
