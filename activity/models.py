from __future__ import annotations

from datetime import datetime
from typing import Any, Final, Literal, TypedDict, cast

from django.apps import apps
from django.db.models import Q

from enrollment.models import EnrollmentRequest
from interactions.models import Comment
from reviews.models import Review
from social.models import Bookmark, FollowRelation

ActivityFilter = Literal[
    "all",
    "follows",
    "enrollment",
    "comments",
    "replies",
    "bookmarks",
    "reviews",
]
ALLOWED_ACTIVITY_FILTERS: Final[set[str]] = {
    "all",
    "follows",
    "enrollment",
    "comments",
    "replies",
    "bookmarks",
    "reviews",
}


class ActivityItemData(TypedDict):
    id: str
    group: str
    actor_username: str
    actor_url: str
    action: str
    target_label: str
    target_url: str
    occurred_at: datetime
    preview: str


class ActivityPayload(TypedDict):
    items: list[ActivityItemData]
    counts: dict[str, int]
    mode: str
    reason: str
    active_filter: ActivityFilter


def normalize_activity_filter(raw_activity_filter: object) -> ActivityFilter:
    normalized = str(raw_activity_filter or "").strip().lower()
    if normalized in ALLOWED_ACTIVITY_FILTERS:
        return cast(ActivityFilter, normalized)
    return "all"


def _resolve_model(app_label: str, model_name: str) -> type[Any] | None:
    try:
        return cast(type[Any], apps.get_model(app_label, model_name))
    except LookupError:
        return None


def _owned_trip_keys_for_member(member_id: int) -> set[str]:
    if member_id <= 0:
        return set()

    trip_model = _resolve_model("trips", "Trip")
    if trip_model is None:
        return set()

    owned_trip_keys: set[str] = set()
    for value in trip_model.objects.filter(host_id=member_id).values_list("pk", flat=True):
        try:
            trip_id = int(value or 0)
        except (TypeError, ValueError):
            continue
        if trip_id > 0:
            owned_trip_keys.add(str(trip_id))
    return owned_trip_keys


def _owned_blog_keys_for_member(member_id: int) -> set[str]:
    if member_id <= 0:
        return set()

    blog_model = _resolve_model("blogs", "Blog")
    if blog_model is None:
        return set()

    owned_blog_keys: set[str] = set()
    for value in blog_model.objects.filter(author_id=member_id).values_list("slug", flat=True):
        slug = str(value or "").strip().lower()
        if slug:
            owned_blog_keys.add(slug)
    return owned_blog_keys


def _owned_content_target_filter(*, owned_trip_keys: set[str], owned_blog_keys: set[str]) -> Q:
    # Start with an always-false predicate, then OR target groups in.
    target_filter = Q(pk__in=[])
    if owned_trip_keys:
        target_filter |= Q(target_type="trip", target_key__in=sorted(owned_trip_keys))
    if owned_blog_keys:
        target_filter |= Q(target_type="blog", target_key__in=sorted(owned_blog_keys))
    return target_filter


def _fallback_target_label(*, target_type: str, target_key: str, member_username: str) -> str:
    if target_type == "user":
        return f"@{member_username}"
    if target_type == "trip":
        if target_key.isdigit():
            return f"Trip #{target_key}"
        return "Trip"
    if target_type == "blog":
        pretty_slug = target_key.replace("-", " ").strip()
        return pretty_slug.title() if pretty_slug else "Blog"
    return "Target"


def _fallback_target_url(*, target_type: str, target_key: str, member_username: str) -> str:
    if target_type == "user":
        return f"/u/{member_username}/"
    if target_type == "trip" and target_key.isdigit():
        return f"/trips/{target_key}/"
    if target_type == "blog" and target_key:
        return f"/blogs/{target_key}/"
    return "/activity/"


