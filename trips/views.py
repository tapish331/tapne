from __future__ import annotations

from datetime import timedelta
from typing import Final

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from interactions.models import build_comment_threads_payload_for_target
from media.models import (
    MediaTargetPayload,
    build_media_attachment_map_for_targets,
    build_media_payload_for_target,
)
from reviews.models import build_reviews_payload_for_target

from .forms import TripForm
from .models import (
    Trip,
    build_my_trips_payload_for_member,
    build_trip_detail_payload_for_user,
    build_trip_list_payload_for_user,
    normalize_mine_tab,
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
        print(f"[trips][verbose] {message}", flush=True)


@require_http_methods(["GET"])
def trip_list_view(request: HttpRequest) -> HttpResponse:
    viewer_state = "member" if request.user.is_authenticated else "guest"
    _vprint(request, f"Rendering trip list for viewer_state={viewer_state}")

    payload = build_trip_list_payload_for_user(request.user)
    _vprint(
        request,
        (
            "Trip list mode={mode}; source={source}; reason={reason}; count={count}".format(
                mode=payload["mode"],
                source=payload["source"],
                reason=payload["reason"],
                count=len(payload["trips"]),
            )
        ),
    )

    context: dict[str, object] = {
        "trips": payload["trips"],
        "trip_mode": payload["mode"],
        "trip_reason": payload["reason"],
        "trip_source": payload["source"],
    }
    return render(request, "pages/trips/list.html", context)


@require_http_methods(["GET"])
def trip_detail_view(request: HttpRequest, trip_id: int) -> HttpResponse:
    payload = build_trip_detail_payload_for_user(request.user, trip_id)
    comments_payload = build_comment_threads_payload_for_target(
        target_type="trip",
        target_id=trip_id,
    )
    reviews_payload = build_reviews_payload_for_target(
        target_type="trip",
        target_id=trip_id,
        viewer=request.user,
    )
    review_items = [dict(item) for item in reviews_payload["reviews"]]
    review_key_map = build_media_attachment_map_for_targets(
        target_type="review",
        target_ids=[item.get("id") for item in review_items],
        viewer=request.user,
        limit_per_target=4,
    )
    for review_item in review_items:
        review_item["media_attachments"] = review_key_map.get(str(review_item.get("id") or ""), [])

    trip_media_payload: MediaTargetPayload
    if payload["source"] == "live-db":
        trip_media_payload = build_media_payload_for_target(
            target_type="trip",
            target_id=trip_id,
            viewer=request.user,
        )
    else:
        trip_media_payload = {
            "attachments": [],
            "mode": "unavailable-target",
            "reason": "Media attachments are available for live trip records only.",
            "target_type": "trip",
            "target_key": str(trip_id),
            "target_label": str(payload["trip"].get("title", f"Trip #{trip_id}")),
            "target_url": str(payload["trip"].get("url", f"/trips/{trip_id}/")),
            "can_upload": False,
        }
    _vprint(
        request,
        (
            "Trip detail id={trip_id}; mode={mode}; source={source}; can_manage={can_manage}".format(
                trip_id=trip_id,
                mode=payload["mode"],
                source=payload["source"],
                can_manage=payload["can_manage_trip"],
            )
        ),
    )
    _vprint(
        request,
        (
            "Trip comments target={target}; mode={mode}; count={count}".format(
                target=f"{comments_payload['target_type']}:{comments_payload['target_key']}",
                mode=comments_payload["mode"],
                count=len(comments_payload["comments"]),
            )
        ),
    )
    _vprint(
        request,
        (
            "Trip reviews target={target}; mode={mode}; count={count}; average={average}".format(
                target=f"{reviews_payload['target_type']}:{reviews_payload['target_key']}",
                mode=reviews_payload["mode"],
                count=reviews_payload["review_count"],
                average=reviews_payload["average_rating"],
            )
        ),
    )
    _vprint(
        request,
        (
            "Trip media target={target}; mode={mode}; count={count}; can_upload={can_upload}".format(
                target=f"{trip_media_payload['target_type']}:{trip_media_payload['target_key']}",
                mode=trip_media_payload["mode"],
                count=len(trip_media_payload["attachments"]),
                can_upload=trip_media_payload["can_upload"],
            )
        ),
    )

    context: dict[str, object] = {
        "trip": payload["trip"],
        "trip_detail_mode": payload["mode"],
        "trip_detail_reason": payload["reason"],
        "trip_detail_source": payload["source"],
        "can_manage_trip": payload["can_manage_trip"],
        "interaction_comments": comments_payload["comments"],
        "interaction_comment_mode": comments_payload["mode"],
        "interaction_comment_reason": comments_payload["reason"],
        "review_items": review_items,
        "review_rating_buckets": reviews_payload["rating_buckets"],
        "review_mode": reviews_payload["mode"],
        "review_reason": reviews_payload["reason"],
        "review_count": reviews_payload["review_count"],
        "review_average_rating": reviews_payload["average_rating"],
        "review_can_review": reviews_payload["can_review"],
        "review_viewer_row": reviews_payload["viewer_review"],
        "trip_media_items": trip_media_payload["attachments"],
        "trip_media_mode": trip_media_payload["mode"],
        "trip_media_reason": trip_media_payload["reason"],
        "trip_media_can_upload": trip_media_payload["can_upload"],
    }
    return render(request, "pages/trips/detail.html", context)


@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def trip_create_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = TripForm(request.POST)
        if form.is_valid():
            trip = form.save(commit=False)
            trip.host = request.user
            trip.save()

            messages.success(request, "Trip created.")
            _vprint(request, f"Created trip id={trip.pk} for @{request.user.username}")
            return redirect(reverse("trips:detail", kwargs={"trip_id": trip.pk}))

        messages.error(request, "Please fix the highlighted fields.")
        _vprint(request, "Trip create failed due to form validation errors")
    else:
        suggested_start = timezone.localtime(timezone.now() + timedelta(days=14)).replace(
            minute=0,
            second=0,
            microsecond=0,
        )
        form = TripForm(initial={"starts_at": suggested_start, "traffic_score": 0, "is_published": True})
        _vprint(request, f"Rendered trip create form for @{request.user.username}")

    context: dict[str, object] = {
        "form": form,
        "form_mode": "create",
        "page_title": "Create trip",
        "submit_label": "Create trip",
    }
    return render(request, "pages/trips/form.html", context)


@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def trip_edit_view(request: HttpRequest, trip_id: int) -> HttpResponse:
    trip = get_object_or_404(Trip, pk=trip_id, host=request.user)

    if request.method == "POST":
        form = TripForm(request.POST, instance=trip)
        if form.is_valid():
            form.save()
            messages.success(request, "Trip updated.")
            _vprint(request, f"Updated trip id={trip.pk} for @{request.user.username}")
            return redirect(reverse("trips:detail", kwargs={"trip_id": trip.pk}))

        messages.error(request, "Please fix the highlighted fields.")
        _vprint(request, f"Trip edit failed for id={trip_id} due to form validation errors")
    else:
        form = TripForm(instance=trip)
        _vprint(request, f"Rendered trip edit form for id={trip_id} and @{request.user.username}")

    context: dict[str, object] = {
        "form": form,
        "form_mode": "edit",
        "trip": trip,
        "page_title": "Edit trip",
        "submit_label": "Save changes",
    }
    return render(request, "pages/trips/form.html", context)


@login_required(login_url="accounts:login")
@require_POST
def trip_delete_view(request: HttpRequest, trip_id: int) -> HttpResponse:
    trip = get_object_or_404(Trip, pk=trip_id, host=request.user)
    trip_title = trip.title
    trip.delete()

    messages.success(request, f"Deleted trip: {trip_title}")
    _vprint(request, f"Deleted trip id={trip_id} for @{request.user.username}")
    return redirect(reverse("trips:mine"))


@login_required(login_url="accounts:login")
@require_http_methods(["GET"])
def trip_mine_view(request: HttpRequest) -> HttpResponse:
    requested_tab = str(request.GET.get("tab", "upcoming"))
    active_tab = normalize_mine_tab(requested_tab)

    if requested_tab.strip().lower() != active_tab:
        _vprint(request, f"Unsupported mine tab '{requested_tab}' requested. Falling back to '{active_tab}'.")

    payload = build_my_trips_payload_for_member(request.user, tab=active_tab)
    _vprint(
        request,
        (
            "Mine view active_tab={tab}; reason={reason}; counts={counts}; rows={rows}".format(
                tab=payload["active_tab"],
                reason=payload["reason"],
                counts=payload["tab_counts"],
                rows=len(payload["trips"]),
            )
        ),
    )

    context: dict[str, object] = {
        "mine_trips": payload["trips"],
        "active_tab": payload["active_tab"],
        "tab_counts": payload["tab_counts"],
        "mine_mode": payload["mode"],
        "mine_reason": payload["reason"],
    }
    return render(request, "pages/trips/mine.html", context)
