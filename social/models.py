from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal, TypedDict, cast

from django.apps import apps
from django.conf import settings
from django.db import models
from django.db.models.constraints import BaseConstraint
from django.db.models import F, Q

from feed.models import BlogData, MemberFeedPreference, ProfileData, TripData

BookmarkTargetType = Literal["trip", "user", "blog"]
ALLOWED_BOOKMARK_TARGET_TYPES: Final[set[str]] = {"trip", "user", "blog"}


class FollowStats(TypedDict):
    followers: int
    following: int


class BookmarksPayload(TypedDict):
    trips: list[TripData]
    profiles: list[ProfileData]
    blogs: list[BlogData]
    counts: dict[str, int]
    mode: str
    reason: str


@dataclass(frozen=True)
class BookmarkTargetResolution:
    target_type: BookmarkTargetType
    target_key: str
    target_label: str
    target_url: str


class FollowRelation(models.Model):
    """
    Directed member-to-member follow edge used by social interactions.

    Keeping this model explicit (instead of generic relation tables) makes it
    easier to enforce uniqueness, prevent self-follow, and keep profile/follower
    counts fast with indexed queries.
    """

    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="following_relationships",
    )
    following = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="follower_relationships",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints: list[BaseConstraint] = [
            cast(
                BaseConstraint,
                models.UniqueConstraint(
                    fields=("follower", "following"),
                    name="social_unique_follow",
                ),
            ),
            cast(
                BaseConstraint,
                models.CheckConstraint(
                    condition=~Q(follower=F("following")),
                    name="social_no_self_follow",
                ),
            ),
        ]
        indexes = [
            models.Index(fields=("follower", "created_at"), name="social_follow_out_idx"),
            models.Index(fields=("following", "created_at"), name="social_follow_in_idx"),
        ]

    def __str__(self) -> str:
        follower_username = str(getattr(self.follower, "username", "") or "").strip()
        following_username = str(getattr(self.following, "username", "") or "").strip()
        return f"@{follower_username} -> @{following_username}"


class Bookmark(models.Model):
    """
    Member bookmark record for trips/users/blogs.

    `target_key` stores a canonical identifier by type:
    - trip: trip primary key as string
    - user: username lowercase
    - blog: blog slug lowercase

    Snapshot fields (`target_label`/`target_url`) preserve readable history even
    if target rows are removed later.
    """

    TARGET_TRIP: Final[str] = "trip"
    TARGET_USER: Final[str] = "user"
    TARGET_BLOG: Final[str] = "blog"
    TARGET_TYPE_CHOICES: Final[tuple[tuple[str, str], ...]] = (
        (TARGET_TRIP, "Trip"),
        (TARGET_USER, "User"),
        (TARGET_BLOG, "Blog"),
    )

    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="social_bookmarks",
    )
    target_type = models.CharField(max_length=12, choices=TARGET_TYPE_CHOICES)
    target_key = models.CharField(max_length=191)
    target_label = models.CharField(max_length=255, blank=True)
    target_url = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("member", "target_type", "target_key"),
                name="social_unique_bookmark",
            )
        ]
        indexes = [
            models.Index(
                fields=("member", "target_type", "created_at"),
                name="social_bookmark_mt_idx",
            ),
            models.Index(fields=("target_type", "target_key"), name="social_bookmark_lookup_idx"),
        ]

    def __str__(self) -> str:
        member_username = str(getattr(self.member, "username", "") or "").strip()
        return f"Bookmark({self.target_type}:{self.target_key}) by @{member_username}"


def _resolve_model(app_label: str, model_name: str) -> type[Any] | None:
    try:
        return cast(type[Any], apps.get_model(app_label, model_name))
    except LookupError:
        return None


def _absolute_url(instance: object, *, fallback: str) -> str:
    get_absolute_url = getattr(instance, "get_absolute_url", None)
    if callable(get_absolute_url):
        try:
            maybe_url = get_absolute_url()
            if isinstance(maybe_url, str) and maybe_url.strip():
                return maybe_url
        except Exception:
            return fallback
    return fallback


def _normalize_username(value: object) -> str:
    username = str(value or "").strip().lstrip("@")
    if not username:
        return ""
    return username.lower()


def _trip_model() -> type[Any] | None:
    return _resolve_model("trips", "Trip")


def _blog_model() -> type[Any] | None:
    return _resolve_model("blogs", "Blog")


def _trip_from_key(target_key: str) -> Any | None:
    if not target_key.isdigit():
        return None

    trip_model = _trip_model()
    if trip_model is None:
        return None

    return trip_model.objects.select_related("host").filter(pk=int(target_key)).first()