def _url_with_anchor(url: str, *, anchor: str) -> str:
    normalized = str(url or "").strip()
    if not normalized:
        return "#"
    if "#" in normalized:
        return normalized

    anchor_name = str(anchor or "").strip().lstrip("#")
    if not anchor_name:
        return normalized
    return f"{normalized}#{anchor_name}"


def _truncate_preview(value: object, *, limit: int = 180) -> str:
    preview = " ".join(str(value or "").strip().split())
    if len(preview) <= limit:
        return preview
    return f"{preview[: max(1, limit - 3)].rstrip()}..."


def _build_follow_events_for_member(
    *,
    member_id: int,
    member_username: str,
    limit: int,
) -> list[ActivityItemData]:
    rows = list(
        FollowRelation.objects.select_related("follower")
        .filter(following_id=member_id)
        .order_by("-created_at", "-pk")[:limit]
    )

    events: list[ActivityItemData] = []
    for row in rows:
        actor_username = str(getattr(getattr(row, "follower", None), "username", "") or "").strip()
        if not actor_username:
            continue

        events.append(
            {
                "id": f"follow:{int(row.pk or 0)}",
                "group": "follows",
                "actor_username": actor_username,
                "actor_url": f"/u/{actor_username}/",
                "action": "started following you",
                "target_label": f"@{member_username}",
                "target_url": f"/u/{member_username}/",
                "occurred_at": row.created_at,
                "preview": "",
            }
        )
    return events


def _build_enrollment_events_for_member(
    *,
    member_id: int,
    member_username: str,
    limit: int,
) -> list[ActivityItemData]:
    rows = list(
        EnrollmentRequest.objects.select_related("trip", "trip__host", "reviewed_by")
        .filter(
            requester_id=member_id,
            status__in=[EnrollmentRequest.STATUS_APPROVED, EnrollmentRequest.STATUS_DENIED],
            reviewed_at__isnull=False,
        )
        .order_by("-reviewed_at", "-pk")[:limit]
    )

    events: list[ActivityItemData] = []
    for row in rows:
        actor_username = str(getattr(getattr(row, "reviewed_by", None), "username", "") or "").strip()
        if not actor_username:
            actor_username = str(
                getattr(getattr(getattr(row, "trip", None), "host", None), "username", "") or ""
            ).strip()
        if not actor_username:
            actor_username = member_username

        trip_id = int(getattr(row, "trip_id", 0) or 0)
        trip_title = str(getattr(getattr(row, "trip", None), "title", "") or "").strip()
        if not trip_title:
            trip_title = f"Trip #{trip_id}" if trip_id > 0 else "Trip"

        trip_url = f"/trips/{trip_id}/" if trip_id > 0 else "/trips/"
        get_absolute_url = getattr(getattr(row, "trip", None), "get_absolute_url", None)
        if callable(get_absolute_url):
            try:
                maybe_url = get_absolute_url()
                if isinstance(maybe_url, str) and maybe_url.strip():
                    trip_url = maybe_url
            except Exception:
                pass

        status = str(row.status or "").strip().lower()
        action = "approved your join request for" if status == EnrollmentRequest.STATUS_APPROVED else "denied your join request for"
        occurred_at = row.reviewed_at if row.reviewed_at is not None else row.updated_at

        events.append(
            {
                "id": f"enrollment:{int(row.pk or 0)}:{status}",
                "group": "enrollment",
                "actor_username": actor_username,
                "actor_url": f"/u/{actor_username}/",
                "action": action,
                "target_label": trip_title,
                "target_url": trip_url,
                "occurred_at": occurred_at,
                "preview": _truncate_preview(row.message),
            }
        )
    return events


