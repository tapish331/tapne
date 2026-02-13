from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Final, Literal, TypedDict, cast

from django.apps import apps
from django.contrib.auth import get_user_model

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

SearchResultType = Literal["all", "trips", "users", "blogs"]
ALLOWED_SEARCH_RESULT_TYPES: Final[set[str]] = {"all", "trips", "users", "blogs"}


class SearchPayload(TypedDict):
    trips: list[TripData]
    profiles: list[ProfileData]
    blogs: list[BlogData]
    mode: str
    reason: str
    query: str
    result_type: SearchResultType


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
    except MemberFeedPreference.DoesNotExist:
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
    Keep defaults stable (demo-only) unless query is present.

    For query-time search, merge live trip rows when trip models are available.
    """

    demo_trips = get_demo_trips()
    normalized_query = query.strip()
    if not normalized_query:
        return demo_trips

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
    Keep default profile behavior demo-only unless a query is provided.

    When `q` exists, merge in live account rows so real users appear in
    `type=users` and `type=all` results.
    """

    demo_profiles = get_demo_profiles()
    normalized_query = query.strip()
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
    if not normalized_query:
        return []

    live_profiles: list[ProfileData] = []
    users = UserModel.objects.select_related("account_profile").all().order_by("username")
    for user in users:
        username = str(getattr(user, "username", "")).strip()
        if not username:
            continue

        profile = getattr(user, "account_profile", None)
        display_name = str(getattr(profile, "display_name", "") or "").strip()
        bio = str(getattr(profile, "bio", "") or "").strip()
        location = str(getattr(profile, "location", "") or "").strip()
        website = str(getattr(profile, "website", "") or "").strip()
        email = str(getattr(user, "email", "") or "").strip()

        if (
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

        live_profiles.append(
            {
                "id": int(getattr(user, "pk", 0)),
                "username": username,
                "bio": bio,
                "followers_count": 0,
                "trips_count": 0,
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
    if not normalized_query:
        return []

    trip_model = _resolve_model("trips", "Trip")
    if trip_model is None:
        return []

    live_trips: list[TripData] = []
    queryset = trip_model.objects.all().order_by("-pk")
    for trip in queryset:
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

        if (
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
    Keep defaults stable (demo-only) unless query is present.

    For query-time search, merge live blog rows when blog models are available.
    """

    demo_blogs = get_demo_blogs()
    normalized_query = query.strip()
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
    if not normalized_query:
        return []

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

        blog_id = int(getattr(blog, "pk", 0))
        if blog_id <= 0:
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

        if (
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
