from __future__ import annotations

import mimetypes
from datetime import timedelta
from typing import Final

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpRequest, HttpResponse, HttpResponseNotFound
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from tapne.seo import (
    BreadcrumbItem,
    build_absolute_url,
    build_breadcrumb_json_ld,
    build_seo_meta_context,
    combine_json_ld_payloads,
    normalize_meta_description,
)
from tapne.storage_urls import build_trip_banner_fallback_url, resolve_file_url, should_use_fallback_file_url

from interactions.models import build_comment_threads_payload_for_target
from media.models import (
    MediaTargetPayload,
    build_media_attachment_map_for_targets,
    build_media_payload_for_target,
    submit_media_upload,
)
from reviews.models import build_reviews_payload_for_target

from .forms import TripForm
from .models import (
    Trip,
    build_my_trips_payload_for_member,
    build_trip_detail_payload_for_user,
    build_trip_list_payload_for_user,
    has_active_trip_filters,
    normalize_mine_tab,
    normalize_trip_filters,
    trip_filter_options,
)

VERBOSE_FLAGS: Final[set[str]] = {"1", "true", "yes", "on"}
FORM_ACTION_SUBMIT: Final[str] = "submit"
FORM_ACTION_SAVE_DRAFT: Final[str] = "save_draft"
FORM_ACTION_PREVIEW: Final[str] = "preview"
TRIP_FORM_ACTIONS: Final[set[str]] = {
    FORM_ACTION_SUBMIT,
    FORM_ACTION_SAVE_DRAFT,
    FORM_ACTION_PREVIEW,
}


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


def _safe_file_url(file_field: object) -> str:
    return resolve_file_url(file_field)


def _safe_file_url_with_fallback(file_field: object, *, fallback_url: str = "") -> str:
    resolved = _safe_file_url(file_field)
    fallback = str(fallback_url or "").strip()
    if fallback and should_use_fallback_file_url(resolved):
        return fallback
    return resolved


def _safe_file_name(file_field: object) -> str:
    if not file_field:
        return ""
    try:
        return str(getattr(file_field, "name", "") or "").strip()
    except Exception:
        return ""


def _trip_form_action(request: HttpRequest) -> str:
    candidate = str(request.POST.get("form_action", "") or "").strip().lower()
    if candidate in TRIP_FORM_ACTIONS:
        return candidate
    return FORM_ACTION_SUBMIT


@require_http_methods(["GET"])
def trip_banner_view(request: HttpRequest, trip_id: int) -> HttpResponse | FileResponse:
    trip = get_object_or_404(Trip.objects.only("id", "host_id", "is_published", "banner_image"), pk=trip_id)
    viewer_id = int(getattr(request.user, "pk", 0) or 0)
    trip_host_id = int(getattr(trip, "host_id", 0) or 0)
    is_published = bool(getattr(trip, "is_published", False))
    if not is_published and (not request.user.is_authenticated or trip_host_id != viewer_id):
        return HttpResponseNotFound()

    banner_field = trip.banner_image
    banner_name = _safe_file_name(banner_field)
    if not banner_name:
        return HttpResponseNotFound()

    try:
        banner_field.open("rb")
    except Exception:
        return HttpResponseNotFound()

    content_type, _ = mimetypes.guess_type(banner_name)
    response = FileResponse(banner_field.file, content_type=content_type or "application/octet-stream")
    response["Cache-Control"] = "public, max-age=300" if is_published else "private, max-age=60"
    return response


