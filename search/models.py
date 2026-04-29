from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone as datetime_timezone
from typing import Any, Callable, Final, Literal, Mapping, TypedDict, cast
from urllib.parse import urlencode

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.utils.dateparse import parse_datetime

from feed.models import (
    BlogData,
    MemberFeedPreference,
    ProfileData,
    TripData,
    enrich_trip_preview_fields,
    get_demo_blogs,
    get_demo_profiles,
    get_demo_trips,
)
from tapne.features import _demo_qs_filter, demo_catalog_enabled, demo_catalog_visible
from tapne.storage_urls import build_trip_banner_fallback_url, resolve_file_url, should_use_fallback_file_url

SearchResultType = Literal["all", "trips", "users", "blogs"]
ALLOWED_SEARCH_RESULT_TYPES: Final[set[str]] = {"all", "trips", "users", "blogs"}
SearchIntent = Literal["all", "trips", "destinations", "stories", "people"]
ALLOWED_SEARCH_INTENTS: Final[set[str]] = {"all", "trips", "destinations", "stories", "people"}
SEARCH_PAGE_SIZE: Final[int] = 12
SEARCH_ALL_PAGE_COMPOSITION: Final[tuple[tuple[str, int], ...]] = (
    ("trips", 5),
    ("destinations", 3),
    ("stories", 2),
    ("people", 2),
)
SEARCH_SORT_OPTIONS: Final[dict[SearchIntent, tuple[tuple[str, str], ...]]] = {
    "all": (("recommended", "Recommended"),),
    "trips": (
        ("best_match", "Best match"),
        ("trending", "Trending"),
        ("soonest_departure", "Soonest departure"),
        ("newest", "Newest"),
    ),
    "destinations": (
        ("best_match", "Best match"),
        ("most_trips", "Most trips"),
        ("trending", "Trending"),
        ("soonest_departure", "Soonest departure"),
    ),
    "stories": (
        ("best_match", "Best match"),
        ("most_read", "Most read"),
        ("newest", "Newest"),
    ),
    "people": (
        ("best_match", "Best match"),
        ("most_followed", "Most followed"),
        ("most_hosted_trips", "Most hosted trips"),
    ),
}
LEGACY_SEARCH_TAB_MAP: Final[dict[str, SearchIntent]] = {
    "trips": "trips",
    "destinations": "destinations",
    "stories": "stories",
    "users": "people",
}
LEGACY_SEARCH_SORT_MAP: Final[dict[str, dict[SearchIntent, str]]] = {
    "popular": {
        "all": "recommended",
        "trips": "trending",
        "destinations": "trending",
        "stories": "most_read",
        "people": "most_followed",
    },
    "recent": {
        "all": "recommended",
        "trips": "newest",
        "destinations": "soonest_departure",
        "stories": "newest",
        "people": "most_followed",
    },
}


class SearchPayload(TypedDict):
    trips: list[TripData]
    profiles: list[ProfileData]
    blogs: list[BlogData]
    mode: str
    reason: str
    query: str
    result_type: SearchResultType


class SearchPagePayload(TypedDict):
    query: str
    intent: SearchIntent
    page: int
    page_size: int
    total_results: int
    showing_from: int
    showing_to: int
    counts: dict[str, int]
    available_sorts: list[dict[str, str]]
    applied_filters: Mapping[str, object]
    available_filters: Mapping[str, object]
    results: list[dict[str, object]]
    meta: dict[str, object]


# Demo-level search demand signals used for guest defaults ("globally most searched").
TRIP_GLOBAL_SEARCH_COUNTS: Final[dict[int, int]] = {
    101: 6_400,
    102: 7_800,
    103: 7_100,
}
PROFILE_GLOBAL_SEARCH_COUNTS: Final[dict[str, int]] = {
    "mei": 8_900,
    "arun": 6_700,
    "sahar": 6_500,
}
BLOG_GLOBAL_SEARCH_COUNTS: Final[dict[str, int]] = {
    "packing-for-swing-weather": 9_300,
    "first-group-trip-ops-checklist": 7_600,
    "how-to-run-a-desert-route": 8_400,
}
UserModel = get_user_model()


def normalize_search_result_type(raw_result_type: str) -> SearchResultType:
    normalized = raw_result_type.strip().lower()
    if normalized in ALLOWED_SEARCH_RESULT_TYPES:
        return cast(SearchResultType, normalized)
    return "all"


def _default_interest_keywords_for_username(username: str) -> list[str]:
    lowered = username.strip().lower()
    if lowered.startswith("m"):
        return ["food", "city", "guide"]
    if lowered.startswith("a"):
        return ["mountain", "trek", "camp"]
    if lowered.startswith("s"):
        return ["desert", "market", "route"]
    return ["trip", "guide"]


def _clean_string_set(values: list[object], *, lower: bool) -> set[str]:
    cleaned: set[str] = set()
    for raw_value in values:
        value = str(raw_value or "").strip()
        if not value:
            continue
        cleaned.add(value.lower() if lower else value)
    return cleaned


def _as_object_list(value: object) -> list[object]:
    if isinstance(value, list):
        return cast(list[object], value)
    return []


def _member_search_context(user: object) -> tuple[set[str], set[str], bool]:
    typed_user = cast(Any, user)
    username = str(getattr(typed_user, "username", "")).strip()

    if not bool(getattr(typed_user, "is_authenticated", False)):
        return set(), set(), False

    try:
        preference = cast(MemberFeedPreference, typed_user.feed_preference)
        raw_followed_usernames = _as_object_list(getattr(preference, "followed_usernames", []))
        raw_interest_keywords = _as_object_list(getattr(preference, "interest_keywords", []))

        followed_usernames = _clean_string_set(
            raw_followed_usernames,
            lower=True,
        )
        interest_keywords = _clean_string_set(
            raw_interest_keywords,
            lower=True,
        )
        if not interest_keywords:
            interest_keywords = set(_default_interest_keywords_for_username(username))
        return followed_usernames, interest_keywords, True
    except ObjectDoesNotExist:
        inferred_keywords = set(_default_interest_keywords_for_username(username))
        return set(), inferred_keywords, False
    except AttributeError:
        inferred_keywords = set(_default_interest_keywords_for_username(username))
        return set(), inferred_keywords, False


def _contains_keyword(keywords: set[str], *values: object) -> bool:
    if not keywords:
        return False
    haystack = " ".join(str(value or "").lower() for value in values)
    return any(keyword in haystack for keyword in keywords)


def _query_match_score(query: str, *values: object) -> int:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return 0

    haystack = " ".join(str(value or "").lower() for value in values)
    if not haystack:
        return 0

    score = 0
    if normalized_query in haystack:
        score += 120

    for token in {piece.strip("@#") for piece in normalized_query.split()}:
        if token and token in haystack:
            score += 40

    return score


def _trip_global_score(trip: TripData) -> int:
    trip_id = int(trip.get("id", 0))
    global_count = TRIP_GLOBAL_SEARCH_COUNTS.get(trip_id, 0)
    return global_count + int(trip.get("traffic_score", 0)) * 10


def _profile_global_score(profile: ProfileData) -> int:
    username = str(profile.get("username", "")).strip().lower()
    global_count = PROFILE_GLOBAL_SEARCH_COUNTS.get(username, 0)
    return global_count + int(profile.get("followers_count", 0)) * 5


def _blog_global_score(blog: BlogData) -> int:
    slug = str(blog.get("slug", "")).strip().lower()
    global_count = BLOG_GLOBAL_SEARCH_COUNTS.get(slug, 0)
    return global_count + int(blog.get("reads", 0))