def _blog_from_key(target_key: str) -> Any | None:
    blog_model = _blog_model()
    if blog_model is None:
        return None

    if target_key.isdigit():
        by_pk = blog_model.objects.select_related("author").filter(pk=int(target_key)).first()
        if by_pk is not None:
            return by_pk

    return blog_model.objects.select_related("author").filter(slug__iexact=target_key).first()


def _user_from_key(target_key: str) -> Any | None:
    try:
        user_model = apps.get_model(settings.AUTH_USER_MODEL)
    except LookupError:
        return None

    if target_key.isdigit():
        by_pk = user_model.objects.filter(pk=int(target_key)).first()
        if by_pk is not None:
            return by_pk

    return user_model.objects.filter(username__iexact=target_key.lstrip("@")).first()


def normalize_bookmark_target_type(raw_target_type: object) -> BookmarkTargetType | None:
    normalized = str(raw_target_type or "").strip().lower()
    if normalized in ALLOWED_BOOKMARK_TARGET_TYPES:
        return cast(BookmarkTargetType, normalized)
    return None


def normalize_bookmark_target_key(target_type: str, raw_target_id: object) -> str | None:
    normalized_type = normalize_bookmark_target_type(target_type)
    if normalized_type is None:
        return None

    raw_key = str(raw_target_id or "").strip()
    if not raw_key:
        return None

    if normalized_type == "trip":
        if not raw_key.isdigit():
            return None
        trip_id = int(raw_key)
        if trip_id <= 0:
            return None
        return str(trip_id)

    if normalized_type == "user":
        normalized_username = _normalize_username(raw_key)
        return normalized_username or None

    if normalized_type == "blog":
        return raw_key.lower()

    return None


def resolve_bookmark_target(
    target_type: str,
    raw_target_id: object,
) -> BookmarkTargetResolution | None:
    normalized_type = normalize_bookmark_target_type(target_type)
    if normalized_type is None:
        return None

    normalized_key = normalize_bookmark_target_key(normalized_type, raw_target_id)
    if normalized_key is None:
        return None

    if normalized_type == "trip":
        trip = _trip_from_key(normalized_key)
        if trip is None:
            return None

        trip_id = int(getattr(trip, "pk", 0) or 0)
        if trip_id <= 0:
            return None

        trip_title = str(getattr(trip, "title", "") or "").strip() or f"Trip #{trip_id}"
        return BookmarkTargetResolution(
            target_type="trip",
            target_key=str(trip_id),
            target_label=trip_title,
            target_url=_absolute_url(trip, fallback=f"/trips/{trip_id}/"),
        )

    if normalized_type == "user":
        user = _user_from_key(normalized_key)
        if user is None:
            return None

        username = str(getattr(user, "username", "") or "").strip()
        if not username:
            return None

        return BookmarkTargetResolution(
            target_type="user",
            target_key=username.lower(),
            target_label=f"@{username}",
            target_url=f"/u/{username}/",
        )

    if normalized_type == "blog":
        blog = _blog_from_key(normalized_key)
        if blog is None:
            return None

        slug = str(getattr(blog, "slug", "") or "").strip()
        if not slug:
            return None

        title = str(getattr(blog, "title", "") or "").strip() or slug.replace("-", " ").title()
        return BookmarkTargetResolution(
            target_type="blog",
            target_key=slug.lower(),
            target_label=title,
            target_url=_absolute_url(blog, fallback=f"/blogs/{slug}/"),
        )

    return None


def canonicalize_bookmark_key_for_delete(
    target_type: str,
    raw_target_id: object,
) -> str | None:
    normalized_type = normalize_bookmark_target_type(target_type)
    if normalized_type is None:
        return None

    resolved = resolve_bookmark_target(normalized_type, raw_target_id)
    if resolved is not None:
        return resolved.target_key

    return normalize_bookmark_target_key(normalized_type, raw_target_id)


def sync_member_follow_usernames(member: object) -> list[str]:
    """
    Mirror social follow edges into feed personalization state.

    Feed ranking currently reads `MemberFeedPreference.followed_usernames`.
    Keeping this in sync ensures follow/unfollow actions immediately affect home
    and search personalization behavior.
    """

    if not bool(getattr(member, "is_authenticated", False)):
        return []

    member_id = int(getattr(member, "pk", 0) or 0)
    if member_id <= 0:
        return []

    followed_rows = FollowRelation.objects.filter(follower_id=member_id).values_list(
        "following__username",
        flat=True,
    )
    normalized_usernames = sorted(
        {
            normalized_username
            for username in followed_rows
            if (normalized_username := _normalize_username(username))
        }
    )

    preference, _ = MemberFeedPreference.objects.get_or_create(user=member)
    if preference.followed_usernames != normalized_usernames:
        preference.followed_usernames = normalized_usernames
        preference.save()

    return normalized_usernames


