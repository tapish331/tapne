from __future__ import annotations

from typing import Final, Literal
from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from trips.models import Trip

from .models import (
    EnrollmentRequest,
    apply_enrollment_decision,
    build_hosting_inbox_payload_for_member,
    normalize_hosting_inbox_filter,
    submit_join_request,
)

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
        print(f"[enrollment][verbose] {message}", flush=True)


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
def trip_request_view(request: HttpRequest, trip_id: int) -> HttpResponse:
    fallback_next = reverse("trips:detail", kwargs={"trip_id": trip_id})
    next_url = _safe_next_url(request, fallback=fallback_next)

    trip = Trip.objects.select_related("host").filter(pk=trip_id).first()
    if trip is None:
        message_text = "Could not submit join request. Trip was not found."
        _vprint(request, f"Join request failed because trip id={trip_id} was not found")
        return _build_action_response(
            request,
            next_url=next_url,
            level="error",
            message_text=message_text,
            status_code=404,
            payload={
                "action": "trip-request",
                "trip_id": trip_id,
                "outcome": "trip-not-found",
                "request_id": None,
            },
        )

    if not bool(getattr(trip, "is_published", False)):
        message_text = "Could not submit join request because this trip is not published."
        _vprint(
            request,
            (
                "Join request blocked for trip id={trip_id}; trip is unpublished".format(
                    trip_id=trip_id,
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
                "action": "trip-request",
                "trip_id": trip_id,
                "outcome": "trip-unpublished",
                "request_id": None,
            },
        )

    request_row, outcome = submit_join_request(
        member=request.user,
        trip=trip,
        message=request.POST.get("message", ""),
    )

    if outcome == "created-pending":
        level: FeedbackLevel = "success"
        message_text = "Join request sent to the host."
    elif outcome == "already-pending":
        level = "info"
        message_text = "You already have a pending join request for this trip."
    elif outcome == "already-approved":
        level = "success"
        message_text = "You are already approved for this trip."
    elif outcome == "reopened-pending":
        level = "success"
        message_text = "Join request re-submitted to the host."
    elif outcome == "host-self-request-blocked":
        level = "info"
        message_text = "Hosts cannot submit join requests to their own trips."
    else:
        level = "error"
        message_text = "Could not submit join request. Please try again."

    _vprint(
        request,
        (
            "Join request outcome={outcome}; trip_id={trip_id}; requester=@{requester}; request_id={request_id}"
            .format(
                outcome=outcome,
                trip_id=trip_id,
                requester=request.user.username,
                request_id=(request_row.pk if request_row is not None else "n/a"),
            )
        ),
    )
    return _build_action_response(
        request,
        next_url=next_url,
        level=level,
        message_text=message_text,
        payload={
            "action": "trip-request",
            "trip_id": trip_id,
            "outcome": outcome,
            "request_id": request_row.pk if request_row is not None else None,
            "is_pending": outcome in {"created-pending", "already-pending", "reopened-pending"},
            "is_approved": outcome == "already-approved",
        },
    )


@login_required(login_url="accounts:login")
@require_http_methods(["GET"])
def hosting_inbox_view(request: HttpRequest) -> HttpResponse:
    requested_status = request.GET.get("status", EnrollmentRequest.STATUS_PENDING)
    active_status = normalize_hosting_inbox_filter(requested_status)

    if str(requested_status or "").strip().lower() != active_status:
        _vprint(
            request,
            (
                "Unsupported hosting status filter '{requested}' requested. Falling back to '{active}'.".format(
                    requested=requested_status,
                    active=active_status,
                )
            ),
        )

    payload = build_hosting_inbox_payload_for_member(
        request.user,
        status=active_status,
    )
    _vprint(
        request,
        (
            "Hosting inbox rendered for @{username}; active_status={status}; counts={counts}; rows={rows}".format(
                username=request.user.username,
                status=payload["active_status"],
                counts=payload["counts"],
                rows=len(payload["requests"]),
            )
        ),
    )

    context: dict[str, object] = {
        "hosting_requests": payload["requests"],
        "hosting_counts": payload["counts"],
        "hosting_inbox_mode": payload["mode"],
        "hosting_inbox_reason": payload["reason"],
        "active_status": payload["active_status"],
    }
    return render(request, "pages/enrollment/hosting_inbox.html", context)


def _review_request_action(
    request: HttpRequest,
    *,
    request_id: int,
    decision: str,
) -> HttpResponse:
    next_url = _safe_next_url(request, fallback=reverse("enrollment:hosting-inbox"))
    enrollment_request = get_object_or_404(
        EnrollmentRequest.objects.select_related("trip", "requester", "trip__host"),
        pk=request_id,
        trip__host=request.user,
    )

    outcome = apply_enrollment_decision(
        request_row=enrollment_request,
        host=request.user,
        decision=decision,
    )

    trip_title = str(getattr(enrollment_request.trip, "title", "") or "").strip()
    requester_username = str(getattr(enrollment_request.requester, "username", "") or "").strip()
    if outcome == "approved":
        messages.success(
            request,
            f"Approved @{requester_username} for {trip_title}.",
        )
    elif outcome == "denied":
        messages.success(
            request,
            f"Denied @{requester_username} for {trip_title}.",
        )
    elif outcome == "already-approved":
        messages.info(request, f"@{requester_username} is already approved for this trip.")
    elif outcome == "already-denied":
        messages.info(request, f"@{requester_username} is already denied for this trip.")
    else:
        messages.error(request, "Could not review this request.")

    _vprint(
        request,
        (
            "Review action decision={decision}; outcome={outcome}; request_id={request_id}; host=@{host}"
            .format(
                decision=decision,
                outcome=outcome,
                request_id=request_id,
                host=request.user.username,
            )
        ),
    )
    return redirect(next_url)


@login_required(login_url="accounts:login")
@require_POST
def approve_request_view(request: HttpRequest, request_id: int) -> HttpResponse:
    return _review_request_action(request, request_id=request_id, decision="approve")


@login_required(login_url="accounts:login")
@require_POST
def deny_request_view(request: HttpRequest, request_id: int) -> HttpResponse:
    return _review_request_action(request, request_id=request_id, decision="deny")