def _build_comment_events_for_member(
    *,
    member_id: int,
    member_username: str,
    owned_content_filter: Q,
    limit: int,
) -> list[ActivityItemData]:
    rows = list(
        Comment.objects.select_related("author")
        .filter(parent__isnull=True)
        .exclude(author_id=member_id)
        .filter(owned_content_filter)
        .order_by("-created_at", "-pk")[:limit]
    )

    events: list[ActivityItemData] = []
    for row in rows:
        actor_username = str(getattr(getattr(row, "author", None), "username", "") or "").strip()
        if not actor_username:
            continue

        target_type = str(row.target_type or "").strip().lower()
        target_key = str(row.target_key or "").strip().lower()
        target_label = str(row.target_label or "").strip() or _fallback_target_label(
            target_type=target_type,
            target_key=target_key,
            member_username=member_username,
        )
        target_url = str(row.target_url or "").strip() or _fallback_target_url(
            target_type=target_type,
            target_key=target_key,
            member_username=member_username,
        )
        action = "commented on your trip" if target_type == "trip" else "commented on your blog"

        events.append(
            {
                "id": f"comment:{int(row.pk or 0)}",
                "group": "comments",
                "actor_username": actor_username,
                "actor_url": f"/u/{actor_username}/",
                "action": action,
                "target_label": target_label,
                "target_url": _url_with_anchor(target_url, anchor="comments"),
                "occurred_at": row.created_at,
                "preview": _truncate_preview(row.text),
            }
        )
    return events


def _build_reply_events_for_member(
    *,
    member_id: int,
    member_username: str,
    limit: int,
) -> list[ActivityItemData]:
    rows = list(
        Comment.objects.select_related("author", "parent")
        .filter(parent__author_id=member_id)
        .exclude(author_id=member_id)
        .order_by("-created_at", "-pk")[:limit]
    )

    events: list[ActivityItemData] = []
    for row in rows:
        actor_username = str(getattr(getattr(row, "author", None), "username", "") or "").strip()
        if not actor_username:
            continue

        target_type = str(row.target_type or "").strip().lower()
        target_key = str(row.target_key or "").strip().lower()
        target_label = str(row.target_label or "").strip() or _fallback_target_label(
            target_type=target_type,
            target_key=target_key,
            member_username=member_username,
        )
        target_url = str(row.target_url or "").strip() or _fallback_target_url(
            target_type=target_type,
            target_key=target_key,
            member_username=member_username,
        )
        action = (
            "replied to your comment on your trip"
            if target_type == "trip"
            else "replied to your comment on your blog"
        )

        events.append(
            {
                "id": f"reply:{int(row.pk or 0)}",
                "group": "replies",
                "actor_username": actor_username,
                "actor_url": f"/u/{actor_username}/",
                "action": action,
                "target_label": target_label,
                "target_url": _url_with_anchor(target_url, anchor="comments"),
                "occurred_at": row.created_at,
                "preview": _truncate_preview(row.text),
            }
        )
    return events


def _build_bookmark_events_for_member(
    *,
    member_id: int,
    member_username: str,
    member_username_lower: str,
    owned_content_filter: Q,
    limit: int,
) -> list[ActivityItemData]:
    rows = list(
        Bookmark.objects.select_related("member")
        .exclude(member_id=member_id)
        .filter(
            Q(target_type=Bookmark.TARGET_USER, target_key=member_username_lower)
            | owned_content_filter
        )
        .order_by("-created_at", "-pk")[:limit]
    )

    events: list[ActivityItemData] = []
    for row in rows:
        actor_username = str(getattr(getattr(row, "member", None), "username", "") or "").strip()
        if not actor_username:
            continue

        target_type = str(row.target_type or "").strip().lower()
        target_key = str(row.target_key or "").strip().lower()
        target_label = str(row.target_label or "").strip() or _fallback_target_label(
            target_type=target_type,
            target_key=target_key,
            member_username=member_username,
        )
        target_url = str(row.target_url or "").strip() or _fallback_target_url(
            target_type=target_type,
            target_key=target_key,
            member_username=member_username,
        )

        if target_type == Bookmark.TARGET_USER:
            action = "bookmarked your profile"
        elif target_type == Bookmark.TARGET_TRIP:
            action = "bookmarked your trip"
        else:
            action = "bookmarked your blog"

        events.append(
            {
                "id": f"bookmark:{int(row.pk or 0)}",
                "group": "bookmarks",
                "actor_username": actor_username,
                "actor_url": f"/u/{actor_username}/",
                "action": action,
                "target_label": target_label,
                "target_url": target_url,
                "occurred_at": row.created_at,
                "preview": "",
            }
        )
    return events