def _rank_trips(
    *,
    query: str,
    limit_per_section: int,
    score_for_item: Callable[[TripData], int],
) -> list[TripData]:
    trip_candidates = _trip_candidates(query)
    ranked: list[tuple[int, TripData]] = []
    for trip in trip_candidates:
        relevance = _query_match_score(
            query,
            trip.get("title"),
            trip.get("summary"),
            trip.get("description"),
            trip.get("destination"),
            trip.get("host_username"),
        )
        if query and relevance == 0:
            continue

        rank_score = score_for_item(trip)
        if query:
            # Keep lexical relevance dominant when query is provided.
            rank_score += relevance * 1_000
        ranked.append((rank_score, trip))

    ranked.sort(
        key=lambda pair: (pair[0], str(pair[1].get("title", "")).lower()),
        reverse=True,
    )
    return [trip for _, trip in ranked[:limit_per_section]]


def _trip_candidates(query: str) -> list[TripData]:
    """
    In live-only mode, use live published rows for both defaults and queries.
    In demo mode, keep stable demo defaults and merge live rows for both defaults
    and query-time search.
    """

    normalized_query = query.strip()
    if not demo_catalog_enabled():
        return _live_trips_for_query(normalized_query)

    demo_trips = get_demo_trips()

    merged_by_id: dict[int, TripData] = {}
    for trip in demo_trips:
        trip_id = int(trip.get("id", 0))
        if trip_id > 0:
            merged_by_id[trip_id] = trip

    for live_trip in _live_trips_for_query(normalized_query):
        trip_id = int(live_trip.get("id", 0))
        if trip_id <= 0:
            continue
        # Prefer live DB rows over demo placeholders when IDs overlap.
        merged_by_id[trip_id] = live_trip

    return [enrich_trip_preview_fields(cast(TripData, dict(item))) for item in merged_by_id.values()]


def _rank_profiles(
    *,
    query: str,
    limit_per_section: int,
    score_for_item: Callable[[ProfileData], int],
) -> list[ProfileData]:
    profile_candidates = _profile_candidates(query)
    ranked: list[tuple[int, ProfileData]] = []
    for profile in profile_candidates:
        relevance = _query_match_score(
            query,
            profile.get("username"),
            profile.get("bio"),
        )
        if query and relevance == 0:
            continue

        rank_score = score_for_item(profile)
        if query:
            rank_score += relevance * 1_000
        ranked.append((rank_score, profile))

    ranked.sort(
        key=lambda pair: (pair[0], str(pair[1].get("username", "")).lower()),
        reverse=True,
    )
    return [profile for _, profile in ranked[:limit_per_section]]


def _profile_candidates(query: str) -> list[ProfileData]:
    """
    In live-only mode, use live account rows for defaults and queries.
    In demo mode, keep demo defaults and merge in live rows for query-time search.
    """

    normalized_query = query.strip()
    if not demo_catalog_enabled():
        return _live_profiles_for_query(normalized_query)

    demo_profiles = get_demo_profiles()
    if not normalized_query:
        return demo_profiles

    merged_by_username: dict[str, ProfileData] = {}
    for profile in demo_profiles:
        username_key = str(profile.get("username", "")).strip().lower()
        if username_key:
            merged_by_username[username_key] = profile

    for live_profile in _live_profiles_for_query(normalized_query):
        username_key = str(live_profile.get("username", "")).strip().lower()
        if not username_key:
            continue
        # Prefer live DB rows over demo placeholders when usernames overlap.
        merged_by_username[username_key] = live_profile

    return list(merged_by_username.values())


def _live_profiles_for_query(query: str) -> list[ProfileData]:
    normalized_query = query.strip()
    live_profiles: list[ProfileData] = []
    trip_model = _resolve_model("trips", "Trip")
    follow_model = _resolve_model("social", "FollowRelation")
    _profile_filter: dict[str, bool] = {} if demo_catalog_visible() else {"account_profile__is_demo": False}
    users = UserModel.objects.select_related("account_profile").filter(**_profile_filter).order_by("username")
    for user in users:
        username = str(getattr(user, "username", "")).strip()
        if not username:
            continue

        profile = getattr(user, "account_profile", None)
        display_name = str(getattr(profile, "display_name", "") or "").strip()
        bio = str(getattr(profile, "bio", "") or "").strip()
        if not bio:
            bio = "No bio has been added yet."
        location = str(getattr(profile, "location", "") or "").strip()
        website = str(getattr(profile, "website", "") or "").strip()
        email = str(getattr(user, "email", "") or "").strip()
        user_id = int(getattr(user, "pk", 0) or 0)

        if normalized_query and (
            _query_match_score(
                normalized_query,
                username,
                display_name,
                bio,
                location,
                website,
                email,
            )
            == 0
        ):
            continue

        followers_count = 0
        if follow_model is not None and user_id > 0:
            followers_count = int(follow_model.objects.filter(following_id=user_id).count())

        trips_count = 0
        if trip_model is not None and user_id > 0:
            trips_count = int(trip_model.objects.filter(host_id=user_id, is_published=True).count())

        live_profiles.append(
            {
                "id": user_id,
                "username": username,
                "bio": bio,
                "followers_count": followers_count,
                "trips_count": trips_count,
                "url": f"/u/{username}/",
            }
        )

    return live_profiles


def _resolve_model(app_label: str, model_name: str) -> type[Any] | None:
    try:
        return cast(type[Any], apps.get_model(app_label, model_name))
    except LookupError:
        return None


