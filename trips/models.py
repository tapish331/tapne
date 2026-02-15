from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, TypedDict, cast

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models
from django.utils import timezone

from feed.models import MemberFeedPreference, TripData, enrich_trip_preview_fields, get_demo_trips, get_trip_by_id
from tapne.features import demo_catalog_enabled
from tapne.storage_urls import build_trip_banner_fallback_url, resolve_file_url, should_use_fallback_file_url


class TripListPayload(TypedDict):
    trips: list[TripData]
    mode: str
    reason: str
    source: str
    filters: "TripListFilters"
    total_count: int
    filtered_count: int


class TripListFilters(TypedDict):
    destination: str
    duration: str
    trip_type: str
    budget: str
    difficulty: str


class TripDetailPayload(TypedDict):
    trip: TripData
    mode: str
    reason: str
    source: str
    can_manage_trip: bool


class TripMinePayload(TypedDict):
    trips: list[TripData]
    active_tab: str
    tab_counts: dict[str, int]
    mode: str
    reason: str


TRIP_TYPE_CHOICES: Final[tuple[tuple[str, str], ...]] = (
    ("food-culture", "Food & Culture"),
    ("trekking", "Trekking"),
    ("desert", "Desert Route"),
    ("city", "City Discovery"),
    ("coastal", "Coastal Escape"),
    ("adventure", "Adventure"),
)
BUDGET_TIER_CHOICES: Final[tuple[tuple[str, str], ...]] = (
    ("budget", "$ Budget-friendly"),
    ("mid", "$$ Mid-range"),
    ("premium", "$$$ Premium"),
)
DIFFICULTY_LEVEL_CHOICES: Final[tuple[tuple[str, str], ...]] = (
    ("easy", "Easy"),
    ("moderate", "Moderate"),
    ("challenging", "Challenging"),
)
PACE_LEVEL_CHOICES: Final[tuple[tuple[str, str], ...]] = (
    ("relaxed", "Relaxed"),
    ("balanced", "Balanced"),
    ("fast", "Fast-paced"),
)
GROUP_SIZE_LABEL_CHOICES: Final[tuple[tuple[str, str], ...]] = (
    ("4-6 travelers", "4-6 travelers"),
    ("6-8 travelers", "6-8 travelers"),
    ("6-10 travelers", "6-10 travelers"),
    ("8-12 travelers", "8-12 travelers"),
    ("10-14 travelers", "10-14 travelers"),
)

class Trip(models.Model):
    """
    Core trip record used by list/detail/CRUD flows.

    This model intentionally keeps shape close to the README contract so other
    apps (for example search) can read live rows without extra adapters.
    """

    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hosted_trips",
    )
    title = models.CharField(max_length=180)
    summary = models.CharField(max_length=280, blank=True)
    description = models.TextField(blank=True, validators=[MaxLengthValidator(4000)])
    destination = models.CharField(max_length=160, blank=True)
    banner_image = models.ImageField(upload_to="trip_banners/", blank=True)
    trip_type = models.CharField(max_length=24, choices=TRIP_TYPE_CHOICES, blank=True, default="")
    budget_tier = models.CharField(max_length=16, choices=BUDGET_TIER_CHOICES, blank=True, default="")
    difficulty_level = models.CharField(max_length=16, choices=DIFFICULTY_LEVEL_CHOICES, blank=True, default="")
    pace_level = models.CharField(max_length=16, choices=PACE_LEVEL_CHOICES, blank=True, default="")
    group_size_label = models.CharField(max_length=32, choices=GROUP_SIZE_LABEL_CHOICES, blank=True, default="")
    includes_label = models.CharField(max_length=280, blank=True, default="")
    starts_at = models.DateTimeField(default=timezone.now, db_index=True)
    ends_at = models.DateTimeField(blank=True, null=True)
    traffic_score = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("starts_at", "id")
        indexes = [
            models.Index(fields=("host", "starts_at"), name="trip_host_start_idx"),
            models.Index(fields=("is_published", "starts_at"), name="trip_pub_start_idx"),
        ]

    def __str__(self) -> str:
        return f"Trip #{self.pk or 'new'}: {self.title}"

    def clean(self) -> None:
        super().clean()
        self.title = str(self.title or "").strip()
        self.summary = str(self.summary or "").strip()
        self.description = str(self.description or "").strip()
        self.destination = str(self.destination or "").strip()
        self.trip_type = str(self.trip_type or "").strip().lower()
        self.budget_tier = str(self.budget_tier or "").strip().lower()
        self.difficulty_level = str(self.difficulty_level or "").strip().lower()
        self.pace_level = str(self.pace_level or "").strip().lower()
        self.group_size_label = str(self.group_size_label or "").strip()
        self.includes_label = str(self.includes_label or "").strip()
        if self.ends_at and self.starts_at and self.ends_at < self.starts_at:
            raise ValidationError({"ends_at": "End time must be after the start time."})

    def get_absolute_url(self) -> str:
        return f"/trips/{self.pk}/"

    def to_trip_data(self) -> TripData:
        trip_id = int(self.pk or 0)
        trip_data: TripData = {
            "id": trip_id,
            "title": self.title,
            "summary": self.summary,
            "description": self.description,
            "destination": self.destination,
            "host_username": str(getattr(self.host, "username", "") or "").strip(),
            "traffic_score": int(self.traffic_score or 0),
            "starts_at": self.starts_at,
            "url": self.get_absolute_url(),
        }
        if self.banner_image:
            banner_url = resolve_file_url(self.banner_image)
            banner_name = str(getattr(self.banner_image, "name", "") or "").strip()
            if should_use_fallback_file_url(banner_url):
                banner_url = build_trip_banner_fallback_url(
                    trip_id=trip_id,
                    file_name=banner_name,
                    updated_at=self.updated_at,
                )
            if banner_url:
                trip_data["banner_image_url"] = banner_url
        if self.trip_type:
            trip_data["trip_type"] = self.trip_type
        if self.budget_tier:
            trip_data["budget_tier"] = self.budget_tier
        if self.difficulty_level:
            trip_data["difficulty_level"] = self.difficulty_level
        if self.pace_level:
            trip_data["pace_level"] = self.pace_level
        if self.group_size_label:
            trip_data["group_size_label"] = self.group_size_label
        if self.includes_label:
            trip_data["includes_label"] = self.includes_label
        if self.ends_at is not None:
            trip_data["ends_at"] = self.ends_at
        return trip_data


