from __future__ import annotations

from typing import Final, Literal
from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .models import (
    Bookmark,
    FollowRelation,
    build_bookmarks_payload_for_member,
    build_follow_stats_for_user,
    canonicalize_bookmark_key_for_delete,
    normalize_bookmark_target_type,
    resolve_bookmark_target,
    sync_member_follow_usernames,
)

UserModel = get_user_model()
VERBOSE_FLAGS: Final[set[str]] = {"1", "true", "yes", "on"}
FeedbackLevel = Literal["success", "info", "warning", "error"]


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
        print(f"[social][verbose] {message}", flush=True)


def _safe_next_url(request: HttpRequest, fallback: str) -> str:
    """
    Resolve post-action redirect target while preventing open redirects.
    """

    allowed_hosts = {request.get_host()}
    require_https = request.is_secure()

    requested_next = str(request.POST.get("next") or request.GET.get("next") or "").strip()
    if requested_next and url_has_allowed_host_and_scheme(
        requested_next,
        allowed_hosts=allowed_hosts,
        require_https=require_https,
    ):
        return requested_next

    referer = str(request.headers.get("Referer", "") or "").strip()
    if referer and url_has_allowed_host_and_scheme(
        referer,
        allowed_hosts=allowed_hosts,
        require_https=require_https,
    ):
        split = urlsplit(referer)
        query = f"?{split.query}" if split.query else ""
        fragment = f"#{split.fragment}" if split.fragment else ""
        return f"{split.path or '/'}{query}{fragment}"

    return fallback


def _wants_json_response(request: HttpRequest) -> bool:
    requested_with = str(request.headers.get("X-Requested-With", "") or "").strip().lower()
    accept = str(request.headers.get("Accept", "") or "").strip().lower()
    response_format = str(
        request.POST.get("response_format") or request.GET.get("response_format") or ""
    ).strip().lower()
    return (
        requested_with == "xmlhttprequest"
        or "application/json" in accept
        or response_format == "json"
    )


def _push_feedback_message(request: HttpRequest, *, level: FeedbackLevel, message_text: str) -> None:
    if level == "success":
        messages.success(request, message_text)
    elif level == "warning":
        messages.warning(request, message_text)
    elif level == "error":
        messages.error(request, message_text)
    else:
        messages.info(request, message_text)


def _build_action_response(
    request: HttpRequest,
    *,
    next_url: str,
    level: FeedbackLevel,
    message_text: str,
    status_code: int = 200,
    payload: dict[str, object] | None = None,
) -> HttpResponse:
    if _wants_json_response(request):
        response_payload: dict[str, object] = {
            "ok": level != "error",
            "level": level,
            "message": message_text,
            "next_url": next_url,
        }
        if payload:
            response_payload.update(payload)
        return JsonResponse(response_payload, status=status_code)

    _push_feedback_message(request, level=level, message_text=message_text)
    return redirect(next_url)


@login_required(login_url="accounts:login")
@require_POST
def follow_user_view(request: HttpRequest, username: str) -> HttpResponse:
    lookup_username = username.strip()
    fallback_next = f"/u/{lookup_username}/"
    next_url = _safe_next_url(request, fallback=fallback_next)

    target_user = UserModel.objects.filter(username__iexact=lookup_username).first()
    if target_user is None:
        message_text = f"Could not follow @{lookup_username}. User was not found."
        _vprint(request, f"Follow failed because target user '{lookup_username}' was not found")
        return _build_action_response(
            request,
            next_url=next_url,
            level="error",
            message_text=message_text,
            status_code=404,
            payload={
                "action": "follow",
                "outcome": "target-not-found",
                "target_username": lookup_username,
                "is_following": False,
            },
        )

    if int(getattr(target_user, "pk", 0) or 0) == int(getattr(request.user, "pk", 0) or 0):
        message_text = "You cannot follow your own profile."
        _vprint(request, f"Blocked self-follow attempt for @{lookup_username}")
        return _build_action_response(
            request,
            next_url=next_url,
            level="info",
            message_text=message_text,
            status_code=400,
            payload={
                "action": "follow",
                "outcome": "self-follow-blocked",
                "target_username": lookup_username,
                "is_following": False,
            },
        )

    relation, created = FollowRelation.objects.get_or_create(
        follower=request.user,
        following=target_user,
    )
    sync_member_follow_usernames(request.user)

    if created:
        level: FeedbackLevel = "success"
        message_text = f"You are now following @{target_user.username}."
        outcome = "followed"
    else:
        level = "info"
        message_text = f"You are already following @{target_user.username}."
        outcome = "already-following"

    _vprint(
        request,
        (
            "Follow action completed follower=@{follower} -> following=@{following}; created={created}; relation_id={relation_id}"
            .format(
                follower=request.user.username,
                following=target_user.username,
                created=created,
                relation_id=relation.pk,
            )
        ),
    )
    return _build_action_response(
        request,
        next_url=next_url,
        level=level,
        message_text=message_text,
        payload={
            "action": "follow",
            "outcome": outcome,
            "target_username": target_user.username,
            "is_following": True,
            "next_action": "unfollow",
            "next_action_url": reverse("social:unfollow", kwargs={"username": target_user.username}),
        },
    )