@require_http_methods(["GET"])
def trip_list_view(request: HttpRequest) -> HttpResponse:
    viewer_state = "member" if request.user.is_authenticated else "guest"
    _vprint(request, f"Rendering trip list for viewer_state={viewer_state}")

    raw_filters: dict[str, object] = {
        "destination": request.GET.get("destination", ""),
        "duration": request.GET.get("duration", "all"),
        "trip_type": request.GET.get("trip_type", "all"),
        "budget": request.GET.get("budget", "all"),
        "difficulty": request.GET.get("difficulty", "all"),
    }
    normalized_filters = normalize_trip_filters(raw_filters)
    payload = build_trip_list_payload_for_user(request.user, filters=normalized_filters)
    _vprint(
        request,
        (
            "Trip list mode={mode}; source={source}; reason={reason}; count={count}; filters={filters}".format(
                mode=payload["mode"],
                source=payload["source"],
                reason=payload["reason"],
                count=len(payload["trips"]),
                filters=payload["filters"],
            )
        ),
    )

    context: dict[str, object] = {
        "trips": payload["trips"],
        "trip_mode": payload["mode"],
        "trip_reason": payload["reason"],
        "trip_source": payload["source"],
        "trip_filters": payload["filters"],
        "trip_filter_options": trip_filter_options(),
        "trip_total_count": payload["total_count"],
        "trip_filtered_count": payload["filtered_count"],
        "trip_has_active_filters": has_active_trip_filters(payload["filters"]),
    }

    breadcrumbs: list[BreadcrumbItem] = [{"label": "Home", "url": "/"}, {"label": "Trips"}]
    context["breadcrumbs"] = breadcrumbs
    list_json_ld: dict[str, object] = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Trips",
        "description": "Browse upcoming and hosted trips on tapne.",
        "numberOfItems": len(payload["trips"]),
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": index + 1,
                "name": str(trip.get("title", "") or "Trip"),
                "url": build_absolute_url(request, str(trip.get("url", "") or "/trips/")),
            }
            for index, trip in enumerate(payload["trips"][:12])
        ],
    }
    context.update(
        build_seo_meta_context(
            request,
            title="Trips | tapne",
            description="Browse upcoming and hosted trips on tapne.",
            json_ld_payload=combine_json_ld_payloads(list_json_ld, build_breadcrumb_json_ld(request, breadcrumbs)),
        )
    )
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
            "reason": "No media yet for this preview trip. Hosts can add photos once the trip is published live.",
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

    trip_title = str(payload["trip"].get("title", "") or f"Trip #{trip_id}")
    trip_description = normalize_meta_description(
        payload["trip"].get("summary") or payload["trip"].get("description") or "Trip details on tapne."
    )
    breadcrumbs: list[BreadcrumbItem] = [
        {"label": "Home", "url": "/"},
        {"label": "Trips", "url": "/trips/"},
        {"label": trip_title},
    ]
    context["breadcrumbs"] = breadcrumbs

    trip_json_ld: dict[str, object] = {
        "@context": "https://schema.org",
        "@type": "TouristTrip",
        "name": trip_title,
        "description": trip_description,
        "url": build_absolute_url(request, str(payload["trip"].get("url", "") or f"/trips/{trip_id}/")),
        "touristType": str(payload["trip"].get("trip_type_label", "") or "Travelers"),
        "itinerary": str(payload["trip"].get("destination", "") or ""),
    }
    host_username = str(payload["trip"].get("host_username", "") or "").strip()
    if host_username:
        trip_json_ld["provider"] = {
            "@type": "Person",
            "name": f"@{host_username}",
            "url": build_absolute_url(request, f"/u/{host_username}/"),
        }

    context.update(
        build_seo_meta_context(
            request,
            title=f"{trip_title} | tapne",
            description=trip_description,
            og_type="article",
            json_ld_payload=combine_json_ld_payloads(trip_json_ld, build_breadcrumb_json_ld(request, breadcrumbs)),
        )
    )
    return render(request, "pages/trips/detail.html", context)


