from __future__ import annotations

from collections.abc import Iterable
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
)

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
    return cast(list[TripData], _clone_dict_sequence(cast(Iterable[dict[str, object]], DEMO_TRIPS)))


def get_demo_profiles() -> list[ProfileData]:
    return cast(list[ProfileData], _clone_dict_sequence(cast(Iterable[dict[str, object]], DEMO_PROFILES)))


def get_demo_blogs() -> list[BlogData]:
    return cast(list[BlogData], _clone_dict_sequence(cast(Iterable[dict[str, object]], DEMO_BLOGS)))


def get_trip_by_id(trip_id: int) -> TripData | None:
    trip = next((item for item in DEMO_TRIPS if item["id"] == trip_id), None)
    if trip is None:
        return None
    return cast(TripData, dict(trip))


def get_blog_by_slug(slug: str) -> BlogData | None:
    blog = next((item for item in DEMO_BLOGS if item["slug"] == slug), None)
    if blog is None:
        return None
    return cast(BlogData, dict(blog))


def search_trips(query: str) -> list[TripData]:
    return [
        cast(TripData, dict(trip))
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
