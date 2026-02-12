from __future__ import annotations

from typing import Final
from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .models import (
    Comment,
    DirectMessageThread,
    build_dm_inbox_payload_for_member,
    build_dm_thread_payload_for_member,
    get_or_create_dm_thread_for_members,
    send_dm_message,
    submit_comment,
    submit_reply,
)

UserModel = get_user_model()
VERBOSE_FLAGS: Final[set[str]] = {"1", "true", "yes", "on"}


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
        print(f"[interactions][verbose] {message}", flush=True)


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


@login_required(login_url="accounts:login")
@require_POST
def comment_view(request: HttpRequest) -> HttpResponse:
    next_url = _safe_next_url(request, fallback=reverse("home"))

    comment_row, outcome, resolved_target = submit_comment(
        member=request.user,
        target_type=request.POST.get("target_type"),
        target_id=request.POST.get("target_id"),
        text=request.POST.get("text", ""),
    )

    if outcome == "created":
        messages.success(request, "Comment posted.")
    elif outcome == "invalid-target-type":
        messages.error(request, "Unsupported comment target type. Use trip or blog.")
    elif outcome == "target-not-found":
        messages.error(request, "Could not post comment because that target was not found.")
    elif outcome == "too-long":
        messages.error(request, f"Comment is too long. Max length is {Comment.TEXT_MAX_LENGTH} characters.")
    elif outcome == "empty-text":
        messages.info(request, "Comment text cannot be empty.")
    else:
        messages.error(request, "Could not post comment. Please try again.")

    _vprint(
        request,
        (
            "Comment outcome={outcome}; member=@{member}; target={target}; comment_id={comment_id}".format(
                outcome=outcome,
                member=request.user.username,
                target=(
                    f"{resolved_target.target_type}:{resolved_target.target_key}"
                    if resolved_target is not None
                    else "n/a"
                ),
                comment_id=(comment_row.pk if comment_row is not None else "n/a"),
            )
        ),
    )
    return redirect(next_url)


@login_required(login_url="accounts:login")
@require_POST
def reply_view(request: HttpRequest) -> HttpResponse:
    next_url = _safe_next_url(request, fallback=reverse("home"))
    raw_comment_id = request.POST.get("comment_id")

    reply_row, outcome, parent = submit_reply(
        member=request.user,
        comment_id=raw_comment_id,
        text=request.POST.get("text", ""),
    )

    if outcome == "created":
        messages.success(request, "Reply posted.")
    elif outcome == "parent-not-found":
        messages.error(request, "Could not post reply because the parent comment was not found.")
    elif outcome == "parent-not-top-level":
        messages.error(request, "Replies can only be added to top-level comments.")
    elif outcome == "too-long":
        messages.error(request, f"Reply is too long. Max length is {Comment.TEXT_MAX_LENGTH} characters.")
    elif outcome == "empty-text":
        messages.info(request, "Reply text cannot be empty.")
    else:
        messages.error(request, "Could not post reply. Please try again.")

    _vprint(
        request,
        (
            "Reply outcome={outcome}; member=@{member}; parent_id={parent_id}; reply_id={reply_id}".format(
                outcome=outcome,
                member=request.user.username,
                parent_id=(parent.pk if parent is not None else str(raw_comment_id or "n/a")),
                reply_id=(reply_row.pk if reply_row is not None else "n/a"),
            )
        ),
    )
    return redirect(next_url)