@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def trip_create_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form_action = _trip_form_action(request)
        form = TripForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            trip = form.save(commit=False)
            trip.host = request.user
            if form_action in {FORM_ACTION_SAVE_DRAFT, FORM_ACTION_PREVIEW}:
                trip.is_published = False
            trip.save()

            gallery_uploads = request.FILES.getlist("gallery_images")
            gallery_upload_success = 0
            gallery_upload_failed = 0
            for uploaded_file in gallery_uploads:
                _asset, _attachment, outcome, _target = submit_media_upload(
                    member=request.user,
                    target_type="trip",
                    target_id=trip.pk,
                    uploaded_file=uploaded_file,
                    caption="",
                )
                if outcome in {"created", "attached-existing", "already-attached"}:
                    gallery_upload_success += 1
                else:
                    gallery_upload_failed += 1

            if form_action == FORM_ACTION_SAVE_DRAFT:
                messages.success(request, "Draft saved.")
            elif form_action == FORM_ACTION_PREVIEW:
                messages.info(request, "Preview mode: review your trip before publishing.")
            else:
                messages.success(request, "Trip created.")
            if gallery_upload_success > 0:
                messages.success(request, f"Uploaded {gallery_upload_success} gallery image(s).")
            if gallery_upload_failed > 0:
                messages.warning(request, f"{gallery_upload_failed} gallery upload(s) failed validation.")
            if form_action == FORM_ACTION_SAVE_DRAFT:
                _vprint(request, f"Saved trip draft id={trip.pk} for @{request.user.username}")
                return redirect(reverse("trips:edit", kwargs={"trip_id": trip.pk}))
            if form_action == FORM_ACTION_PREVIEW:
                _vprint(request, f"Previewing trip draft id={trip.pk} for @{request.user.username}")
                return redirect(reverse("trips:detail", kwargs={"trip_id": trip.pk}))
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
        suggested_end = suggested_start + timedelta(days=2)
        suggested_booking_close = suggested_start - timedelta(days=3)
        form = TripForm(
            initial={
                "starts_at": suggested_start,
                "ends_at": suggested_end,
                "booking_closes_at": suggested_booking_close,
                "is_published": True,
            },
            user=request.user,
        )
        _vprint(request, f"Rendered trip create form for @{request.user.username}")

    context: dict[str, object] = {
        "form": form,
        "form_mode": "create",
        "page_title": "Create trip",
        "submit_label": "Create trip",
        "form_timezone_label": timezone.get_current_timezone_name(),
        "current_banner_preview_url": _safe_file_url_with_fallback(
            getattr(form.instance, "banner_image", None),
            fallback_url=build_trip_banner_fallback_url(
                trip_id=int(getattr(form.instance, "pk", 0) or 0),
                file_name=_safe_file_name(getattr(form.instance, "banner_image", None)),
                updated_at=getattr(form.instance, "updated_at", None),
            ),
        ),
        "current_banner_name": _safe_file_name(getattr(form.instance, "banner_image", None)),
    }
    return render(request, "pages/trips/form.html", context)


@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def trip_edit_view(request: HttpRequest, trip_id: int) -> HttpResponse:
    trip = get_object_or_404(Trip, pk=trip_id, host=request.user)
    original_is_published = bool(trip.is_published)

    if request.method == "POST":
        form_action = _trip_form_action(request)
        form = TripForm(request.POST, request.FILES, instance=trip, user=request.user)
        if form.is_valid():
            edited_trip = form.save(commit=False)
            if form_action == FORM_ACTION_SAVE_DRAFT:
                edited_trip.is_published = False
            elif form_action == FORM_ACTION_PREVIEW:
                # Preview should not accidentally publish or unpublish an existing trip.
                edited_trip.is_published = original_is_published
            edited_trip.save()

            if form_action == FORM_ACTION_SAVE_DRAFT:
                messages.success(request, "Draft saved.")
                _vprint(request, f"Saved trip draft id={trip.pk} for @{request.user.username}")
                return redirect(reverse("trips:edit", kwargs={"trip_id": trip.pk}))
            if form_action == FORM_ACTION_PREVIEW:
                messages.info(request, "Preview mode: review your trip before publishing.")
                _vprint(request, f"Previewing trip id={trip.pk} for @{request.user.username}")
                return redirect(reverse("trips:detail", kwargs={"trip_id": trip.pk}))

            messages.success(request, "Trip updated.")
            _vprint(request, f"Updated trip id={trip.pk} for @{request.user.username}")
            return redirect(reverse("trips:detail", kwargs={"trip_id": trip.pk}))

        messages.error(request, "Please fix the highlighted fields.")
        _vprint(request, f"Trip edit failed for id={trip_id} due to form validation errors")
    else:
        form = TripForm(instance=trip, user=request.user)
        _vprint(request, f"Rendered trip edit form for id={trip_id} and @{request.user.username}")

    context: dict[str, object] = {
        "form": form,
        "form_mode": "edit",
        "trip": trip,
        "page_title": "Edit trip",
        "submit_label": "Save changes",
        "form_timezone_label": timezone.get_current_timezone_name(),
        "current_banner_preview_url": _safe_file_url_with_fallback(
            getattr(form.instance, "banner_image", None),
            fallback_url=build_trip_banner_fallback_url(
                trip_id=int(getattr(form.instance, "pk", 0) or 0),
                file_name=_safe_file_name(getattr(form.instance, "banner_image", None)),
                updated_at=getattr(form.instance, "updated_at", None),
            ),
        ),
        "current_banner_name": _safe_file_name(getattr(form.instance, "banner_image", None)),
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