MINE_TABS: Final[tuple[str, ...]] = ("upcoming", "hosting", "past", "saved")
TRIP_DURATION_FILTER_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("all", "Any duration"),
    ("short", "1-3 days"),
    ("medium", "4-7 days"),
    ("long", "8+ days"),
)
TRIP_TYPE_FILTER_OPTIONS: Final[tuple[tuple[str, str], ...]] = (("all", "Any trip type"), *TRIP_TYPE_CHOICES)
TRIP_BUDGET_FILTER_OPTIONS: Final[tuple[tuple[str, str], ...]] = (("all", "Any budget"), *BUDGET_TIER_CHOICES)
TRIP_DIFFICULTY_FILTER_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("all", "Any difficulty"),
    *DIFFICULTY_LEVEL_CHOICES,
)

TRIP_DURATION_FILTER_VALUES: Final[set[str]] = {item[0] for item in TRIP_DURATION_FILTER_OPTIONS}
TRIP_TYPE_FILTER_VALUES: Final[set[str]] = {item[0] for item in TRIP_TYPE_FILTER_OPTIONS}
TRIP_BUDGET_FILTER_VALUES: Final[set[str]] = {item[0] for item in TRIP_BUDGET_FILTER_OPTIONS}
TRIP_DIFFICULTY_FILTER_VALUES: Final[set[str]] = {item[0] for item in TRIP_DIFFICULTY_FILTER_OPTIONS}


def _as_trip_data_copy(item: TripData) -> TripData:
    return cast(TripData, dict(item))


def _default_trip_filters() -> TripListFilters:
    return {
        "destination": "",
        "duration": "all",
        "trip_type": "all",
        "budget": "all",
        "difficulty": "all",
    }


def normalize_trip_filters(raw_filters: TripListFilters | Mapping[str, object] | None) -> TripListFilters:
    defaults = _default_trip_filters()
    if raw_filters is None:
        return defaults

    destination = str(raw_filters.get("destination", "") or "").strip()
    duration = str(raw_filters.get("duration", "all") or "").strip().lower()
    trip_type = str(raw_filters.get("trip_type", "all") or "").strip().lower()
    budget = str(raw_filters.get("budget", "all") or "").strip().lower()
    difficulty = str(raw_filters.get("difficulty", "all") or "").strip().lower()

    if duration not in TRIP_DURATION_FILTER_VALUES:
        duration = "all"
    if trip_type not in TRIP_TYPE_FILTER_VALUES:
        trip_type = "all"
    if budget not in TRIP_BUDGET_FILTER_VALUES:
        budget = "all"
    if difficulty not in TRIP_DIFFICULTY_FILTER_VALUES:
        difficulty = "all"

    return {
        "destination": destination,
        "duration": duration,
        "trip_type": trip_type,
        "budget": budget,
        "difficulty": difficulty,
    }