def _build_review_events_for_member(
    *,
    member_id: int,
    member_username: str,
    owned_content_filter: Q,
    limit: int,
) -> list[ActivityItemData]:
    rows = list(
        Review.objects.select_related("author")
        .exclude(author_id=member_id)
        .filter(owned_content_filter)
        .order_by("-updated_at", "-pk")[:limit]
    )

    events: list[ActivityItemData] = []
    for row in rows:
        actor_username = str(getattr(getattr(row, "author", None), "username", "") or "").strip()
        if not actor_username:
            continue

        target_type = str(row.target_type or "").strip().lower()
        target_key = str(row.target_key or "").strip().lower()
        target_label = str(row.target_label or "").strip() or _fallback_target_label(
            target_type=target_type,
            target_key=target_key,
            member_username=member_username,
        )
        target_url = str(row.target_url or "").strip() or _fallback_target_url(
            target_type=target_type,
            target_key=target_key,
            member_username=member_username,
        )
        action = "reviewed your trip" if target_type == "trip" else "reviewed your blog"
        preview = f"{int(row.rating or 0)}/5"
        if str(row.headline or "").strip():
            preview = f"{preview} - {_truncate_preview(row.headline, limit=110)}"
        elif str(row.body or "").strip():
            preview = f"{preview} - {_truncate_preview(row.body, limit=110)}"

        events.append(
            {
                "id": f"review:{int(row.pk or 0)}",
                "group": "reviews",
                "actor_username": actor_username,
                "actor_url": f"/u/{actor_username}/",
                "action": action,
                "target_label": target_label,
                "target_url": _url_with_anchor(target_url, anchor="reviews"),
                "occurred_at": row.updated_at,
                "preview": preview,
            }
        )
    return events


def _build_activity_counts_for_member(
    *,
    member_id: int,
    member_username_lower: str,
    owned_content_filter: Q,
) -> dict[str, int]:
    counts = {
        "all": 0,
        "follows": FollowRelation.objects.filter(following_id=member_id).count(),
        "enrollment": EnrollmentRequest.objects.filter(
            requester_id=member_id,
            status__in=[EnrollmentRequest.STATUS_APPROVED, EnrollmentRequest.STATUS_DENIED],
            reviewed_at__isnull=False,
        ).count(),
        "comments": Comment.objects.filter(parent__isnull=True)
        .exclude(author_id=member_id)
        .filter(owned_content_filter)
        .count(),
        "replies": Comment.objects.filter(parent__author_id=member_id)
        .exclude(author_id=member_id)
        .count(),
        "bookmarks": Bookmark.objects.exclude(member_id=member_id)
        .filter(
            Q(target_type=Bookmark.TARGET_USER, target_key=member_username_lower)
            | owned_content_filter
        )
        .count(),
        "reviews": Review.objects.exclude(author_id=member_id).filter(owned_content_filter).count(),
    }
    counts["all"] = sum(
        counts[key]
        for key in ("follows", "enrollment", "comments", "replies", "bookmarks", "reviews")
    )
    return counts