def is_following_user(*, follower: object, target_user: object) -> bool:
    follower_id = int(getattr(follower, "pk", 0) or 0)
    target_user_id = int(getattr(target_user, "pk", 0) or 0)
    if follower_id <= 0 or target_user_id <= 0:
        return False
    return FollowRelation.objects.filter(
        follower_id=follower_id,
        following_id=target_user_id,
    ).exists()


def build_follow_stats_for_user(user: object) -> FollowStats:
    user_id = int(getattr(user, "pk", 0) or 0)
    if user_id <= 0:
        return {"followers": 0, "following": 0}

    return {
        "followers": FollowRelation.objects.filter(following_id=user_id).count(),
        "following": FollowRelation.objects.filter(follower_id=user_id).count(),
    }


def _profile_data_from_user_row(user_row: Any) -> ProfileData:
    username = str(getattr(user_row, "username", "") or "").strip()
    user_id = int(getattr(user_row, "pk", 0) or 0)

    account_profile = getattr(user_row, "account_profile", None)
    bio = str(getattr(account_profile, "bio", "") or "").strip()
    if not bio:
        bio = "No bio has been added yet."

    trip_model = _trip_model()
    trips_count = 0
    if trip_model is not None and user_id > 0:
        trips_count = int(
            trip_model.objects.filter(host_id=user_id, is_published=True).count()
        )

    followers_count = FollowRelation.objects.filter(following_id=user_id).count()

    return {
        "id": user_id,
        "username": username,
        "bio": bio,
        "followers_count": followers_count,
        "trips_count": trips_count,
        "url": f"/u/{username}/",
    }


def _fallback_trip_data(bookmark: Bookmark) -> TripData:
    trip_id = int(bookmark.target_key) if str(bookmark.target_key).isdigit() else 0
    fallback_title = bookmark.target_label or (
        f"Trip #{trip_id}" if trip_id > 0 else "Unavailable trip"
    )
    fallback_url = bookmark.target_url or (f"/trips/{trip_id}/" if trip_id > 0 else "/trips/")
    return {
        "id": trip_id,
        "title": fallback_title,
        "summary": "This trip bookmark is no longer available in live records.",
        "description": "The saved trip could not be resolved from the current catalog.",
        "destination": "Unavailable",
        "host_username": "",
        "traffic_score": 0,
        "url": fallback_url,
    }


def _fallback_profile_data(bookmark: Bookmark) -> ProfileData:
    username = _normalize_username(bookmark.target_key) or "unknown-user"
    return {
        "id": 0,
        "username": username,
        "bio": "This user bookmark is no longer available in live records.",
        "followers_count": 0,
        "trips_count": 0,
        "url": bookmark.target_url or f"/u/{username}/",
    }


def _fallback_blog_data(bookmark: Bookmark) -> BlogData:
    slug = str(bookmark.target_key or "").strip().lower() or "missing-blog"
    title = bookmark.target_label or slug.replace("-", " ").title() or "Unavailable blog"
    return {
        "id": 0,
        "slug": slug,
        "title": title,
        "excerpt": "This blog bookmark is no longer available in live records.",
        "summary": "This blog bookmark is no longer available in live records.",
        "author_username": "",
        "reads": 0,
        "reviews_count": 0,
        "url": bookmark.target_url or f"/blogs/{slug}/",
        "body": "",
    }


def _trip_data_from_bookmark(bookmark: Bookmark, *, viewer_id: int) -> TripData:
    trip = _trip_from_key(bookmark.target_key)
    if trip is None:
        return _fallback_trip_data(bookmark)

    trip_is_published = bool(getattr(trip, "is_published", True))
    trip_host_id = int(getattr(trip, "host_id", 0) or 0)
    if not trip_is_published and trip_host_id != viewer_id:
        return _fallback_trip_data(bookmark)

    to_trip_data = getattr(trip, "to_trip_data", None)
    if callable(to_trip_data):
        result = to_trip_data()
        if isinstance(result, dict):
            return cast(TripData, result)

    trip_id = int(getattr(trip, "pk", 0) or 0)
    return {
        "id": trip_id,
        "title": str(getattr(trip, "title", "") or "").strip() or f"Trip #{trip_id}",
        "summary": str(getattr(trip, "summary", "") or "").strip(),
        "description": str(getattr(trip, "description", "") or "").strip(),
        "destination": str(getattr(trip, "destination", "") or "").strip(),
        "host_username": str(getattr(getattr(trip, "host", None), "username", "") or "").strip(),
        "traffic_score": int(getattr(trip, "traffic_score", 0) or 0),
        "url": _absolute_url(trip, fallback=f"/trips/{trip_id}/"),
    }