@login_required(login_url="accounts:login")
@require_POST
def unfollow_user_view(request: HttpRequest, username: str) -> HttpResponse:
    lookup_username = username.strip()
    fallback_next = f"/u/{lookup_username}/"
    next_url = _safe_next_url(request, fallback=fallback_next)

    target_user = UserModel.objects.filter(username__iexact=lookup_username).first()
    if target_user is None:
        message_text = f"Could not unfollow @{lookup_username}. User was not found."
        _vprint(request, f"Unfollow failed because target user '{lookup_username}' was not found")
        return _build_action_response(
            request,
            next_url=next_url,
            level="error",
            message_text=message_text,
            status_code=404,
            payload={
                "action": "unfollow",
                "outcome": "target-not-found",
                "target_username": lookup_username,
                "is_following": False,
            },
        )

    deleted_count, _ = FollowRelation.objects.filter(
        follower=request.user,
        following=target_user,
    ).delete()
    sync_member_follow_usernames(request.user)

    if deleted_count:
        level: FeedbackLevel = "success"
        message_text = f"You unfollowed @{target_user.username}."
        outcome = "unfollowed"
    else:
        level = "info"
        message_text = f"You are not currently following @{target_user.username}."
        outcome = "already-not-following"

    _vprint(
        request,
        (
            "Unfollow action follower=@{follower} -> following=@{following}; deleted={deleted_count}"
            .format(
                follower=request.user.username,
                following=target_user.username,
                deleted_count=deleted_count,
            )
        ),
    )
    return _build_action_response(
        request,
        next_url=next_url,
        level=level,
        message_text=message_text,
        payload={
            "action": "unfollow",
            "outcome": outcome,
            "target_username": target_user.username,
            "is_following": False,
            "next_action": "follow",
            "next_action_url": reverse("social:follow", kwargs={"username": target_user.username}),
        },
    )


@login_required(login_url="accounts:login")
@require_POST
def bookmark_view(request: HttpRequest) -> HttpResponse:
    next_url = _safe_next_url(request, fallback=reverse("social:bookmarks"))
    raw_target_type = request.POST.get("type")
    raw_target_id = request.POST.get("id")

    target_type = normalize_bookmark_target_type(raw_target_type)
    if target_type is None:
        message_text = "Unsupported bookmark type. Use trip, user, or blog."
        _vprint(request, f"Bookmark failed due to unsupported type='{raw_target_type}'")
        return _build_action_response(
            request,
            next_url=next_url,
            level="error",
            message_text=message_text,
            status_code=400,
            payload={
                "action": "bookmark",
                "outcome": "invalid-type",
                "target_type": str(raw_target_type or ""),
                "is_bookmarked": False,
            },
        )

    target = resolve_bookmark_target(target_type, raw_target_id)
    if target is None:
        message_text = "Could not bookmark that item because it was not found."
        _vprint(
            request,
            (
                "Bookmark failed for type={target_type} id={target_id}; target resolution returned none"
                .format(
                    target_type=target_type,
                    target_id=str(raw_target_id or ""),
                )
            ),
        )
        return _build_action_response(
            request,
            next_url=next_url,
            level="error",
            message_text=message_text,
            status_code=404,
            payload={
                "action": "bookmark",
                "outcome": "target-not-found",
                "target_type": target_type,
                "target_id": str(raw_target_id or ""),
                "is_bookmarked": False,
            },
        )

    bookmark, created = Bookmark.objects.get_or_create(
        member=request.user,
        target_type=target.target_type,
        target_key=target.target_key,
        defaults={
            "target_label": target.target_label,
            "target_url": target.target_url,
        },
    )

    if not created:
        changed = False
        if bookmark.target_label != target.target_label:
            bookmark.target_label = target.target_label
            changed = True
        if bookmark.target_url != target.target_url:
            bookmark.target_url = target.target_url
            changed = True
        if changed:
            bookmark.save(update_fields=["target_label", "target_url", "updated_at"])

    if created:
        level: FeedbackLevel = "success"
        message_text = "Saved to bookmarks."
        outcome = "bookmarked"
    else:
        level = "info"
        message_text = "That item is already in your bookmarks."
        outcome = "already-bookmarked"

    _vprint(
        request,
        (
            "Bookmark action member=@{member}; type={target_type}; key={target_key}; created={created}"
            .format(
                member=request.user.username,
                target_type=target.target_type,
                target_key=target.target_key,
                created=created,
            )
        ),
    )
    return _build_action_response(
        request,
        next_url=next_url,
        level=level,
        message_text=message_text,
        payload={
            "action": "bookmark",
            "outcome": outcome,
            "target_type": target.target_type,
            "target_key": target.target_key,
            "target_label": target.target_label,
            "target_url": target.target_url,
            "is_bookmarked": True,
            "next_action": "unbookmark",
            "next_action_url": reverse("social:unbookmark"),
        },
    )