def _object_username(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    username = getattr(value, "username", None)
    if isinstance(username, str):
        return username.strip()
    return ""


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


def _live_trips_for_query(query: str) -> list[TripData]:
    normalized_query = query.strip()
    trip_model = _resolve_model("trips", "Trip")
    if trip_model is None:
        return []

    live_trips: list[TripData] = []
    queryset = trip_model.objects.filter(status="published", **_demo_qs_filter()).order_by("-pk")
    for trip in queryset:
        to_trip_data = getattr(trip, "to_trip_data", None)
        if callable(to_trip_data):
            full_trip_data = to_trip_data()
            if isinstance(full_trip_data, dict):
                trip_payload = cast(TripData, dict(full_trip_data))
                if normalized_query and (
                    _query_match_score(
                        normalized_query,
                        trip_payload.get("title"),
                        trip_payload.get("summary"),
                        trip_payload.get("description"),
                        trip_payload.get("destination"),
                        trip_payload.get("host_username"),
                    )
                    == 0
                ):
                    continue
                live_trips.append(enrich_trip_preview_fields(trip_payload))
                continue

        title = _string_attr(trip, "title", "name")
        summary = _string_attr(trip, "summary", "excerpt")
        description = _string_attr(trip, "description", "details", "body")
        destination = _string_attr(trip, "destination", "location")
        host_username = _object_username(
            getattr(trip, "host", None)
            or getattr(trip, "creator", None)
            or getattr(trip, "user", None)
            or getattr(trip, "host_username", None)
        )

        if normalized_query and (
            _query_match_score(
                normalized_query,
                title,
                summary,
                description,
                destination,
                host_username,
            )
            == 0
        ):
            continue

        trip_id = int(getattr(trip, "pk", 0))
        if trip_id <= 0:
            continue

        url = ""
        get_absolute_url = getattr(trip, "get_absolute_url", None)
        if callable(get_absolute_url):
            try:
                maybe_url = get_absolute_url()
                if isinstance(maybe_url, str):
                    url = maybe_url
            except Exception:
                url = ""
        if not url:
            url = f"/trips/{trip_id}/"

        trip_payload: TripData = {
            "id": trip_id,
            "title": title or f"Trip #{trip_id}",
            "summary": summary,
            "description": description,
            "destination": destination,
            "host_username": host_username,
            "traffic_score": _int_attr(trip, "traffic_score", "search_count", "views_count"),
            "url": url,
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
                trip_payload["banner_image_url"] = banner_url

        starts_at_value = getattr(trip, "starts_at", None)
        if isinstance(starts_at_value, (datetime, str)):
            trip_payload["starts_at"] = starts_at_value

        ends_at_value = getattr(trip, "ends_at", None)
        if isinstance(ends_at_value, (datetime, str)):
            trip_payload["ends_at"] = ends_at_value

        live_trips.append(enrich_trip_preview_fields(trip_payload))

    return live_trips


def _rank_blogs(
    *,
    query: str,
    limit_per_section: int,
    score_for_item: Callable[[BlogData], int],
) -> list[BlogData]:
    blog_candidates = _blog_candidates(query)
    ranked: list[tuple[int, BlogData]] = []
    for blog in blog_candidates:
        relevance = _query_match_score(
            query,
            blog.get("title"),
            blog.get("excerpt"),
            blog.get("summary"),
            blog.get("body"),
            blog.get("author_username"),
        )
        if query and relevance == 0:
            continue

        rank_score = score_for_item(blog)
        if query:
            rank_score += relevance * 1_000
        ranked.append((rank_score, blog))

    ranked.sort(
        key=lambda pair: (pair[0], str(pair[1].get("slug", "")).lower()),
        reverse=True,
    )
    return [blog for _, blog in ranked[:limit_per_section]]


def _blog_candidates(query: str) -> list[BlogData]:
    """
    In live-only mode, use live published blog rows for defaults and queries.
    In demo mode, keep stable demo defaults and merge live rows for query-time search.
    """

    normalized_query = query.strip()
    if not demo_catalog_enabled():
        return _live_blogs_for_query(normalized_query)

    demo_blogs = get_demo_blogs()
    if not normalized_query:
        return demo_blogs

    merged_by_slug: dict[str, BlogData] = {}
    for blog in demo_blogs:
        slug_key = str(blog.get("slug", "")).strip().lower()
        if slug_key:
            merged_by_slug[slug_key] = blog

    for live_blog in _live_blogs_for_query(normalized_query):
        slug_key = str(live_blog.get("slug", "")).strip().lower()
        if not slug_key:
            continue
        # Prefer live DB rows over demo placeholders when slugs overlap.
        merged_by_slug[slug_key] = live_blog

    return list(merged_by_slug.values())


def _live_blogs_for_query(query: str) -> list[BlogData]:
    normalized_query = query.strip()
    blog_model = _resolve_model("blogs", "Blog")
    if blog_model is None:
        return []

    live_blogs: list[BlogData] = []
    queryset = blog_model.objects.all().order_by("-pk")
    for blog in queryset:
        # Search results should not leak unpublished drafts.
        is_published_value = getattr(blog, "is_published", True)
        if isinstance(is_published_value, bool) and not is_published_value:
            continue
        # Respect the demo catalog visibility flag.
        if not demo_catalog_visible() and getattr(blog, "is_demo", False):
            continue

        blog_id = int(getattr(blog, "pk", 0))
        if blog_id <= 0:
            continue

        to_blog_data = getattr(blog, "to_blog_data", None)
        if callable(to_blog_data):
            full_blog_data = to_blog_data()
            if isinstance(full_blog_data, dict):
                blog_payload = cast(BlogData, dict(full_blog_data))
                if normalized_query and (
                    _query_match_score(
                        normalized_query,
                        blog_payload.get("title"),
                        blog_payload.get("excerpt"),
                        blog_payload.get("summary"),
                        blog_payload.get("body"),
                        blog_payload.get("author_username"),
                        blog_payload.get("slug"),
                    )
                    == 0
                ):
                    continue
                live_blogs.append(blog_payload)
                continue

        title = _string_attr(blog, "title", "headline", "name")
        excerpt = _string_attr(blog, "excerpt", "summary")
        summary = _string_attr(blog, "summary", "excerpt")
        body = _string_attr(blog, "body", "content")
        author_username = _object_username(
            getattr(blog, "author", None)
            or getattr(blog, "creator", None)
            or getattr(blog, "user", None)
            or getattr(blog, "author_username", None)
        )
        slug = _string_attr(blog, "slug")
        if not slug:
            slug = f"blog-{blog_id}"

        if normalized_query and (
            _query_match_score(
                normalized_query,
                title,
                excerpt,
                summary,
                body,
                author_username,
                slug,
            )
            == 0
        ):
            continue

        url = ""
        get_absolute_url = getattr(blog, "get_absolute_url", None)
        if callable(get_absolute_url):
            try:
                maybe_url = get_absolute_url()
                if isinstance(maybe_url, str):
                    url = maybe_url
            except Exception:
                url = ""
        if not url:
            url = f"/blogs/{slug}/"

        live_blogs.append(
            {
                "id": blog_id,
                "slug": slug,
                "title": title or f"Blog #{blog_id}",
                "excerpt": excerpt,
                "summary": summary,
                "author_username": author_username,
                "reads": _int_attr(blog, "reads", "read_count", "views_count"),
                "reviews_count": _int_attr(blog, "reviews_count", "review_count", "comments_count"),
                "url": url,
                "body": body,
            }
        )

    return live_blogs


def build_guest_search_payload(
    *,
    query: str,
    result_type: SearchResultType,
    limit_per_section: int = 8,
) -> SearchPayload:
    normalized_query = query.strip()

    trips = _rank_trips(
        query=normalized_query,
        limit_per_section=limit_per_section,
        score_for_item=_trip_global_score,
    )
    profiles = _rank_profiles(
        query=normalized_query,
        limit_per_section=limit_per_section,
        score_for_item=_profile_global_score,
    )
    blogs = _rank_blogs(
        query=normalized_query,
        limit_per_section=limit_per_section,
        score_for_item=_blog_global_score,
    )

    if result_type == "trips":
        profiles = []
        blogs = []
    elif result_type == "users":
        trips = []
        blogs = []
    elif result_type == "blogs":
        trips = []
        profiles = []

    reason = "Global most-searched defaults for guests."
    if normalized_query:
        reason = "Query results ranked by relevance and global search demand."

    return {
        "trips": trips,
        "profiles": profiles,
        "blogs": blogs,
        "mode": "guest-most-searched",
        "reason": reason,
        "query": normalized_query,
        "result_type": result_type,
    }


def build_member_search_payload(
    user: object,
    *,
    query: str,
    result_type: SearchResultType,
    limit_per_section: int = 8,
) -> SearchPayload:
    normalized_query = query.strip()
    followed_usernames, interest_keywords, has_saved_preference = _member_search_context(user)

    def member_trip_score(trip: TripData) -> int:
        score = _trip_global_score(trip)
        host_username = str(trip.get("host_username", "")).strip().lower()

        if host_username in followed_usernames:
            score += 10_000
        if _contains_keyword(
            interest_keywords,
            trip.get("title"),
            trip.get("summary"),
            trip.get("destination"),
        ):
            score += 900
        return score

    def member_profile_score(profile: ProfileData) -> int:
        score = _profile_global_score(profile)
        username = str(profile.get("username", "")).strip().lower()
        if username in followed_usernames:
            # Followed creators should dominate member defaults for profile rows.
            score += 50_000
        if _contains_keyword(
            interest_keywords,
            profile.get("username"),
            profile.get("bio"),
        ):
            score += 450
        return score

    def member_blog_score(blog: BlogData) -> int:
        score = _blog_global_score(blog)
        author_username = str(blog.get("author_username", "")).strip().lower()
        if author_username in followed_usernames:
            score += 10_000
        if _contains_keyword(
            interest_keywords,
            blog.get("title"),
            blog.get("excerpt"),
            blog.get("summary"),
        ):
            score += 700
        return score

    trips = _rank_trips(
        query=normalized_query,
        limit_per_section=limit_per_section,
        score_for_item=member_trip_score,
    )
    profiles = _rank_profiles(
        query=normalized_query,
        limit_per_section=limit_per_section,
        score_for_item=member_profile_score,
    )
    blogs = _rank_blogs(
        query=normalized_query,
        limit_per_section=limit_per_section,
        score_for_item=member_blog_score,
    )

    if result_type == "trips":
        profiles = []
        blogs = []
    elif result_type == "users":
        trips = []
        blogs = []
    elif result_type == "blogs":
        trips = []
        profiles = []

    if normalized_query:
        reason = "Query results ranked by relevance and like-minded demand signals."
    elif has_saved_preference:
        reason = "Most searched by like-minded members and followed creators."
    else:
        reason = "Fallback like-minded defaults using inferred member interests."

    return {
        "trips": trips,
        "profiles": profiles,
        "blogs": blogs,
        "mode": "member-like-minded",
        "reason": reason,
        "query": normalized_query,
        "result_type": result_type,
    }


def build_search_payload_for_user(
    user: object,
    *,
    query: str = "",
    result_type: str = "all",
    limit_per_section: int = 8,
) -> SearchPayload:
    normalized_result_type = normalize_search_result_type(result_type)
    if bool(getattr(user, "is_authenticated", False)):
        return build_member_search_payload(
            user,
            query=query,
            result_type=normalized_result_type,
            limit_per_section=limit_per_section,
        )

    return build_guest_search_payload(
        query=query,
        result_type=normalized_result_type,
        limit_per_section=limit_per_section,
    )


def normalize_search_intent(
    raw_intent: str,
    *,
    raw_tab: str = "",
    destination_filter: str = "",
) -> SearchIntent:
    normalized_intent = raw_intent.strip().lower()
    if normalized_intent in ALLOWED_SEARCH_INTENTS:
        return cast(SearchIntent, normalized_intent)

    normalized_tab = raw_tab.strip().lower()
    if normalized_tab in LEGACY_SEARCH_TAB_MAP:
        return LEGACY_SEARCH_TAB_MAP[normalized_tab]

    if destination_filter.strip():
        return "trips"

    return "all"


def _default_sort_for_intent(intent: SearchIntent, query: str) -> str:
    if intent == "all":
        return "recommended"
    if query.strip():
        return "best_match"
    if intent in {"trips", "destinations"}:
        return "trending"
    if intent == "stories":
        return "most_read"
    return "most_followed"


def normalize_search_sort(raw_sort: str, *, intent: SearchIntent, query: str) -> str:
    allowed_values = {value for value, _label in SEARCH_SORT_OPTIONS[intent]}
    normalized_sort = raw_sort.strip().lower()
    if normalized_sort in allowed_values:
        return normalized_sort

    if normalized_sort in LEGACY_SEARCH_SORT_MAP:
        mapped = LEGACY_SEARCH_SORT_MAP[normalized_sort].get(intent, "")
        if mapped in allowed_values:
            return mapped

    return _default_sort_for_intent(intent, query)


def _normalize_positive_int(raw_value: object, *, default: int) -> int:
    try:
        parsed = int(str(raw_value or "").strip())
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _coerce_int(raw_value: object, *, default: int = 0) -> int:
    if isinstance(raw_value, bool):
        return int(raw_value)
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float):
        return int(raw_value)
    try:
        text = str(raw_value or "").strip()
        if not text:
            return default
        return int(text)
    except (TypeError, ValueError):
        return default


def _normalize_flag(raw_value: object) -> bool:
    return str(raw_value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_token(value: object) -> str:
    return " ".join(str(value or "").replace("_", " ").replace("-", " ").lower().split())


def _safe_datetime_timestamp(value: object) -> float | None:
    if isinstance(value, datetime):
        dt_value = value
    elif isinstance(value, str):
        dt_value = parse_datetime(value.strip())
        if dt_value is None:
            return None
    else:
        return None

    if dt_value.tzinfo is None:
        dt_value = dt_value.replace(tzinfo=datetime_timezone.utc)
    return dt_value.timestamp()


def _datetime_label(value: object) -> str:
    if isinstance(value, datetime):
        dt_value = value
    elif isinstance(value, str):
        dt_value = parse_datetime(value.strip())
        if dt_value is None:
            return ""
    else:
        return ""

    return dt_value.strftime("%b %d, %Y")


def _identity_profile_map(usernames: list[str]) -> dict[str, dict[str, object]]:
    normalized = sorted({str(username or "").strip() for username in usernames if str(username or "").strip()})
    if not normalized:
        return {}

    identity_map: dict[str, dict[str, object]] = {}
    queryset = UserModel.objects.select_related("account_profile").filter(username__in=normalized)
    for user in queryset:
        username = str(getattr(user, "username", "") or "").strip()
        if not username:
            continue

        profile = getattr(user, "account_profile", None)
        display_name = str(getattr(profile, "effective_display_name", "") or "").strip()
        if not display_name:
            full_name_getter = getattr(user, "get_full_name", None)
            if callable(full_name_getter):
                display_name = str(full_name_getter() or "").strip()
        if not display_name:
            display_name = username

        identity_map[username] = {
            "display_name": display_name,
            "bio": str(getattr(profile, "bio", "") or "").strip(),
            "location": str(getattr(profile, "location", "") or "").strip(),
            "avatar_url": str(getattr(profile, "avatar_url", "") or "").strip(),
            "travel_tags": [
                str(item or "").strip()
                for item in list(getattr(profile, "travel_tags", []) or [])
                if str(item or "").strip()
            ],
        }

    return identity_map


def _trip_score_for_user(user: object) -> Callable[[TripData], int]:
    if not bool(getattr(user, "is_authenticated", False)):
        return _trip_global_score

    followed_usernames, interest_keywords, _has_saved_preference = _member_search_context(user)

    def _score(trip: TripData) -> int:
        score = _trip_global_score(trip)
        host_username = str(trip.get("host_username", "") or "").strip().lower()
        if host_username in followed_usernames:
            score += 10_000
        if _contains_keyword(
            interest_keywords,
            trip.get("title"),
            trip.get("summary"),
            trip.get("description"),
            trip.get("destination"),
        ):
            score += 900
        return score

    return _score


def _profile_score_for_user(user: object) -> Callable[[ProfileData], int]:
    if not bool(getattr(user, "is_authenticated", False)):
        return _profile_global_score

    followed_usernames, interest_keywords, _has_saved_preference = _member_search_context(user)

    def _score(profile: ProfileData) -> int:
        score = _profile_global_score(profile)
        username = str(profile.get("username", "") or "").strip().lower()
        if username in followed_usernames:
            score += 50_000
        if _contains_keyword(interest_keywords, profile.get("username"), profile.get("bio")):
            score += 450
        return score

    return _score


def _blog_score_for_user(user: object) -> Callable[[BlogData], int]:
    if not bool(getattr(user, "is_authenticated", False)):
        return _blog_global_score

    followed_usernames, interest_keywords, _has_saved_preference = _member_search_context(user)

    def _score(blog: BlogData) -> int:
        score = _blog_global_score(blog)
        author_username = str(blog.get("author_username", "") or "").strip().lower()
        if author_username in followed_usernames:
            score += 10_000
        if _contains_keyword(
            interest_keywords,
            blog.get("title"),
            blog.get("excerpt"),
            blog.get("summary"),
            blog.get("body"),
        ):
            score += 700
        return score

    return _score


def _trip_rank_rows_for_user(user: object, query: str) -> list[dict[str, object]]:
    score_for_item = _trip_score_for_user(user)
    rows: list[dict[str, object]] = []
    for trip in _trip_candidates(query):
        relevance = _query_match_score(
            query,
            trip.get("title"),
            trip.get("summary"),
            trip.get("description"),
            trip.get("destination"),
            trip.get("host_username"),
        )
        if query and relevance == 0:
            continue

        rows.append(
            {
                "trip": cast(TripData, dict(trip)),
                "base_score": int(score_for_item(trip)),
                "relevance": relevance,
            }
        )

    return rows


def _profile_rank_rows_for_user(user: object, query: str) -> list[dict[str, object]]:
    score_for_item = _profile_score_for_user(user)
    rows: list[dict[str, object]] = []
    for profile in _profile_candidates(query):
        relevance = _query_match_score(
            query,
            profile.get("username"),
            profile.get("bio"),
        )
        if query and relevance == 0:
            continue

        rows.append(
            {
                "profile": cast(ProfileData, dict(profile)),
                "base_score": int(score_for_item(profile)),
                "relevance": relevance,
            }
        )

    return rows


def _blog_rank_rows_for_user(user: object, query: str) -> list[dict[str, object]]:
    score_for_item = _blog_score_for_user(user)
    rows: list[dict[str, object]] = []
    for blog in _blog_candidates(query):
        relevance = _query_match_score(
            query,
            blog.get("title"),
            blog.get("excerpt"),
            blog.get("summary"),
            blog.get("body"),
            blog.get("author_username"),
            blog.get("slug"),
        )
        if query and relevance == 0:
            continue

        rows.append(
            {
                "blog": cast(BlogData, dict(blog)),
                "base_score": int(score_for_item(blog)),
                "relevance": relevance,
            }
        )

    return rows


def _normalize_trip_search_filters(raw_filters: Mapping[str, object] | None) -> dict[str, str]:
    from trips.models import normalize_trip_filters

    filters = normalize_trip_filters(raw_filters)
    return {
        "destination": str(filters.get("destination", "") or "").strip(),
        "duration": str(filters.get("duration", "all") or "all").strip().lower() or "all",
        "trip_type": str(filters.get("trip_type", "all") or "all").strip().lower() or "all",
        "budget": str(filters.get("budget", "all") or "all").strip().lower() or "all",
        "difficulty": str(filters.get("difficulty", "all") or "all").strip().lower() or "all",
    }


def _trip_matches_search_filters(trip: TripData, filters: Mapping[str, object]) -> bool:
    destination_filter = _normalize_token(filters.get("destination", ""))
    if destination_filter:
        searchable_destination = _normalize_token(
            " ".join(
                str(value or "")
                for value in (
                    trip.get("destination"),
                    trip.get("title"),
                    trip.get("summary"),
                )
            )
        )
        if destination_filter not in searchable_destination:
            return False

    duration_value = str(filters.get("duration", "all") or "all").strip().lower()
    if duration_value != "all" and str(trip.get("duration_bucket", "") or "").strip().lower() != duration_value:
        return False

    trip_type_value = str(filters.get("trip_type", "all") or "all").strip().lower()
    if trip_type_value != "all" and str(trip.get("trip_type", "") or "").strip().lower() != trip_type_value:
        return False

    budget_value = str(filters.get("budget", "all") or "all").strip().lower()
    if budget_value != "all" and str(trip.get("budget_tier", "") or "").strip().lower() != budget_value:
        return False

    difficulty_value = str(filters.get("difficulty", "all") or "all").strip().lower()
    if difficulty_value != "all" and str(trip.get("difficulty_level", "") or "").strip().lower() != difficulty_value:
        return False

    return True


def _sort_trip_rows(rows: list[dict[str, object]], *, sort: str) -> list[dict[str, object]]:
    sorted_rows = list(rows)
    if sort == "soonest_departure":
        sorted_rows.sort(
            key=lambda row: (
                _safe_datetime_timestamp(cast(TripData, row["trip"]).get("starts_at")) is None,
                _safe_datetime_timestamp(cast(TripData, row["trip"]).get("starts_at")) or float("inf"),
                -_coerce_int(row.get("base_score", 0)),
                str(cast(TripData, row["trip"]).get("title", "") or "").lower(),
            ),
        )
        return sorted_rows

    if sort == "newest":
        sorted_rows.sort(
            key=lambda row: (
                _coerce_int(cast(TripData, row["trip"]).get("id", 0)),
                _coerce_int(row.get("base_score", 0)),
            ),
            reverse=True,
        )
        return sorted_rows

    if sort == "best_match":
        sorted_rows.sort(
            key=lambda row: (
                _coerce_int(row.get("base_score", 0)) + _coerce_int(row.get("relevance", 0)) * 1_000,
                str(cast(TripData, row["trip"]).get("title", "") or "").lower(),
            ),
            reverse=True,
        )
        return sorted_rows

    sorted_rows.sort(
        key=lambda row: (
            _coerce_int(row.get("base_score", 0)),
            str(cast(TripData, row["trip"]).get("title", "") or "").lower(),
        ),
        reverse=True,
    )
    return sorted_rows


def _trip_results_from_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    usernames = [
        str(cast(TripData, row["trip"]).get("host_username", "") or "").strip()
        for row in rows
        if str(cast(TripData, row["trip"]).get("host_username", "") or "").strip()
    ]
    identity_map = _identity_profile_map(usernames)

    results: list[dict[str, object]] = []
    for row in rows:
        trip = dict(cast(TripData, row["trip"]))
        username = str(trip.get("host_username", "") or "").strip()
        identity = identity_map.get(username, {})
        trip_id = _coerce_int(trip.get("id", 0))
        if identity:
            trip["host_display_name"] = identity.get("display_name", username)
            trip["host_bio"] = identity.get("bio", "")
            trip["host_location"] = identity.get("location", "")
        trip["result_kind"] = "trip"
        trip["url"] = f"/trips/{trip_id}" if trip_id > 0 else str(trip.get("url", "") or "").strip()
        results.append(trip)
    return results


def _normalize_destination_search_filters(raw_filters: Mapping[str, object] | None) -> dict[str, str]:
    trip_filters = _normalize_trip_search_filters(raw_filters)
    return {
        "trip_type": trip_filters["trip_type"],
        "budget": trip_filters["budget"],
        "difficulty": trip_filters["difficulty"],
    }


def _destination_results_from_trip_rows(
    trip_rows: list[dict[str, object]],
    *,
    sort: str,
) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for row in trip_rows:
        trip = cast(TripData, row["trip"])
        raw_destination = str(trip.get("destination", "") or "").strip()
        destination_name = raw_destination.split(",")[0].strip() if raw_destination else ""
        if not destination_name:
            continue
        group_key = _normalize_token(destination_name)
        if not group_key:
            continue

        group = grouped.setdefault(
            group_key,
            {
                "name": destination_name,
                "hero_image_url": str(trip.get("banner_image_url", "") or "").strip(),
                "trip_count": 0,
                "best_score": 0,
                "score_sum": 0,
                "next_departure_ts": None,
                "next_departure": "",
                "next_departure_label": "",
                "top_trip_types_counter": Counter(),
            },
        )

        trip_score = _coerce_int(row.get("base_score", 0))
        if sort == "best_match":
            trip_score += _coerce_int(row.get("relevance", 0)) * 1_000

        group["trip_count"] = _coerce_int(group.get("trip_count", 0)) + 1
        group["best_score"] = max(_coerce_int(group.get("best_score", 0)), trip_score)
        group["score_sum"] = _coerce_int(group.get("score_sum", 0)) + trip_score
        if not str(group.get("hero_image_url", "") or "").strip():
            group["hero_image_url"] = str(trip.get("banner_image_url", "") or "").strip()

        trip_type_label = str(
            trip.get("trip_type_label")
            or trip.get("trip_type")
            or ""
        ).strip()
        if trip_type_label:
            cast(Counter[str], group["top_trip_types_counter"])[trip_type_label] += 1

        departure_ts = _safe_datetime_timestamp(trip.get("starts_at"))
        existing_departure_ts = group.get("next_departure_ts")
        if departure_ts is not None and (
            existing_departure_ts is None or departure_ts < cast(float, existing_departure_ts)
        ):
            group["next_departure_ts"] = departure_ts
            group["next_departure"] = trip.get("starts_at")
            group["next_departure_label"] = _datetime_label(trip.get("starts_at"))

    destination_rows: list[dict[str, object]] = []
    for group in grouped.values():
        destination_name = str(group.get("name", "") or "").strip()
        canonical_params = {
            "q": destination_name,
            "intent": "trips",
            "destination": destination_name,
            "page": "1",
            "sort": "best_match",
        }
        destination_rows.append(
            {
                "result_kind": "destination",
                "name": destination_name,
                "hero_image_url": str(group.get("hero_image_url", "") or "").strip(),
                "trip_count": _coerce_int(group.get("trip_count", 0)),
                "next_departure": group.get("next_departure", ""),
                "next_departure_label": str(group.get("next_departure_label", "") or "").strip(),
                "top_trip_types": [
                    trip_type
                    for trip_type, _count in cast(Counter[str], group["top_trip_types_counter"]).most_common(3)
                ],
                "target_url": f"/search?{urlencode(canonical_params)}",
                "query_value": destination_name,
                "destination_filter_value": destination_name,
                "best_score": _coerce_int(group.get("best_score", 0)),
                "score_sum": _coerce_int(group.get("score_sum", 0)),
                "next_departure_ts": group.get("next_departure_ts"),
            }
        )

    if sort == "most_trips":
        destination_rows.sort(
            key=lambda row: (
                _coerce_int(row.get("trip_count", 0)),
                _coerce_int(row.get("best_score", 0)),
                str(row.get("name", "") or "").lower(),
            ),
            reverse=True,
        )
    elif sort == "soonest_departure":
        destination_rows.sort(
            key=lambda row: (
                row.get("next_departure_ts") is None,
                row.get("next_departure_ts") or float("inf"),
                -_coerce_int(row.get("score_sum", 0)),
                str(row.get("name", "") or "").lower(),
            ),
        )
    elif sort == "best_match":
        destination_rows.sort(
            key=lambda row: (
                _coerce_int(row.get("best_score", 0)),
                _coerce_int(row.get("trip_count", 0)),
                str(row.get("name", "") or "").lower(),
            ),
            reverse=True,
        )
    else:
        destination_rows.sort(
            key=lambda row: (
                _coerce_int(row.get("score_sum", 0)),
                _coerce_int(row.get("trip_count", 0)),
                str(row.get("name", "") or "").lower(),
            ),
            reverse=True,
        )

    for row in destination_rows:
        row.pop("best_score", None)
        row.pop("score_sum", None)
        row.pop("next_departure_ts", None)

    return destination_rows


def _normalize_story_search_filters(raw_filters: Mapping[str, object] | None) -> dict[str, str]:
    return {
        "location": str((raw_filters or {}).get("location", "") or "").strip(),
        "tag": str((raw_filters or {}).get("tag", "") or "").strip(),
    }


def _blog_matches_search_filters(blog: BlogData, filters: Mapping[str, object]) -> bool:
    location_filter = _normalize_token(filters.get("location", ""))
    if location_filter and location_filter not in _normalize_token(blog.get("location", "")):
        return False

    tag_filter = str(filters.get("tag", "") or "").strip().lower()
    if tag_filter:
        normalized_tags = {
            str(tag or "").strip().lower()
            for tag in cast(list[object], blog.get("tags", []) if isinstance(blog.get("tags", []), list) else [])
            if str(tag or "").strip()
        }
        if tag_filter not in normalized_tags:
            return False

    return True


def _sort_blog_rows(rows: list[dict[str, object]], *, sort: str) -> list[dict[str, object]]:
    sorted_rows = list(rows)
    if sort == "newest":
        sorted_rows.sort(
            key=lambda row: (
                _coerce_int(cast(BlogData, row["blog"]).get("id", 0)),
                _coerce_int(row.get("base_score", 0)),
            ),
            reverse=True,
        )
        return sorted_rows

    if sort == "best_match":
        sorted_rows.sort(
            key=lambda row: (
                _coerce_int(row.get("base_score", 0)) + _coerce_int(row.get("relevance", 0)) * 1_000,
                str(cast(BlogData, row["blog"]).get("title", "") or "").lower(),
            ),
            reverse=True,
        )
        return sorted_rows

    sorted_rows.sort(
        key=lambda row: (
            _coerce_int(cast(BlogData, row["blog"]).get("reads", 0)),
            _coerce_int(row.get("base_score", 0)),
            str(cast(BlogData, row["blog"]).get("title", "") or "").lower(),
        ),
        reverse=True,
    )
    return sorted_rows


def _story_results_from_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    usernames = [
        str(cast(BlogData, row["blog"]).get("author_username", "") or "").strip()
        for row in rows
        if str(cast(BlogData, row["blog"]).get("author_username", "") or "").strip()
    ]
    identity_map = _identity_profile_map(usernames)

    results: list[dict[str, object]] = []
    for row in rows:
        blog = dict(cast(BlogData, row["blog"]))
        author_username = str(blog.get("author_username", "") or "").strip()
        identity = identity_map.get(author_username, {})
        slug = str(blog.get("slug", "") or "").strip()
        if identity:
            blog["author_display_name"] = identity.get("display_name", author_username)
        blog["result_kind"] = "story"
        blog["url"] = f"/stories/{slug}" if slug else str(blog.get("url", "") or "").strip()
        results.append(blog)
    return results


def _normalize_people_search_filters(raw_filters: Mapping[str, object] | None) -> dict[str, object]:
    return {
        "location": str((raw_filters or {}).get("location", "") or "").strip(),
        "travel_tag": str((raw_filters or {}).get("travel_tag", "") or "").strip(),
        "hosted_only": _normalize_flag((raw_filters or {}).get("hosted_only", "")),
    }


def _person_results_from_profile_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    usernames = [
        str(cast(ProfileData, row["profile"]).get("username", "") or "").strip()
        for row in rows
        if str(cast(ProfileData, row["profile"]).get("username", "") or "").strip()
    ]
    identity_map = _identity_profile_map(usernames)

    results: list[dict[str, object]] = []
    for row in rows:
        profile = cast(ProfileData, row["profile"])
        username = str(profile.get("username", "") or "").strip()
        identity = identity_map.get(username, {})
        display_name = str(identity.get("display_name", "") or "").strip() or username
        bio = str(identity.get("bio", "") or "").strip() or str(profile.get("bio", "") or "").strip()
        location = str(identity.get("location", "") or "").strip()
        avatar_url = str(identity.get("avatar_url", "") or "").strip()
        travel_tags = [
            str(item or "").strip()
            for item in cast(list[object], identity.get("travel_tags", []))
            if str(item or "").strip()
        ]
        results.append(
            {
                "result_kind": "person",
                "username": username,
                "display_name": display_name,
                "bio": bio,
                "location": location,
                "avatar_url": avatar_url,
                "travel_tags": travel_tags,
                "followers_count": _coerce_int(profile.get("followers_count", 0)),
                "trips_count": _coerce_int(profile.get("trips_count", 0)),
                "url": f"/u/{username}/",
            }
        )
    return results


def _person_matches_search_filters(person: Mapping[str, object], filters: Mapping[str, object]) -> bool:
    location_filter = _normalize_token(filters.get("location", ""))
    if location_filter and location_filter not in _normalize_token(person.get("location", "")):
        return False

    travel_tag_filter = str(filters.get("travel_tag", "") or "").strip().lower()
    if travel_tag_filter:
        normalized_tags = {
            str(tag or "").strip().lower()
            for tag in cast(list[object], person.get("travel_tags", []))
            if str(tag or "").strip()
        }
        if travel_tag_filter not in normalized_tags:
            return False

    if bool(filters.get("hosted_only", False)) and _coerce_int(person.get("trips_count", 0)) <= 0:
        return False

    return True


def _sort_people_results(results: list[dict[str, object]], *, sort: str, query: str) -> list[dict[str, object]]:
    sorted_results = list(results)
    if sort == "most_hosted_trips":
        sorted_results.sort(
            key=lambda row: (
                _coerce_int(row.get("trips_count", 0)),
                _coerce_int(row.get("followers_count", 0)),
                str(row.get("username", "") or "").lower(),
            ),
            reverse=True,
        )
        return sorted_results

    if sort == "best_match":
        sorted_results.sort(
            key=lambda row: (
                _query_match_score(
                    query,
                    row.get("username"),
                    row.get("display_name"),
                    row.get("bio"),
                    row.get("location"),
                    " ".join(cast(list[str], row.get("travel_tags", []))),
                )
                + _coerce_int(row.get("followers_count", 0)) * 5,
                str(row.get("username", "") or "").lower(),
            ),
            reverse=True,
        )
        return sorted_results

    sorted_results.sort(
        key=lambda row: (
            _coerce_int(row.get("followers_count", 0)),
            _coerce_int(row.get("trips_count", 0)),
            str(row.get("username", "") or "").lower(),
        ),
        reverse=True,
    )
    return sorted_results


def _available_sort_items(intent: SearchIntent) -> list[dict[str, str]]:
    return [
        {"value": value, "label": label}
        for value, label in SEARCH_SORT_OPTIONS[intent]
    ]


def _option_rows_from_counts(counter: Counter[str]) -> list[dict[str, str]]:
    return [
        {"value": value, "label": value}
        for value, _count in sorted(counter.items(), key=lambda item: (-item[1], item[0].lower()))
        if value
    ]


def _trip_available_filters(rows: list[dict[str, object]]) -> dict[str, object]:
    from trips.models import trip_filter_options

    destination_counter: Counter[str] = Counter()
    for row in rows:
        trip = cast(TripData, row["trip"])
        destination = str(trip.get("destination", "") or "").strip()
        if destination:
            destination_counter[destination.split(",")[0].strip()] += 1

    fixed_options = trip_filter_options()
    return {
        "destination": _option_rows_from_counts(destination_counter),
        "duration": [{"value": value, "label": label} for value, label in fixed_options["duration"]],
        "trip_type": [{"value": value, "label": label} for value, label in fixed_options["trip_type"]],
        "budget": [{"value": value, "label": label} for value, label in fixed_options["budget"]],
        "difficulty": [{"value": value, "label": label} for value, label in fixed_options["difficulty"]],
    }


def _destination_available_filters(rows: list[dict[str, object]]) -> dict[str, object]:
    trip_type_counter: Counter[str] = Counter()
    budget_counter: Counter[str] = Counter()
    difficulty_counter: Counter[str] = Counter()

    for row in rows:
        trip = cast(TripData, row["trip"])
        trip_type = str(trip.get("trip_type", "") or "").strip().lower()
        trip_type_label = str(trip.get("trip_type_label", "") or trip.get("trip_type", "") or "").strip()
        if trip_type and trip_type_label:
            trip_type_counter[f"{trip_type}|{trip_type_label}"] += 1

        budget = str(trip.get("budget_tier", "") or "").strip().lower()
        budget_label = str(trip.get("budget_label", "") or trip.get("budget_tier", "") or "").strip()
        if budget and budget_label:
            budget_counter[f"{budget}|{budget_label}"] += 1

        difficulty = str(trip.get("difficulty_level", "") or "").strip().lower()
        difficulty_label = str(trip.get("difficulty_label", "") or trip.get("difficulty_level", "") or "").strip()
        if difficulty and difficulty_label:
            difficulty_counter[f"{difficulty}|{difficulty_label}"] += 1

    def _decode(counter: Counter[str]) -> list[dict[str, str]]:
        rows_out: list[dict[str, str]] = []
        for key, _count in sorted(counter.items(), key=lambda item: (-item[1], item[0].lower())):
            value, label = key.split("|", 1)
            rows_out.append({"value": value, "label": label})
        return rows_out

    return {
        "trip_type": _decode(trip_type_counter),
        "budget": _decode(budget_counter),
        "difficulty": _decode(difficulty_counter),
    }


def _story_available_filters(rows: list[dict[str, object]]) -> dict[str, object]:
    location_counter: Counter[str] = Counter()
    tag_counter: Counter[str] = Counter()

    for row in rows:
        blog = cast(BlogData, row["blog"])
        location = str(blog.get("location", "") or "").strip()
        if location:
            location_counter[location] += 1
        for raw_tag in cast(list[object], blog.get("tags", []) if isinstance(blog.get("tags", []), list) else []):
            tag = str(raw_tag or "").strip()
            if tag:
                tag_counter[tag] += 1

    return {
        "location": _option_rows_from_counts(location_counter),
        "tag": _option_rows_from_counts(tag_counter),
    }


def _people_available_filters(results: list[dict[str, object]]) -> dict[str, object]:
    location_counter: Counter[str] = Counter()
    tag_counter: Counter[str] = Counter()
    for person in results:
        location = str(person.get("location", "") or "").strip()
        if location:
            location_counter[location] += 1
        for raw_tag in cast(list[object], person.get("travel_tags", [])):
            tag = str(raw_tag or "").strip()
            if tag:
                tag_counter[tag] += 1

    return {
        "location": _option_rows_from_counts(location_counter),
        "travel_tag": _option_rows_from_counts(tag_counter),
        "hosted_only": [
            {"value": "false", "label": "All people"},
            {"value": "true", "label": "Hosts only"},
        ],
    }


def _compose_all_results(pools: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    queues = {key: list(value) for key, value in pools.items()}
    priority = [key for key, _quota in SEARCH_ALL_PAGE_COMPOSITION]
    ordered: list[dict[str, object]] = []

    while any(queues[key] for key in priority):
        page_rows: list[dict[str, object]] = []
        for key, quota in SEARCH_ALL_PAGE_COMPOSITION:
            for _index in range(quota):
                if not queues[key]:
                    break
                page_rows.append(queues[key].pop(0))

        remaining_slots = SEARCH_PAGE_SIZE - len(page_rows)
        if remaining_slots > 0:
            for key in priority:
                while remaining_slots > 0 and queues[key]:
                    page_rows.append(queues[key].pop(0))
                    remaining_slots -= 1
                if remaining_slots <= 0:
                    break

        if not page_rows:
            break
        ordered.extend(page_rows)

    return ordered


def _paginate_rows(rows: list[dict[str, object]], *, page: int, page_size: int) -> tuple[list[dict[str, object]], int, int, int]:
    total_results = len(rows)
    if total_results <= 0:
        return [], 1, 0, 0

    max_page = max(1, (total_results + page_size - 1) // page_size)
    effective_page = min(max(1, page), max_page)
    start_index = (effective_page - 1) * page_size
    end_index = min(start_index + page_size, total_results)
    return rows[start_index:end_index], effective_page, start_index + 1, end_index


def _canonical_params_for_search(
    *,
    query: str,
    intent: SearchIntent,
    page: int,
    sort: str,
    applied_filters: Mapping[str, object],
) -> dict[str, str]:
    params: dict[str, str] = {
        "intent": intent,
        "page": str(page),
        "sort": sort,
    }
    if query.strip():
        params["q"] = query.strip()

    for key, raw_value in applied_filters.items():
        if isinstance(raw_value, bool):
            if raw_value:
                params[key] = "true"
            continue

        value = str(raw_value or "").strip()
        if not value or value == "all":
            continue
        params[key] = value

    return params


def build_search_page_payload_for_user(
    user: object,
    *,
    query: str = "",
    intent: str = "",
    raw_tab: str = "",
    page: object = 1,
    page_size: object = SEARCH_PAGE_SIZE,
    sort: str = "",
    raw_filters: Mapping[str, object] | None = None,
) -> SearchPagePayload:
    raw_query = str(query or "").strip()
    destination_filter = str((raw_filters or {}).get("destination", "") or "").strip()
    normalized_query = raw_query or destination_filter
    effective_intent = normalize_search_intent(intent, raw_tab=raw_tab, destination_filter=destination_filter)
    requested_page = _normalize_positive_int(page, default=1)
    effective_page_size = SEARCH_PAGE_SIZE

    base_trip_rows = _sort_trip_rows(
        _trip_rank_rows_for_user(user, normalized_query),
        sort=_default_sort_for_intent("trips", normalized_query),
    )
    base_story_rows = _sort_blog_rows(
        _blog_rank_rows_for_user(user, normalized_query),
        sort=_default_sort_for_intent("stories", normalized_query),
    )
    base_profile_rows = _profile_rank_rows_for_user(user, normalized_query)
    base_people_results = _sort_people_results(
        _person_results_from_profile_rows(base_profile_rows),
        sort=_default_sort_for_intent("people", normalized_query),
        query=normalized_query,
    )
    base_destination_rows = _destination_results_from_trip_rows(
        base_trip_rows,
        sort=_default_sort_for_intent("destinations", normalized_query),
    )

    counts = {
        "trips": len(base_trip_rows),
        "destinations": len(base_destination_rows),
        "stories": len(base_story_rows),
        "people": len(base_people_results),
    }
    counts["all"] = counts["trips"] + counts["destinations"] + counts["stories"] + counts["people"]

    if effective_intent == "all":
        effective_sort = "recommended"
        available_filters: Mapping[str, object] = {}
        applied_filters: Mapping[str, object] = {}
        all_results = _compose_all_results(
            {
                "trips": _trip_results_from_rows(base_trip_rows),
                "destinations": base_destination_rows,
                "stories": _story_results_from_rows(base_story_rows),
                "people": base_people_results,
            }
        )
        paged_results, resolved_page, showing_from, showing_to = _paginate_rows(
            all_results,
            page=requested_page,
            page_size=effective_page_size,
        )
        total_results = len(all_results)
    elif effective_intent == "trips":
        applied_filters = _normalize_trip_search_filters(raw_filters)
        effective_sort = normalize_search_sort(sort, intent=effective_intent, query=normalized_query)
        filtered_trip_rows = [
            row for row in base_trip_rows
            if _trip_matches_search_filters(cast(TripData, row["trip"]), applied_filters)
        ]
        sorted_trip_rows = _sort_trip_rows(filtered_trip_rows, sort=effective_sort)
        available_filters = _trip_available_filters(base_trip_rows)
        trip_results = _trip_results_from_rows(sorted_trip_rows)
        paged_results, resolved_page, showing_from, showing_to = _paginate_rows(
            trip_results,
            page=requested_page,
            page_size=effective_page_size,
        )
        total_results = len(trip_results)
    elif effective_intent == "destinations":
        applied_filters = _normalize_destination_search_filters(raw_filters)
        effective_sort = normalize_search_sort(sort, intent=effective_intent, query=normalized_query)
        filtered_trip_rows = [
            row for row in base_trip_rows
            if _trip_matches_search_filters(
                cast(TripData, row["trip"]),
                {
                    "destination": "",
                    "duration": "all",
                    "trip_type": str(applied_filters.get("trip_type", "all") or "all"),
                    "budget": str(applied_filters.get("budget", "all") or "all"),
                    "difficulty": str(applied_filters.get("difficulty", "all") or "all"),
                },
            )
        ]
        destination_results = _destination_results_from_trip_rows(filtered_trip_rows, sort=effective_sort)
        available_filters = _destination_available_filters(base_trip_rows)
        paged_results, resolved_page, showing_from, showing_to = _paginate_rows(
            destination_results,
            page=requested_page,
            page_size=effective_page_size,
        )
        total_results = len(destination_results)
    elif effective_intent == "stories":
        applied_filters = _normalize_story_search_filters(raw_filters)
        effective_sort = normalize_search_sort(sort, intent=effective_intent, query=normalized_query)
        filtered_story_rows = [
            row for row in base_story_rows
            if _blog_matches_search_filters(cast(BlogData, row["blog"]), applied_filters)
        ]
        sorted_story_rows = _sort_blog_rows(filtered_story_rows, sort=effective_sort)
        available_filters = _story_available_filters(base_story_rows)
        story_results = _story_results_from_rows(sorted_story_rows)
        paged_results, resolved_page, showing_from, showing_to = _paginate_rows(
            story_results,
            page=requested_page,
            page_size=effective_page_size,
        )
        total_results = len(story_results)
    else:
        applied_filters = _normalize_people_search_filters(raw_filters)
        effective_sort = normalize_search_sort(sort, intent=effective_intent, query=normalized_query)
        filtered_people = [
            person for person in base_people_results
            if _person_matches_search_filters(person, applied_filters)
        ]
        sorted_people = _sort_people_results(filtered_people, sort=effective_sort, query=normalized_query)
        available_filters = _people_available_filters(base_people_results)
        paged_results, resolved_page, showing_from, showing_to = _paginate_rows(
            sorted_people,
            page=requested_page,
            page_size=effective_page_size,
        )
        total_results = len(sorted_people)

    canonical_params = _canonical_params_for_search(
        query=normalized_query,
        intent=effective_intent,
        page=resolved_page,
        sort=effective_sort,
        applied_filters=applied_filters,
    )
    meta: dict[str, object] = {
        "legacy_tab": str(raw_tab or "").strip(),
        "legacy_tab_mapped": bool(str(raw_tab or "").strip() and not str(intent or "").strip()),
        "legacy_destination_query_mapped": bool(destination_filter and not raw_query),
        "default_sort": _default_sort_for_intent(effective_intent, normalized_query),
        "default_sort_applied": effective_sort == _default_sort_for_intent(effective_intent, normalized_query) and str(sort or "").strip().lower() != effective_sort,
        "requested_page": requested_page,
        "resolved_page": resolved_page,
        "canonical_params": canonical_params,
        "canonical_url": f"/search?{urlencode(canonical_params)}",
        "all_composition": {key: value for key, value in SEARCH_ALL_PAGE_COMPOSITION} if effective_intent == "all" else {},
    }

    return {
        "query": normalized_query,
        "intent": effective_intent,
        "page": resolved_page,
        "page_size": effective_page_size,
        "total_results": total_results,
        "showing_from": showing_from,
        "showing_to": showing_to,
        "counts": counts,
        "available_sorts": _available_sort_items(effective_intent),
        "applied_filters": applied_filters,
        "available_filters": available_filters,
        "results": paged_results,
        "meta": meta,
    }