def _profile_data_from_bookmark(bookmark: Bookmark) -> ProfileData:
    user_row = _user_from_key(bookmark.target_key)
    if user_row is None:
        return _fallback_profile_data(bookmark)
    return _profile_data_from_user_row(user_row)


def _blog_data_from_bookmark(bookmark: Bookmark, *, viewer_id: int) -> BlogData:
    blog = _blog_from_key(bookmark.target_key)
    if blog is None:
        return _fallback_blog_data(bookmark)

    blog_is_published = bool(getattr(blog, "is_published", True))
    blog_author_id = int(getattr(blog, "author_id", 0) or 0)
    if not blog_is_published and blog_author_id != viewer_id:
        return _fallback_blog_data(bookmark)

    to_blog_data = getattr(blog, "to_blog_data", None)
    if callable(to_blog_data):
        result = to_blog_data()
        if isinstance(result, dict):
            return cast(BlogData, result)

    blog_id = int(getattr(blog, "pk", 0) or 0)
    slug = str(getattr(blog, "slug", "") or "").strip() or f"blog-{blog_id}"
    return {
        "id": blog_id,
        "slug": slug,
        "title": str(getattr(blog, "title", "") or "").strip() or slug.replace("-", " ").title(),
        "excerpt": str(getattr(blog, "excerpt", "") or "").strip(),
        "summary": str(getattr(blog, "excerpt", "") or "").strip(),
        "author_username": str(getattr(getattr(blog, "author", None), "username", "") or "").strip(),
        "reads": int(getattr(blog, "reads", 0) or 0),
        "reviews_count": int(getattr(blog, "reviews_count", 0) or 0),
        "url": _absolute_url(blog, fallback=f"/blogs/{slug}/"),
        "body": str(getattr(blog, "body", "") or "").strip(),
    }


def build_bookmarks_payload_for_member(
    user: object,
    *,
    limit_per_type: int = 24,
) -> BookmarksPayload:
    effective_limit = max(1, int(limit_per_type or 24))
    if not bool(getattr(user, "is_authenticated", False)):
        return {
            "trips": [],
            "profiles": [],
            "blogs": [],
            "counts": {"trip": 0, "user": 0, "blog": 0},
            "mode": "guest-not-allowed",
            "reason": "Bookmarks are available for members only.",
        }

    viewer_id = int(getattr(user, "pk", 0) or 0)
    if viewer_id <= 0:
        return {
            "trips": [],
            "profiles": [],
            "blogs": [],
            "counts": {"trip": 0, "user": 0, "blog": 0},
            "mode": "member-bookmarks",
            "reason": "No bookmark records are available for this member.",
        }

    bookmark_rows = Bookmark.objects.filter(member_id=viewer_id).order_by("-created_at", "-pk")
    counts = {
        "trip": bookmark_rows.filter(target_type=Bookmark.TARGET_TRIP).count(),
        "user": bookmark_rows.filter(target_type=Bookmark.TARGET_USER).count(),
        "blog": bookmark_rows.filter(target_type=Bookmark.TARGET_BLOG).count(),
    }

    trips: list[TripData] = []
    profiles: list[ProfileData] = []
    blogs: list[BlogData] = []
    for bookmark in bookmark_rows:
        if bookmark.target_type == Bookmark.TARGET_TRIP:
            if len(trips) >= effective_limit:
                continue
            trips.append(_trip_data_from_bookmark(bookmark, viewer_id=viewer_id))
        elif bookmark.target_type == Bookmark.TARGET_USER:
            if len(profiles) >= effective_limit:
                continue
            profiles.append(_profile_data_from_bookmark(bookmark))
        elif bookmark.target_type == Bookmark.TARGET_BLOG:
            if len(blogs) >= effective_limit:
                continue
            blogs.append(_blog_data_from_bookmark(bookmark, viewer_id=viewer_id))

        if (
            len(trips) >= effective_limit
            and len(profiles) >= effective_limit
            and len(blogs) >= effective_limit
        ):
            break

    total_count = int(counts["trip"]) + int(counts["user"]) + int(counts["blog"])
    reason = "Bookmarks ordered by most recent save."
    if total_count == 0:
        reason = "No bookmarks yet. Save trips, users, and blogs to build this page."

    return {
        "trips": trips,
        "profiles": profiles,
        "blogs": blogs,
        "counts": counts,
        "mode": "member-bookmarks",
        "reason": reason,
    }