@login_required(login_url="accounts:login")
@require_POST
def unbookmark_view(request: HttpRequest) -> HttpResponse:
    next_url = _safe_next_url(request, fallback=reverse("social:bookmarks"))
    raw_target_type = request.POST.get("type")
    raw_target_id = request.POST.get("id")

    target_type = normalize_bookmark_target_type(raw_target_type)
    if target_type is None:
        message_text = "Unsupported bookmark type. Use trip, user, or blog."
        _vprint(request, f"Unbookmark failed due to unsupported type='{raw_target_type}'")
        return _build_action_response(
            request,
            next_url=next_url,
            level="error",
            message_text=message_text,
            status_code=400,
            payload={
                "action": "unbookmark",
                "outcome": "invalid-type",
                "target_type": str(raw_target_type or ""),
                "is_bookmarked": False,
            },
        )

    target_key = canonicalize_bookmark_key_for_delete(target_type, raw_target_id)
    if target_key is None:
        message_text = "Could not remove bookmark. Invalid target identifier."
        _vprint(
            request,
            (
                "Unbookmark failed for type={target_type} id={target_id}; canonical key was invalid"
                .format(
                    target_type=target_type,
                    target_id=str(raw_target_id or ""),
                )
            ),
        )
        return _build_action_response(
            request,
            next_url=next_url,
            level="error",
            message_text=message_text,
            status_code=400,
            payload={
                "action": "unbookmark",
                "outcome": "invalid-target-key",
                "target_type": target_type,
                "target_id": str(raw_target_id or ""),
                "is_bookmarked": False,
            },
        )

    deleted_count, _ = Bookmark.objects.filter(
        member=request.user,
        target_type=target_type,
        target_key=target_key,
    ).delete()

    if deleted_count:
        level: FeedbackLevel = "success"
        message_text = "Removed from bookmarks."
        outcome = "removed"
    else:
        level = "info"
        message_text = "That bookmark was already removed."
        outcome = "already-removed"

    _vprint(
        request,
        (
            "Unbookmark action member=@{member}; type={target_type}; key={target_key}; deleted={deleted_count}"
            .format(
                member=request.user.username,
                target_type=target_type,
                target_key=target_key,
                deleted_count=deleted_count,
            )
        ),
    )
    return _build_action_response(
        request,
        next_url=next_url,
        level=level,
        message_text=message_text,
        payload={
            "action": "unbookmark",
            "outcome": outcome,
            "target_type": target_type,
            "target_key": target_key,
            "is_bookmarked": False,
            "next_action": "bookmark",
            "next_action_url": reverse("social:bookmark"),
        },
    )


@login_required(login_url="accounts:login")
@require_http_methods(["GET"])
def bookmarks_view(request: HttpRequest) -> HttpResponse:
    payload = build_bookmarks_payload_for_member(request.user)
    follow_stats = build_follow_stats_for_user(request.user)
    _vprint(
        request,
        (
            "Rendering bookmarks for @{username}; counts={counts}; follow_stats={follow_stats}"
            .format(
                username=request.user.username,
                counts=payload["counts"],
                follow_stats=follow_stats,
            )
        ),
    )

    context: dict[str, object] = {
        "bookmarked_trips": payload["trips"],
        "bookmarked_profiles": payload["profiles"],
        "bookmarked_blogs": payload["blogs"],
        "bookmark_counts": payload["counts"],
        "bookmark_mode": payload["mode"],
        "bookmark_reason": payload["reason"],
        "follow_stats": follow_stats,
    }
    return render(request, "pages/social/bookmarks.html", context)