@login_required(login_url="accounts:login")
@require_POST
def dm_open_view(request: HttpRequest) -> HttpResponse:
    fallback_next = reverse("interactions:dm-inbox")
    next_url = _safe_next_url(request, fallback=fallback_next)
    open_with_username = str(request.POST.get("with") or request.GET.get("with") or "").strip().lstrip("@")
    if not open_with_username:
        messages.info(request, "Enter a username to open a direct message thread.")
        return redirect(next_url)

    target_member = UserModel.objects.filter(username__iexact=open_with_username).first()
    if target_member is None:
        messages.error(request, f"Could not open chat. User '@{open_with_username}' was not found.")
        _vprint(
            request,
            f"DM open-with failed; user '@{open_with_username}' does not exist.",
        )
        return redirect(next_url)

    if int(target_member.pk) == int(getattr(request.user, "pk", 0) or 0):
        messages.info(request, "You cannot create a direct message thread with yourself.")
        _vprint(request, f"DM open-with blocked self-thread for @{request.user.username}")
        return redirect(next_url)

    thread, created, outcome = get_or_create_dm_thread_for_members(
        member=request.user,
        other_member=target_member,
    )
    if thread is not None:
        if created:
            messages.success(request, f"Started a conversation with @{target_member.username}.")
        return redirect(reverse("interactions:dm-thread", kwargs={"thread_id": thread.pk}))

    messages.error(request, "Could not open direct message thread.")
    _vprint(
        request,
        (
            "DM open-with failed; member=@{member}; target=@{target}; outcome={outcome}".format(
                member=request.user.username,
                target=target_member.username,
                outcome=outcome,
            )
        ),
    )
    return redirect(next_url)


@login_required(login_url="accounts:login")
@require_http_methods(["GET"])
def dm_inbox_view(request: HttpRequest) -> HttpResponse:
    payload = build_dm_inbox_payload_for_member(request.user)
    _vprint(
        request,
        (
            "DM inbox rendered for @{member}; mode={mode}; thread_count={count}".format(
                member=request.user.username,
                mode=payload["mode"],
                count=len(payload["threads"]),
            )
        ),
    )

    context: dict[str, object] = {
        "dm_threads": payload["threads"],
        "dm_mode": payload["mode"],
        "dm_reason": payload["reason"],
    }
    return render(request, "pages/interactions/dm_inbox.html", context)


@login_required(login_url="accounts:login")
@require_http_methods(["GET"])
def dm_thread_view(request: HttpRequest, thread_id: int) -> HttpResponse:
    payload = build_dm_thread_payload_for_member(request.user, thread_id=thread_id)
    if payload["thread"] is None:
        raise Http404("Thread not found.")

    _vprint(
        request,
        (
            "DM thread rendered for @{member}; thread_id={thread_id}; mode={mode}; messages={count}".format(
                member=request.user.username,
                thread_id=thread_id,
                mode=payload["mode"],
                count=len(payload["messages"]),
            )
        ),
    )

    context: dict[str, object] = {
        "dm_thread": payload["thread"],
        "dm_messages": payload["messages"],
        "dm_mode": payload["mode"],
        "dm_reason": payload["reason"],
    }
    return render(request, "pages/interactions/dm_thread.html", context)


@login_required(login_url="accounts:login")
@require_POST
def dm_send_view(request: HttpRequest, thread_id: int) -> HttpResponse:
    next_url = _safe_next_url(
        request,
        fallback=reverse("interactions:dm-thread", kwargs={"thread_id": thread_id}),
    )
    payload = build_dm_thread_payload_for_member(request.user, thread_id=thread_id, limit=1)
    if payload["thread"] is None:
        raise Http404("Thread not found.")

    thread = DirectMessageThread.objects.filter(pk=thread_id).first()
    message_row, outcome = send_dm_message(
        thread=thread,
        sender=request.user,
        body=request.POST.get("text", ""),
    )

    if outcome == "sent":
        messages.success(request, "Message sent.")
    elif outcome == "empty-message":
        messages.info(request, "Message text cannot be empty.")
    elif outcome == "too-long":
        messages.error(request, "Message is too long. Keep it under 4000 characters.")
    else:
        messages.error(request, "Could not send message.")

    _vprint(
        request,
        (
            "DM send outcome={outcome}; member=@{member}; thread_id={thread_id}; message_id={message_id}".format(
                outcome=outcome,
                member=request.user.username,
                thread_id=thread_id,
                message_id=(message_row.pk if message_row is not None else "n/a"),
            )
        ),
    )
    return redirect(next_url)