def has_active_trip_filters(filters: TripListFilters) -> bool:
    return bool(
        filters["destination"]
        or filters["duration"] != "all"
        or filters["trip_type"] != "all"
        or filters["budget"] != "all"
        or filters["difficulty"] != "all"
    )


def trip_filter_options() -> dict[str, tuple[tuple[str, str], ...]]:
    return {
        "duration": TRIP_DURATION_FILTER_OPTIONS,
        "trip_type": TRIP_TYPE_FILTER_OPTIONS,
        "budget": TRIP_BUDGET_FILTER_OPTIONS,
        "difficulty": TRIP_DIFFICULTY_FILTER_OPTIONS,
    }


def _traffic_score(trip: TripData) -> int:
    try:
        return int(trip.get("traffic_score", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _default_interest_keywords_for_username(username: str) -> set[str]:
    lowered = username.strip().lower()
    if lowered.startswith("m"):
        return {"food", "city", "guide"}
    if lowered.startswith("a"):
        return {"mountain", "trek", "camp"}
    if lowered.startswith("s"):
        return {"desert", "market", "route"}
    return {"trip", "guide"}


def _member_ranking_sets(user: object) -> tuple[set[str], set[str], bool]:
    typed_user = cast(Any, user)
    username = str(getattr(typed_user, "username", "") or "").strip()

    if not bool(getattr(typed_user, "is_authenticated", False)):
        return set(), set(), False

    try:
        preference = cast(MemberFeedPreference, typed_user.feed_preference)
        raw_followed = getattr(preference, "followed_usernames", [])
        raw_interests = getattr(preference, "interest_keywords", [])

        followed_usernames = {
            str(item or "").strip().lower()
            for item in raw_followed
            if str(item or "").strip()
        }
        interest_keywords = {
            str(item or "").strip().lower()
            for item in raw_interests
            if str(item or "").strip()
        }
        if not interest_keywords:
            interest_keywords = _default_interest_keywords_for_username(username)
        return followed_usernames, interest_keywords, True
    except (MemberFeedPreference.DoesNotExist, AttributeError):
        return set(), _default_interest_keywords_for_username(username), False


def _content_matches_keywords(keywords: set[str], *values: object) -> bool:
    if not keywords:
        return False
    haystack = " ".join(str(value or "").lower() for value in values)
    return any(keyword in haystack for keyword in keywords)


def _rank_for_guest(trips: list[TripData]) -> list[TripData]:
    return sorted(
        trips,
        key=lambda trip: (
            _traffic_score(trip),
            str(trip.get("title", "")).lower(),
        ),
        reverse=True,
    )


def _rank_for_member(
    trips: list[TripData],
    *,
    followed_usernames: set[str],
    interest_keywords: set[str],
) -> list[TripData]:
    def trip_rank_score(trip: TripData) -> int:
        score = _traffic_score(trip)
        host_username = str(trip.get("host_username", "")).strip().lower()

        if host_username and host_username in followed_usernames:
            score += 10_000

        if _content_matches_keywords(
            interest_keywords,
            trip.get("title"),
            trip.get("summary"),
            trip.get("description"),
            trip.get("destination"),
        ):
            score += 700

        return score

    return sorted(
        trips,
        key=lambda trip: (trip_rank_score(trip), str(trip.get("title", "")).lower()),
        reverse=True,
    )


def _guest_limited_detail(trip: TripData) -> TripData:
    limited = _as_trip_data_copy(trip)
    source_text = str(limited.get("summary") or limited.get("description") or "").strip()

    if source_text:
        if len(source_text) > 220:
            source_text = f"{source_text[:217].rstrip()}..."
        source_text = f"{source_text} Log in to view the full itinerary, join details, and host notes."
    else:
        source_text = "Log in to view the full itinerary, join details, and host notes."

    limited["description"] = source_text
    return limited


def _trip_matches_filters(trip: TripData, filters: TripListFilters) -> bool:
    destination_filter = filters["destination"].strip().lower()
    if destination_filter:
        searchable_destination = " ".join(
            str(value or "").lower()
            for value in (
                trip.get("destination"),
                trip.get("title"),
                trip.get("summary"),
            )
        )
        if destination_filter not in searchable_destination:
            return False

    if filters["duration"] != "all":
        if str(trip.get("duration_bucket", "") or "").strip().lower() != filters["duration"]:
            return False

    if filters["trip_type"] != "all":
        if str(trip.get("trip_type", "") or "").strip().lower() != filters["trip_type"]:
            return False

    if filters["budget"] != "all":
        if str(trip.get("budget_tier", "") or "").strip().lower() != filters["budget"]:
            return False

    if filters["difficulty"] != "all":
        if str(trip.get("difficulty_level", "") or "").strip().lower() != filters["difficulty"]:
            return False

    return True


def normalize_mine_tab(raw_tab: str) -> str:
    normalized = raw_tab.strip().lower()
    if normalized in MINE_TABS:
        return normalized
    return "upcoming"


def _live_trip_rows() -> list[Trip]:
    return list(
        Trip.objects.select_related("host")
        .filter(is_published=True)
        .order_by("starts_at", "pk")
    )


def _saved_trip_ids_for_member(user: object, *, limit: int | None = None) -> list[int]:
    try:
        bookmark_model = apps.get_model("social", "Bookmark")
    except LookupError:
        return []

    queryset = bookmark_model.objects.filter(
        member=user,
        target_type="trip",
    ).order_by("-created_at", "-pk")

    effective_limit = None if limit is None else max(1, int(limit or 1))
    saved_ids: list[int] = []
    seen_ids: set[int] = set()
    for bookmark in queryset:
        target_key = str(getattr(bookmark, "target_key", "") or "").strip()
        if not target_key.isdigit():
            continue

        trip_id = int(target_key)
        if trip_id <= 0 or trip_id in seen_ids:
            continue

        seen_ids.add(trip_id)
        saved_ids.append(trip_id)

        if effective_limit is not None and len(saved_ids) >= effective_limit:
            break

    return saved_ids


def _saved_trip_rows_for_member(user: object, *, limit: int) -> list[Trip]:
    saved_ids = _saved_trip_ids_for_member(user, limit=limit)
    if not saved_ids:
        return []

    trip_rows = Trip.objects.select_related("host").filter(pk__in=saved_ids)
    trip_map: dict[int, Trip] = {int(trip.pk): trip for trip in trip_rows}
    return [trip_map[trip_id] for trip_id in saved_ids if trip_id in trip_map]


def _saved_trip_count_for_member(user: object) -> int:
    return len(_saved_trip_ids_for_member(user))


def build_trip_list_payload_for_user(
    user: object,
    limit: int = 24,
    *,
    filters: TripListFilters | Mapping[str, object] | None = None,
) -> TripListPayload:
    effective_limit = max(1, int(limit or 24))
    normalized_filters = normalize_trip_filters(filters)

    live_rows = _live_trip_rows()
    source = "live-db"
    candidate_trips = [trip.to_trip_data() for trip in live_rows]

    if not candidate_trips and demo_catalog_enabled():
        source = "demo-fallback"
        candidate_trips = [_as_trip_data_copy(item) for item in get_demo_trips()]

    enriched_candidates = [enrich_trip_preview_fields(item) for item in candidate_trips]
    total_count = len(enriched_candidates)
    filtered_candidates = [trip for trip in enriched_candidates if _trip_matches_filters(trip, normalized_filters)]
    filtered_count = len(filtered_candidates)
    active_filters = has_active_trip_filters(normalized_filters)

    if bool(getattr(user, "is_authenticated", False)):
        followed_usernames, interest_keywords, has_saved_preference = _member_ranking_sets(user)
        ranked_trips = _rank_for_member(
            filtered_candidates,
            followed_usernames=followed_usernames,
            interest_keywords=interest_keywords,
        )

        reason = "Trips ranked using followed hosts and like-minded topic boosts."
        if not has_saved_preference:
            reason = "Trips ranked with fallback member interests until preferences are saved."
        if active_filters and filtered_count > 0:
            reason = "Trips filtered first, then ranked using followed hosts and like-minded topic boosts."
        elif active_filters and filtered_count == 0:
            reason = "No trips match the selected filters yet."

        mode = "member-like-minded-live" if source == "live-db" else "member-like-minded-demo"
        return {
            "trips": ranked_trips[:effective_limit],
            "mode": mode,
            "reason": reason,
            "source": source,
            "filters": normalized_filters,
            "total_count": total_count,
            "filtered_count": filtered_count,
        }

    ranked_trips = _rank_for_guest(filtered_candidates)
    mode = "guest-trending-live" if source == "live-db" else "guest-trending-demo"
    reason = "Trips ranked by global demand signals for guests."
    if active_filters and filtered_count > 0:
        reason = "Trips filtered first, then ranked by global demand signals for guests."
    elif active_filters and filtered_count == 0:
        reason = "No trips match the selected filters yet."

    return {
        "trips": ranked_trips[:effective_limit],
        "mode": mode,
        "reason": reason,
        "source": source,
        "filters": normalized_filters,
        "total_count": total_count,
        "filtered_count": filtered_count,
    }


def build_trip_detail_payload_for_user(user: object, trip_id: int) -> TripDetailPayload:
    viewer_is_member = bool(getattr(user, "is_authenticated", False))
    viewer_id = int(getattr(user, "pk", 0) or 0)

    live_row = Trip.objects.select_related("host").filter(pk=trip_id).first()
    live_row_host_id = int(getattr(live_row, "host_id", 0) or 0) if live_row is not None else 0

    trip_data: TripData
    source: str
    can_manage_trip: bool = False

    if live_row is not None and (
        live_row.is_published or (viewer_is_member and live_row_host_id == viewer_id)
    ):
        trip_data = live_row.to_trip_data()
        source = "live-db"
        can_manage_trip = bool(viewer_is_member and live_row_host_id == viewer_id)
    else:
        demo_trip = get_trip_by_id(trip_id) if demo_catalog_enabled() else None
        if demo_trip is not None:
            trip_data = _as_trip_data_copy(demo_trip)
            source = "demo-fallback"
        else:
            trip_data = {
                "id": trip_id,
                "title": f"Trip #{trip_id}",
                "summary": "Trip record not found.",
                "description": "Trip record is not available in live storage or demo fallback data.",
                "url": f"/trips/{trip_id}/",
            }
            source = "synthetic-fallback"

    enriched_trip = enrich_trip_preview_fields(trip_data)

    if viewer_is_member:
        mode = "member-full"
        reason = "Members see full trip details and available actions."
        visible_trip = enriched_trip
    else:
        mode = "guest-limited"
        reason = "Guests see a limited preview until they authenticate."
        visible_trip = _guest_limited_detail(enriched_trip)

    return {
        "trip": visible_trip,
        "mode": mode,
        "reason": reason,
        "source": source,
        "can_manage_trip": can_manage_trip,
    }


def build_my_trips_payload_for_member(
    user: object,
    *,
    tab: str = "upcoming",
    limit: int = 24,
) -> TripMinePayload:
    effective_tab = normalize_mine_tab(tab)
    effective_limit = max(1, int(limit or 24))

    if not bool(getattr(user, "is_authenticated", False)):
        return {
            "trips": [],
            "active_tab": effective_tab,
            "tab_counts": {"upcoming": 0, "hosting": 0, "past": 0, "saved": 0},
            "mode": "guest-not-allowed",
            "reason": "This page is member-only.",
        }

    typed_user = cast(Any, user)
    hosted_qs = Trip.objects.select_related("host").filter(host=typed_user).order_by("starts_at", "pk")
    now = timezone.now()

    upcoming_qs = hosted_qs.filter(starts_at__gte=now)
    past_qs = hosted_qs.filter(starts_at__lt=now)

    if effective_tab == "hosting":
        selected_rows = list(hosted_qs[:effective_limit])
        reason = "All trips hosted by the current member account."
    elif effective_tab == "past":
        selected_rows = list(past_qs[:effective_limit])
        reason = "Hosted trips that have already started."
    elif effective_tab == "saved":
        selected_rows = _saved_trip_rows_for_member(typed_user, limit=effective_limit)
        reason = "Saved tab is sourced from social bookmarks."
    else:
        selected_rows = list(upcoming_qs[:effective_limit])
        reason = "Upcoming hosted trips ordered by start time."

    saved_count = _saved_trip_count_for_member(typed_user)

    return {
        "trips": [enrich_trip_preview_fields(trip.to_trip_data()) for trip in selected_rows],
        "active_tab": effective_tab,
        "tab_counts": {
            "upcoming": upcoming_qs.count(),
            "hosting": hosted_qs.count(),
            "past": past_qs.count(),
            "saved": saved_count,
        },
        "mode": "member-mine-hosted",
        "reason": reason,
    }
