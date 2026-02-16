from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
import re
from typing import Any, NotRequired, TypeVar, TypedDict, cast

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models

from tapne.features import demo_catalog_enabled
from tapne.storage_urls import build_trip_banner_fallback_url, resolve_file_url, should_use_fallback_file_url


class TripData(TypedDict):
    id: int
    title: str
    summary: NotRequired[str]
    description: NotRequired[str]
    destination: NotRequired[str]
    banner_image_url: NotRequired[str]
    host_username: NotRequired[str]
    is_bookmarked: NotRequired[bool]
    traffic_score: NotRequired[int]
    url: NotRequired[str]
    starts_at: NotRequired[datetime | str]
    ends_at: NotRequired[datetime | str]
    date_label: NotRequired[str]
    season_label: NotRequired[str]
    duration_days: NotRequired[int]
    duration_bucket: NotRequired[str]
    duration_label: NotRequired[str]
    trip_type: NotRequired[str]
    trip_type_label: NotRequired[str]
    budget_tier: NotRequired[str]
    budget_label: NotRequired[str]
    budget_range_label: NotRequired[str]
    cost_label: NotRequired[str]
    difficulty_level: NotRequired[str]
    difficulty_label: NotRequired[str]
    pace_level: NotRequired[str]
    pace_label: NotRequired[str]
    group_size_label: NotRequired[str]
    spots_left_label: NotRequired[str]
    includes_label: NotRequired[str]
    highlights: NotRequired[list[str]]


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


class HomeFeedPayload(TypedDict):
    trips: list[TripData]
    profiles: list[ProfileData]
    blogs: list[BlogData]
    mode: str
    reason: str