def build_activity_payload_for_member(
    member: object,
    *,
    activity_filter: object = "all",
    limit: int = 80,
) -> ActivityPayload:
    normalized_filter = normalize_activity_filter(activity_filter)
    if not bool(getattr(member, "is_authenticated", False)):
        return {
            "items": [],
            "counts": {
                "all": 0,
                "follows": 0,
                "enrollment": 0,
                "comments": 0,
                "replies": 0,
                "bookmarks": 0,
                "reviews": 0,
            },
            "mode": "guest-not-allowed",
            "reason": "Activity is available for members only.",
            "active_filter": normalized_filter,
        }

    member_id = int(getattr(member, "pk", 0) or 0)
    if member_id <= 0:
        return {
            "items": [],
            "counts": {
                "all": 0,
                "follows": 0,
                "enrollment": 0,
                "comments": 0,
                "replies": 0,
                "bookmarks": 0,
                "reviews": 0,
            },
            "mode": "member-activity",
            "reason": "No activity records are available for this account.",
            "active_filter": normalized_filter,
        }

    try:
        parsed_limit = int(limit)
    except (TypeError, ValueError):
        parsed_limit = 80

    effective_limit = max(5, min(parsed_limit, 250))
    stream_limit = max(40, effective_limit * 2)

    member_username = str(getattr(member, "username", "") or "").strip() or "member"
    member_username_lower = member_username.lower()
    owned_trip_keys = _owned_trip_keys_for_member(member_id)
    owned_blog_keys = _owned_blog_keys_for_member(member_id)
    owned_content_filter = _owned_content_target_filter(
        owned_trip_keys=owned_trip_keys,
        owned_blog_keys=owned_blog_keys,
    )

    counts = _build_activity_counts_for_member(
        member_id=member_id,
        member_username_lower=member_username_lower,
        owned_content_filter=owned_content_filter,
    )

    events: list[ActivityItemData] = []
    if normalized_filter in {"all", "follows"}:
        events.extend(
            _build_follow_events_for_member(
                member_id=member_id,
                member_username=member_username,
                limit=stream_limit,
            )
        )
    if normalized_filter in {"all", "enrollment"}:
        events.extend(
            _build_enrollment_events_for_member(
                member_id=member_id,
                member_username=member_username,
                limit=stream_limit,
            )
        )
    if normalized_filter in {"all", "comments"}:
        events.extend(
            _build_comment_events_for_member(
                member_id=member_id,
                member_username=member_username,
                owned_content_filter=owned_content_filter,
                limit=stream_limit,
            )
        )
    if normalized_filter in {"all", "replies"}:
        events.extend(
            _build_reply_events_for_member(
                member_id=member_id,
                member_username=member_username,
                limit=stream_limit,
            )
        )
    if normalized_filter in {"all", "bookmarks"}:
        events.extend(
            _build_bookmark_events_for_member(
                member_id=member_id,
                member_username=member_username,
                member_username_lower=member_username_lower,
                owned_content_filter=owned_content_filter,
                limit=stream_limit,
            )
        )
    if normalized_filter in {"all", "reviews"}:
        events.extend(
            _build_review_events_for_member(
                member_id=member_id,
                member_username=member_username,
                owned_content_filter=owned_content_filter,
                limit=stream_limit,
            )
        )

    events.sort(key=lambda item: (item["occurred_at"], item["id"]), reverse=True)
    events = events[:effective_limit]

    if counts["all"] == 0:
        reason = (
            "No activity yet. New follows, enrollment decisions, comments, bookmarks, and reviews "
            "will appear here."
        )
    elif normalized_filter == "all":
        reason = "Unified member activity stream ordered by newest updates first."
    else:
        filter_labels = {
            "follows": "follower",
            "enrollment": "enrollment",
            "comments": "comment",
            "replies": "reply",
            "bookmarks": "bookmark",
            "reviews": "review",
        }
        label = filter_labels.get(normalized_filter, normalized_filter)
        reason = f"Showing {label} activity only, ordered newest first."
        if not events:
            reason = f"No {label} activity yet."

    return {
        "items": events,
        "counts": counts,
        "mode": "member-activity",
        "reason": reason,
        "active_filter": normalized_filter,
    }
