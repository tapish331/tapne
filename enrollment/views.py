from __future__ import annotations

from typing import Final
from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
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


@login_required(login_url="accounts:login")
@require_POST
def trip_request_view(request: HttpRequest, trip_id: int) -> HttpResponse:
    fallback_next = reverse("trips:detail", kwargs={"trip_id": trip_id})
    next_url = _safe_next_url(request, fallback=fallback_next)

    trip = Trip.objects.select_related("host").filter(pk=trip_id).first()
    if trip is None:
        messages.error(request, "Could not submit join request. Trip was not found.")
        _vprint(request, f"Join request failed because trip id={trip_id} was not found")
        return redirect(next_url)

    if not bool(getattr(trip, "is_published", False)):
        messages.error(request, "Could not submit join request because this trip is not published.")
        _vprint(
            request,
            (
                "Join request blocked for trip id={trip_id}; trip is unpublished".format(
                    trip_id=trip_id,
                )
            ),
        )
        return redirect(next_url)

    request_row, outcome = submit_join_request(
        member=request.user,
        trip=trip,
        message=request.POST.get("message", ""),
    )

    if outcome == "created-pending":
        messages.success(request, "Join request sent to the host.")
    elif outcome == "already-pending":
        messages.info(request, "You already have a pending join request for this trip.")
    elif outcome == "already-approved":
        messages.success(request, "You are already approved for this trip.")
    elif outcome == "reopened-pending":
        messages.success(request, "Join request re-submitted to the host.")
    elif outcome == "host-self-request-blocked":
        messages.info(request, "Hosts cannot submit join requests to their own trips.")
    else:
        messages.error(request, "Could not submit join request. Please try again.")

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
    return redirect(next_url)


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