class MemberFeedPreference(models.Model):
    """
    Lightweight member feed preferences used to shape home ordering.

    This keeps feed personalization in the feed app even before dedicated
    follow/search analytics apps are implemented.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="feed_preference",
    )
    followed_usernames: models.JSONField[list[str]] = models.JSONField(
        default=list,
        blank=True,
        help_text="Preferred creators for ranking boosts (stored lowercase).",
    )
    interest_keywords: models.JSONField[list[str]] = models.JSONField(
        default=list,
        blank=True,
        help_text="Topic hints that boost related trips/blogs.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user__username",)

    def __str__(self) -> str:
        return f"Feed preference for @{self.user.get_username()}"

    def clean_followed_usernames(self) -> list[str]:
        raw_values = _as_object_list(getattr(self, "followed_usernames", []))
        return _clean_string_list(raw_values, lower=True)

    def clean_interest_keywords(self) -> list[str]:
        raw_values = _as_object_list(getattr(self, "interest_keywords", []))
        return _clean_string_list(raw_values, lower=True)

    def save(
        self,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        # Persist normalized lowercase arrays for predictable ranking behavior.
        self.followed_usernames = self.clean_followed_usernames()
        self.interest_keywords = self.clean_interest_keywords()
        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )


DEMO_TRIPS: tuple[TripData, ...] = (
    {
        "id": 101,
        "title": "Kyoto food lanes weekend",
        "summary": "A compact culinary walk through Nishiki, neighborhood izakaya spots, and hidden tea counters.",
        "destination": "Kyoto, Japan",
        "host_username": "mei",
        "traffic_score": 92,
        "date_label": "Apr 18-20, 2026",
        "season_label": "Spring",
        "duration_days": 3,
        "trip_type": "food-culture",
        "budget_tier": "mid",
        "difficulty_level": "easy",
        "pace_level": "balanced",
        "group_size_label": "6-10 travelers",
        "includes_label": "Host planning support, local route guidance, and group coordination. Booking remains self-managed.",
        "url": "/trips/101/",
    },
    {
        "id": 102,
        "title": "Patagonia first-light trekking camp",
        "summary": "Five-day route with sunrise ridge points, weather-safe camps, and a photographer-friendly pace.",
        "destination": "El Chalten, Argentina",
        "host_username": "arun",
        "traffic_score": 87,
        "date_label": "May 14-18, 2026",
        "season_label": "Fall",
        "duration_days": 5,
        "trip_type": "trekking",
        "budget_tier": "premium",
        "difficulty_level": "challenging",
        "pace_level": "balanced",
        "group_size_label": "6-8 travelers",
        "includes_label": "Host planning support, safety briefings, and route pacing. Flights and lodging are booked directly by members.",
        "url": "/trips/102/",
    },
    {
        "id": 103,
        "title": "Morocco souk to desert circuit",
        "summary": "Markets in Marrakech, Atlas crossings, and a two-night Sahara camp for first-time route builders.",
        "destination": "Marrakech to Merzouga",
        "host_username": "sahar",
        "traffic_score": 81,
        "date_label": "Sep 6-10, 2026",
        "season_label": "Fall",
        "duration_days": 5,
        "trip_type": "desert",
        "budget_tier": "mid",
        "difficulty_level": "moderate",
        "pace_level": "balanced",
        "group_size_label": "8-12 travelers",
        "includes_label": "Host planning support, transfer sequencing, and camp coordination. Members book transport and stays directly.",
        "url": "/trips/103/",
    },
)

TRIP_TYPE_LABELS: dict[str, str] = {
    "food-culture": "Food & Culture",
    "trekking": "Trekking",
    "desert": "Desert Route",
    "city": "City Discovery",
    "coastal": "Coastal Escape",
    "adventure": "Adventure",
}
DEFAULT_TRIP_BANNER_PATH: str = "img/trip-banners/adventure.svg"
TRIP_TYPE_BANNER_PATHS: dict[str, str] = {
    "food-culture": "img/trip-banners/food-culture.svg",
    "trekking": "img/trip-banners/trekking.svg",
    "desert": "img/trip-banners/desert.svg",
    "city": "img/trip-banners/city.svg",
    "coastal": "img/trip-banners/coastal.svg",
    "adventure": DEFAULT_TRIP_BANNER_PATH,
}
BUDGET_LABELS: dict[str, str] = {
    "budget": "$ Budget-friendly",
    "mid": "$$ Mid-range",
    "premium": "$$$ Premium",
}
BUDGET_RANGE_LABELS: dict[str, str] = {
    "budget": "$450-$900 (est.)",
    "mid": "$900-$1,800 (est.)",
    "premium": "$1,800-$3,500 (est.)",
}
DIFFICULTY_LABELS: dict[str, str] = {
    "easy": "Easy",
    "moderate": "Moderate",
    "challenging": "Challenging",
}
PACE_LABELS: dict[str, str] = {
    "relaxed": "Relaxed",
    "balanced": "Balanced",
    "fast": "Fast-paced",
}
SEASON_BY_MONTH: dict[int, str] = {
    12: "Winter",
    1: "Winter",
    2: "Winter",
    3: "Spring",
    4: "Spring",
    5: "Spring",
    6: "Summer",
    7: "Summer",
    8: "Summer",
    9: "Fall",
    10: "Fall",
    11: "Fall",
}

DEMO_PROFILES: tuple[ProfileData, ...] = (
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
    {
        "id": 203,
        "username": "sahar",
        "bio": "Market-to-desert host combining cultural routes and practical logistics.",
        "followers_count": 2240,
        "trips_count": 9,
        "url": "/u/sahar/",
    },
)

DEMO_BLOGS: tuple[BlogData, ...] = (
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
    {
        "id": 303,
        "slug": "how-to-run-a-desert-route",
        "title": "How to run a desert route without chaos",
        "excerpt": "A logistics-first system for market pickups, long transfers, and camp sequencing.",
        "author_username": "sahar",
        "reads": 6100,
        "reviews_count": 76,
        "url": "/blogs/how-to-run-a-desert-route/",
        "body": "Fix transport and hydration constraints early, then fit storytelling around reliable checkpoints.",
    },
)


def _clone_dict_sequence(items: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    return [dict(item) for item in items]


def _as_object_list(value: object) -> list[object]:
    if isinstance(value, list):
        return cast(list[object], value)
    return []


def _clean_string_list(values: Iterable[object], *, lower: bool) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue

        normalized = value.lower() if lower else value
        if normalized in seen:
            continue

        seen.add(normalized)
        cleaned.append(normalized)

    return cleaned


def _matches(query: str, *values: object) -> bool:
    normalized = query.strip().lower()
    if not normalized:
        return True

    for value in values:
        if normalized in str(value or "").lower():
            return True
    return False


def _content_matches_keywords(keywords: set[str], *values: object) -> bool:
    if not keywords:
        return False

    haystack = " ".join(str(value or "").lower() for value in values)
    return any(keyword in haystack for keyword in keywords)


def _trip_text_blob(trip: TripData) -> str:
    return " ".join(
        str(value or "").lower()
        for value in (
            trip.get("title"),
            trip.get("summary"),
            trip.get("description"),
            trip.get("destination"),
        )
    )


def _join_static_url(path: str) -> str:
    cleaned_path = str(path or "").strip().lstrip("/")
    if not cleaned_path:
        cleaned_path = DEFAULT_TRIP_BANNER_PATH

    static_url = str(getattr(settings, "STATIC_URL", "/static/") or "/static/").strip()
    if not static_url:
        static_url = "/static/"
    if not static_url.endswith("/"):
        static_url = f"{static_url}/"

    return f"{static_url}{cleaned_path}"


def _default_trip_banner_url(trip_type: str) -> str:
    normalized_trip_type = str(trip_type or "").strip().lower()
    banner_path = TRIP_TYPE_BANNER_PATHS.get(normalized_trip_type, DEFAULT_TRIP_BANNER_PATH)
    return _join_static_url(banner_path)


def _as_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
    return None


def _duration_days_from_dates(starts_at: datetime | None, ends_at: datetime | None) -> int:
    if starts_at is None or ends_at is None or ends_at < starts_at:
        return 0
    total_seconds = (ends_at - starts_at).total_seconds()
    # Round partial days up so a 2.5 day route surfaces as 3 days.
    return max(1, int((total_seconds + 86_399) // 86_400))


def _format_date_label(starts_at: datetime | None, ends_at: datetime | None) -> str:
    if starts_at is None and ends_at is None:
        return "Dates announced soon"
    if starts_at is None:
        if ends_at is None:
            return "Dates announced soon"
        return f"Ends {ends_at:%b} {ends_at.day}, {ends_at.year}"
    if ends_at is None:
        return f"Starts {starts_at:%b} {starts_at.day}, {starts_at.year}"
    if ends_at < starts_at:
        return f"Starts {starts_at:%b} {starts_at.day}, {starts_at.year}"

    if starts_at.year == ends_at.year and starts_at.month == ends_at.month:
        return f"{starts_at:%b} {starts_at.day}-{ends_at.day}, {starts_at.year}"
    if starts_at.year == ends_at.year:
        return f"{starts_at:%b} {starts_at.day} - {ends_at:%b} {ends_at.day}, {starts_at.year}"
    return f"{starts_at:%b} {starts_at.day}, {starts_at.year} - {ends_at:%b} {ends_at.day}, {ends_at.year}"


def _duration_bucket(days: int) -> str:
    if days <= 3:
        return "short"
    if days <= 7:
        return "medium"
    return "long"


def _infer_trip_type(text_blob: str) -> str:
    if any(token in text_blob for token in ("food", "culinary", "souk", "market", "tea", "izakaya")):
        return "food-culture"
    if any(token in text_blob for token in ("desert", "sahara", "dune")):
        return "desert"
    if any(token in text_blob for token in ("trek", "hike", "mountain", "camp", "ridge", "alpine")):
        return "trekking"
    if any(token in text_blob for token in ("city", "urban", "neighborhood", "street", "lanes")):
        return "city"
    if any(token in text_blob for token in ("shore", "beach", "island", "sea")):
        return "coastal"
    return "adventure"


def _infer_budget_tier(text_blob: str, trip_type: str) -> str:
    if any(token in text_blob for token in ("luxury", "premium", "private")):
        return "premium"
    if any(token in text_blob for token in ("budget", "backpack", "hostel")):
        return "budget"
    if trip_type in {"trekking", "coastal"}:
        return "premium"
    return "mid"


def _infer_difficulty(text_blob: str, trip_type: str) -> str:
    if any(token in text_blob for token in ("easy", "beginner", "first-time", "leisure")):
        return "easy"
    if any(token in text_blob for token in ("advanced", "technical", "steep", "high-altitude", "challenging")):
        return "challenging"
    if trip_type == "trekking":
        return "challenging"
    return "moderate"


def _infer_pace(text_blob: str) -> str:
    if any(token in text_blob for token in ("relaxed", "slow", "leisure", "easygoing")):
        return "relaxed"
    if any(token in text_blob for token in ("fast", "packed", "intense", "rapid")):
        return "fast"
    return "balanced"


def _infer_group_size_label(text_blob: str, trip_type: str) -> str:
    if any(token in text_blob for token in ("private", "small group", "intimate")):
        return "4-6 travelers"
    if any(token in text_blob for token in ("community", "large group", "big group")):
        return "10-14 travelers"
    if trip_type == "trekking":
        return "6-8 travelers"
    if trip_type == "desert":
        return "8-12 travelers"
    return "6-10 travelers"


def _infer_spots_left_label(group_size_label: str) -> str:
    cleaned = str(group_size_label or "").strip().lower()
    if not cleaned:
        return "Limited spots"

    matches = [int(token) for token in re.findall(r"\d+", cleaned)]
    if not matches:
        return "Limited spots"

    max_size = max(matches)
    if max_size <= 0:
        return "Limited spots"

    return f"{max_size} spot{'s' if max_size != 1 else ''} left"


def enrich_trip_preview_fields(trip: TripData) -> TripData:
    enriched = cast(TripData, dict(trip))
    text_blob = _trip_text_blob(enriched)
    starts_at = _as_datetime(enriched.get("starts_at"))
    ends_at = _as_datetime(enriched.get("ends_at"))

    trip_type = str(enriched.get("trip_type", "") or "").strip().lower()
    if trip_type not in TRIP_TYPE_LABELS:
        trip_type = _infer_trip_type(text_blob)
    enriched["trip_type"] = trip_type
    enriched["trip_type_label"] = TRIP_TYPE_LABELS.get(trip_type, TRIP_TYPE_LABELS["adventure"])

    banner_image_url = str(enriched.get("banner_image_url", "") or "").strip()
    if not banner_image_url:
        banner_image_url = _default_trip_banner_url(trip_type)
    enriched["banner_image_url"] = banner_image_url

    duration_days = int(enriched.get("duration_days", 0) or 0)
    if duration_days <= 0:
        duration_days = _duration_days_from_dates(starts_at, ends_at)
    if duration_days <= 0:
        if "weekend" in text_blob:
            duration_days = 2
        elif "week" in text_blob:
            duration_days = 7
        elif any(token in text_blob for token in ("circuit", "crossing", "expedition", "trek")):
            duration_days = 5
        else:
            duration_days = 4

    enriched["duration_days"] = duration_days
    enriched["duration_bucket"] = _duration_bucket(duration_days)
    enriched["duration_label"] = f"{duration_days} day{'s' if duration_days != 1 else ''}"

    if not str(enriched.get("date_label", "") or "").strip():
        enriched["date_label"] = _format_date_label(starts_at, ends_at)

    if not str(enriched.get("season_label", "") or "").strip():
        if starts_at is not None:
            enriched["season_label"] = SEASON_BY_MONTH.get(starts_at.month, "Year-round")
        else:
            enriched["season_label"] = "Year-round"

    budget_tier = str(enriched.get("budget_tier", "") or "").strip().lower()
    if budget_tier not in BUDGET_LABELS:
        budget_tier = _infer_budget_tier(text_blob, trip_type)
    enriched["budget_tier"] = budget_tier
    enriched["budget_label"] = BUDGET_LABELS.get(budget_tier, BUDGET_LABELS["mid"])
    enriched["budget_range_label"] = BUDGET_RANGE_LABELS.get(budget_tier, BUDGET_RANGE_LABELS["mid"])
    if not str(enriched.get("cost_label", "") or "").strip():
        enriched["cost_label"] = str(enriched.get("budget_range_label", "") or "").strip() or str(
            enriched.get("budget_label", "") or ""
        ).strip() or BUDGET_LABELS["mid"]

    difficulty_level = str(enriched.get("difficulty_level", "") or "").strip().lower()
    if difficulty_level not in DIFFICULTY_LABELS:
        difficulty_level = _infer_difficulty(text_blob, trip_type)
    enriched["difficulty_level"] = difficulty_level
    enriched["difficulty_label"] = DIFFICULTY_LABELS.get(difficulty_level, DIFFICULTY_LABELS["moderate"])

    pace_level = str(enriched.get("pace_level", "") or "").strip().lower()
    if pace_level not in PACE_LABELS:
        pace_level = _infer_pace(text_blob)
    enriched["pace_level"] = pace_level
    enriched["pace_label"] = PACE_LABELS.get(pace_level, PACE_LABELS["balanced"])

    if not str(enriched.get("group_size_label", "") or "").strip():
        enriched["group_size_label"] = _infer_group_size_label(text_blob, trip_type)
    if not str(enriched.get("spots_left_label", "") or "").strip():
        enriched["spots_left_label"] = _infer_spots_left_label(str(enriched.get("group_size_label", "") or ""))

    if not str(enriched.get("includes_label", "") or "").strip():
        enriched["includes_label"] = (
            "Host planning support, route guidance, and group coordination. "
            "Bookings are self-managed by members."
        )

    raw_highlights = enriched.get("highlights")
    if not isinstance(raw_highlights, list) or not raw_highlights:
        enriched["highlights"] = [
            str(enriched.get("duration_label", "")),
            str(enriched.get("difficulty_label", "")),
            str(enriched.get("pace_label", "")),
            str(enriched.get("budget_label", "")),
        ]

    return enriched


def _default_interest_keywords_for_username(username: str) -> list[str]:
    lowered = username.strip().lower()
    if lowered.startswith("m"):
        return ["food", "city", "guide"]
    if lowered.startswith("a"):
        return ["mountain", "trek", "camp"]
    if lowered.startswith("s"):
        return ["desert", "market", "route"]
    return ["trip", "guide"]


def _member_preference_sets(user: object) -> tuple[set[str], set[str], bool]:
    typed_user = cast(Any, user)
    username = str(getattr(typed_user, "username", "")).strip()

    if not bool(getattr(typed_user, "is_authenticated", False)):
        return set(), set(), False

    try:
        preference: MemberFeedPreference = cast(MemberFeedPreference, typed_user.feed_preference)
        followed = set(preference.clean_followed_usernames())
        interests = set(preference.clean_interest_keywords())
        if not interests:
            interests = set(_default_interest_keywords_for_username(username))
        return followed, interests, True
    except MemberFeedPreference.DoesNotExist:
        fallback_interests = set(_default_interest_keywords_for_username(username))
        return set(), fallback_interests, False


def get_demo_trips() -> list[TripData]:
    demo_rows = cast(list[TripData], _clone_dict_sequence(cast(Iterable[dict[str, object]], DEMO_TRIPS)))
    return [enrich_trip_preview_fields(row) for row in demo_rows]


def get_demo_profiles() -> list[ProfileData]:
    return cast(list[ProfileData], _clone_dict_sequence(cast(Iterable[dict[str, object]], DEMO_PROFILES)))


def get_demo_blogs() -> list[BlogData]:
    return cast(list[BlogData], _clone_dict_sequence(cast(Iterable[dict[str, object]], DEMO_BLOGS)))


def get_trip_by_id(trip_id: int) -> TripData | None:
    trip = next((item for item in DEMO_TRIPS if item["id"] == trip_id), None)
    if trip is None:
        return None
    return enrich_trip_preview_fields(cast(TripData, dict(trip)))


def get_blog_by_slug(slug: str) -> BlogData | None:
    blog = next((item for item in DEMO_BLOGS if item["slug"] == slug), None)
    if blog is None:
        return None
    return cast(BlogData, dict(blog))


UserModel = get_user_model()
RowT = TypeVar("RowT")


def _resolve_model(app_label: str, model_name: str) -> type[Any] | None:
    try:
        return cast(type[Any], apps.get_model(app_label, model_name))
    except LookupError:
        return None


def _string_attr(instance: object, *names: str) -> str:
    for name in names:
        value = getattr(instance, name, None)
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
    return ""


def _int_attr(instance: object, *names: str) -> int:
    for name in names:
        value = getattr(instance, name, None)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            text = value.strip()
            if text.isdigit():
                return int(text)
    return 0


def _object_username(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    username = getattr(value, "username", None)
    if isinstance(username, str):
        return username.strip()
    return ""


def _live_trip_rows() -> list[TripData]:
    trip_model = _resolve_model("trips", "Trip")
    if trip_model is None:
        return []

    live_rows: list[TripData] = []
    queryset = (
        trip_model.objects.select_related("host")
        .filter(is_published=True)
        .order_by("-traffic_score", "starts_at", "pk")
    )
    for trip in queryset:
        to_trip_data = getattr(trip, "to_trip_data", None)
        if callable(to_trip_data):
            result = to_trip_data()
            if isinstance(result, dict):
                live_rows.append(enrich_trip_preview_fields(cast(TripData, result)))
                continue

        trip_id = int(getattr(trip, "pk", 0) or 0)
        if trip_id <= 0:
            continue

        payload: TripData = {
            "id": trip_id,
            "title": _string_attr(trip, "title", "name") or f"Trip #{trip_id}",
            "summary": _string_attr(trip, "summary", "excerpt"),
            "description": _string_attr(trip, "description", "details", "body"),
            "destination": _string_attr(trip, "destination", "location"),
            "host_username": _object_username(
                getattr(trip, "host", None)
                or getattr(trip, "creator", None)
                or getattr(trip, "user", None)
                or getattr(trip, "host_username", None)
            ),
            "traffic_score": _int_attr(trip, "traffic_score", "search_count", "views_count"),
            "url": f"/trips/{trip_id}/",
        }

        banner_field = getattr(trip, "banner_image", None)
        if banner_field is not None:
            banner_url = resolve_file_url(banner_field)
            banner_name = str(getattr(banner_field, "name", "") or "").strip()
            if should_use_fallback_file_url(banner_url) and trip_id > 0:
                banner_url = build_trip_banner_fallback_url(
                    trip_id=trip_id,
                    file_name=banner_name,
                    updated_at=getattr(trip, "updated_at", None),
                )
            if banner_url:
                payload["banner_image_url"] = banner_url

        get_absolute_url = getattr(trip, "get_absolute_url", None)
        if callable(get_absolute_url):
            try:
                maybe_url = get_absolute_url()
                if isinstance(maybe_url, str) and maybe_url.strip():
                    payload["url"] = maybe_url
            except Exception:
                pass

        starts_at_value = getattr(trip, "starts_at", None)
        if isinstance(starts_at_value, (datetime, str)):
            payload["starts_at"] = starts_at_value
        ends_at_value = getattr(trip, "ends_at", None)
        if isinstance(ends_at_value, (datetime, str)):
            payload["ends_at"] = ends_at_value

        live_rows.append(enrich_trip_preview_fields(payload))
    return live_rows


def _live_profile_rows() -> list[ProfileData]:
    trip_model = _resolve_model("trips", "Trip")
    follow_model = _resolve_model("social", "FollowRelation")
    profiles: list[ProfileData] = []

    queryset = UserModel.objects.select_related("account_profile").all().order_by("username")
    for user in queryset:
        username = str(getattr(user, "username", "")).strip()
        if not username:
            continue

        user_id = int(getattr(user, "pk", 0) or 0)
        profile = getattr(user, "account_profile", None)
        bio = _string_attr(profile, "bio")
        if not bio:
            bio = "No bio has been added yet."

        followers_count = 0
        if follow_model is not None and user_id > 0:
            followers_count = int(follow_model.objects.filter(following_id=user_id).count())

        trips_count = 0
        if trip_model is not None and user_id > 0:
            trips_count = int(trip_model.objects.filter(host_id=user_id, is_published=True).count())

        profiles.append(
            {
                "id": user_id,
                "username": username,
                "bio": bio,
                "followers_count": followers_count,
                "trips_count": trips_count,
                "url": f"/u/{username}/",
            }
        )

    return profiles


def _live_blog_rows() -> list[BlogData]:
    blog_model = _resolve_model("blogs", "Blog")
    if blog_model is None:
        return []

    live_rows: list[BlogData] = []
    queryset = (
        blog_model.objects.select_related("author")
        .filter(is_published=True)
        .order_by("-reads", "-created_at", "-pk")
    )
    for blog in queryset:
        to_blog_data = getattr(blog, "to_blog_data", None)
        if callable(to_blog_data):
            result = to_blog_data()
            if isinstance(result, dict):
                live_rows.append(cast(BlogData, result))
                continue

        blog_id = int(getattr(blog, "pk", 0) or 0)
        slug = _string_attr(blog, "slug") or f"blog-{blog_id}"
        payload: BlogData = {
            "id": blog_id,
            "slug": slug,
            "title": _string_attr(blog, "title", "headline", "name") or slug.replace("-", " ").title(),
            "excerpt": _string_attr(blog, "excerpt", "summary"),
            "summary": _string_attr(blog, "summary", "excerpt"),
            "author_username": _object_username(
                getattr(blog, "author", None)
                or getattr(blog, "creator", None)
                or getattr(blog, "user", None)
                or getattr(blog, "author_username", None)
            ),
            "reads": _int_attr(blog, "reads", "read_count", "views_count"),
            "reviews_count": _int_attr(blog, "reviews_count", "review_count", "comments_count"),
            "url": f"/blogs/{slug}/",
            "body": _string_attr(blog, "body", "content"),
        }

        get_absolute_url = getattr(blog, "get_absolute_url", None)
        if callable(get_absolute_url):
            try:
                maybe_url = get_absolute_url()
                if isinstance(maybe_url, str) and maybe_url.strip():
                    payload["url"] = maybe_url
            except Exception:
                pass

        live_rows.append(payload)
    return live_rows


def _limit_rows(rows: list[RowT], *, limit: int | None) -> list[RowT]:
    if limit is None:
        return list(rows)
    try:
        effective_limit = int(limit)
    except (TypeError, ValueError):
        effective_limit = 0
    if effective_limit <= 0:
        return []
    return rows[:effective_limit]


def _catalog_candidates(
    *,
    include_profiles: bool = True,
) -> tuple[list[TripData], list[ProfileData], list[BlogData], str]:
    if demo_catalog_enabled():
        demo_profiles = get_demo_profiles() if include_profiles else []
        return get_demo_trips(), demo_profiles, get_demo_blogs(), "demo-catalog"

    live_profiles = _live_profile_rows() if include_profiles else []
    return _live_trip_rows(), live_profiles, _live_blog_rows(), "live-catalog"


def search_trips(query: str) -> list[TripData]:
    return [
        enrich_trip_preview_fields(cast(TripData, dict(trip)))
        for trip in DEMO_TRIPS
        if _matches(query, trip.get("title"), trip.get("summary"), trip.get("destination"))
    ]


def search_profiles(query: str) -> list[ProfileData]:
    return [
        cast(ProfileData, dict(profile))
        for profile in DEMO_PROFILES
        if _matches(query, profile.get("username"), profile.get("bio"))
    ]


def search_blogs(query: str) -> list[BlogData]:
    return [
        cast(BlogData, dict(blog))
        for blog in DEMO_BLOGS
        if _matches(query, blog.get("title"), blog.get("excerpt"), blog.get("author_username"))
    ]


def build_guest_home_payload(
    limit_per_section: int | None = 6,
    *,
    include_profiles: bool = True,
) -> HomeFeedPayload:
    trip_candidates, profile_candidates, blog_candidates, source = _catalog_candidates(
        include_profiles=include_profiles
    )
    sorted_trips = sorted(
        trip_candidates,
        key=lambda trip: int(trip.get("traffic_score", 0)),
        reverse=True,
    )
    sorted_profiles: list[ProfileData] = []
    if include_profiles:
        sorted_profiles = sorted(
            profile_candidates,
            key=lambda profile: int(profile.get("followers_count", 0)),
            reverse=True,
        )
    sorted_blogs = sorted(
        blog_candidates,
        key=lambda blog: int(blog.get("reads", 0)),
        reverse=True,
    )

    mode = "guest-trending" if source == "demo-catalog" else "guest-trending-live"
    reason = "Traffic-ranked defaults for guests."
    if source == "live-catalog":
        reason = "Traffic-ranked live catalog for guests."

    return {
        "trips": _limit_rows(sorted_trips, limit=limit_per_section),
        "profiles": _limit_rows(sorted_profiles, limit=limit_per_section),
        "blogs": _limit_rows(sorted_blogs, limit=limit_per_section),
        "mode": mode,
        "reason": reason,
    }


def build_member_home_payload(
    user: object,
    limit_per_section: int | None = 6,
    *,
    include_profiles: bool = True,
) -> HomeFeedPayload:
    trip_candidates, profile_candidates, blog_candidates, source = _catalog_candidates(
        include_profiles=include_profiles
    )
    followed_usernames, interest_keywords, has_saved_preference = _member_preference_sets(user)
    viewer_username = str(getattr(user, "username", "")).strip().lower()

    def trip_rank_score(trip: TripData) -> int:
        score = int(trip.get("traffic_score", 0))
        host_username = str(trip.get("host_username", "")).strip().lower()

        # Followed creators should appear earlier for member feed context.
        if host_username and host_username in followed_usernames:
            score += 10_000

        if _content_matches_keywords(
            interest_keywords,
            trip.get("title"),
            trip.get("summary"),
            trip.get("destination"),
        ):
            score += 80

        return score

    def profile_rank_score(profile: ProfileData) -> int:
        score = int(profile.get("followers_count", 0))
        username = str(profile.get("username", "")).strip().lower()

        if username == viewer_username:
            score -= 500
        if username in followed_usernames:
            score += 10_000

        if _content_matches_keywords(interest_keywords, profile.get("bio"), username):
            score += 40

        return score

    def blog_rank_score(blog: BlogData) -> int:
        score = int(blog.get("reads", 0))
        author_username = str(blog.get("author_username", "")).strip().lower()

        if author_username and author_username in followed_usernames:
            score += 10_000

        if _content_matches_keywords(
            interest_keywords,
            blog.get("title"),
            blog.get("excerpt"),
            blog.get("summary"),
        ):
            score += 70

        return score

    sorted_trips = sorted(trip_candidates, key=trip_rank_score, reverse=True)
    sorted_profiles: list[ProfileData] = []
    if include_profiles:
        sorted_profiles = sorted(profile_candidates, key=profile_rank_score, reverse=True)
    sorted_blogs = sorted(blog_candidates, key=blog_rank_score, reverse=True)

    reason = "Followed creators + like-minded topic recommendations."
    if not has_saved_preference:
        reason = "Fallback member personalization using inferred topic interests."
    if source == "live-catalog":
        reason = f"{reason} (live catalog)"

    return {
        "trips": _limit_rows(sorted_trips, limit=limit_per_section),
        "profiles": _limit_rows(sorted_profiles, limit=limit_per_section),
        "blogs": _limit_rows(sorted_blogs, limit=limit_per_section),
        "mode": "member-personalized" if source == "demo-catalog" else "member-personalized-live",
        "reason": reason,
    }


def build_home_payload_for_user(
    user: object,
    limit_per_section: int | None = 6,
    *,
    include_profiles: bool = True,
) -> HomeFeedPayload:
    if bool(getattr(user, "is_authenticated", False)):
        return build_member_home_payload(
            user,
            limit_per_section=limit_per_section,
            include_profiles=include_profiles,
        )
    return build_guest_home_payload(
        limit_per_section=limit_per_section,
        include_profiles=include_profiles,
    )
