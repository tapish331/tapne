from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any, NotRequired, TypedDict, cast

from django.conf import settings
from django.db import models


class TripData(TypedDict):
    id: int
    title: str
    summary: NotRequired[str]
    description: NotRequired[str]
    destination: NotRequired[str]
    host_username: NotRequired[str]
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
    difficulty_level: NotRequired[str]
    difficulty_label: NotRequired[str]
    pace_level: NotRequired[str]
    pace_label: NotRequired[str]
    group_size_label: NotRequired[str]
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
    if any(token in text_blob for token in ("coast", "beach", "island", "sea")):
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


def build_guest_home_payload(limit_per_section: int = 6) -> HomeFeedPayload:
    sorted_trips = sorted(
        get_demo_trips(),
        key=lambda trip: int(trip.get("traffic_score", 0)),
        reverse=True,
    )
    sorted_profiles = sorted(
        get_demo_profiles(),
        key=lambda profile: int(profile.get("followers_count", 0)),
        reverse=True,
    )
    sorted_blogs = sorted(
        get_demo_blogs(),
        key=lambda blog: int(blog.get("reads", 0)),
        reverse=True,
    )

    return {
        "trips": sorted_trips[:limit_per_section],
        "profiles": sorted_profiles[:limit_per_section],
        "blogs": sorted_blogs[:limit_per_section],
        "mode": "guest-trending",
        "reason": "Traffic-ranked defaults for guests.",
    }


def build_member_home_payload(user: object, limit_per_section: int = 6) -> HomeFeedPayload:
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

    sorted_trips = sorted(get_demo_trips(), key=trip_rank_score, reverse=True)
    sorted_profiles = sorted(get_demo_profiles(), key=profile_rank_score, reverse=True)
    sorted_blogs = sorted(get_demo_blogs(), key=blog_rank_score, reverse=True)

    reason = "Followed creators + like-minded topic recommendations."
    if not has_saved_preference:
        reason = "Fallback member personalization using inferred topic interests."

    return {
        "trips": sorted_trips[:limit_per_section],
        "profiles": sorted_profiles[:limit_per_section],
        "blogs": sorted_blogs[:limit_per_section],
        "mode": "member-personalized",
        "reason": reason,
    }


def build_home_payload_for_user(user: object, limit_per_section: int = 6) -> HomeFeedPayload:
    if bool(getattr(user, "is_authenticated", False)):
        return build_member_home_payload(user, limit_per_section=limit_per_section)
    return build_guest_home_payload(limit_per_section=limit_per_section)
