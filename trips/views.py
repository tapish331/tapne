from __future__ import annotations

import mimetypes
from typing import Final

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpRequest, HttpResponse, HttpResponseNotFound, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods

from runtime.models import RuntimeRateLimitDecision, check_rate_limit
from tapne.storage_urls import resolve_file_url, should_use_fallback_file_url

from .models import Trip
from .places_proxy import PlacesProxyError, autocomplete_places, place_details

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


def _trip_destination_identifier(request: HttpRequest) -> str:
    user_id = int(getattr(request.user, "pk", 0) or 0)
    forwarded_for = str(request.META.get("HTTP_X_FORWARDED_FOR", "") or "").strip()
    if forwarded_for:
        source_ip = forwarded_for.split(",")[0].strip()
    else:
        source_ip = str(request.META.get("REMOTE_ADDR", "") or "").strip()
    if not source_ip:
        source_ip = "unknown-ip"
    return f"user:{user_id}|ip:{source_ip}"


def _trip_destination_rate_limit_window_seconds() -> int:
    raw = getattr(settings, "TAPNE_TRIP_DESTINATION_RATE_LIMIT_WINDOW_SECONDS", 60)
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        parsed = 60
    return max(1, parsed)


def _trip_destination_rate_limit(
    request: HttpRequest,
    *,
    scope: str,
    limit_setting_name: str,
    fallback_limit: int,
) -> RuntimeRateLimitDecision:
    raw_limit = getattr(settings, limit_setting_name, fallback_limit)
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = fallback_limit
    limit = max(1, limit)
    decision = check_rate_limit(
        scope=scope,
        identifier=_trip_destination_identifier(request),
        limit=limit,
        window_seconds=_trip_destination_rate_limit_window_seconds(),
    )
    return decision


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


@login_required(login_url="/")
@require_GET
def trip_destination_autocomplete_view(request: HttpRequest) -> JsonResponse:
    decision = _trip_destination_rate_limit(
        request,
        scope="trips-destination-autocomplete",
        limit_setting_name="TAPNE_TRIP_DESTINATION_AUTOCOMPLETE_RATE_LIMIT_REQUESTS",
        fallback_limit=90,
    )
    if not decision["allowed"]:
        retry_after = decision["retry_after_seconds"]
        response = JsonResponse(
            {
                "error": "rate-limited",
                "message": "Too many destination suggestion requests. Please retry shortly.",
                "retry_after_seconds": retry_after,
            },
            status=429,
        )
        response["Retry-After"] = str(retry_after)
        return response

    query = str(request.GET.get("q", "") or "").strip()
    session_token = str(request.GET.get("session_token", "") or "").strip()
    if len(query) < 2:
        return JsonResponse(
            {
                "predictions": [],
                "query": query,
                "remaining": decision["remaining"],
            }
        )

    try:
        predictions = autocomplete_places(query, session_token=session_token)
    except PlacesProxyError as exc:
        return JsonResponse(
            {
                "error": exc.code,
                "message": "Destination suggestions are unavailable right now. Try again shortly.",
            },
            status=exc.status_code,
        )

    return JsonResponse(
        {
            "predictions": predictions,
            "query": query,
            "remaining": decision["remaining"],
        }
    )


@login_required(login_url="/")
@require_GET
def trip_destination_details_view(request: HttpRequest) -> JsonResponse:
    decision = _trip_destination_rate_limit(
        request,
        scope="trips-destination-details",
        limit_setting_name="TAPNE_TRIP_DESTINATION_DETAILS_RATE_LIMIT_REQUESTS",
        fallback_limit=45,
    )
    if not decision["allowed"]:
        retry_after = decision["retry_after_seconds"]
        response = JsonResponse(
            {
                "error": "rate-limited",
                "message": "Too many destination detail requests. Please retry shortly.",
                "retry_after_seconds": retry_after,
            },
            status=429,
        )
        response["Retry-After"] = str(retry_after)
        return response

    place_id = str(request.GET.get("place_id", "") or "").strip()
    if not place_id:
        return JsonResponse(
            {
                "error": "missing-place-id",
                "message": "Query parameter 'place_id' is required.",
            },
            status=400,
        )

    session_token = str(request.GET.get("session_token", "") or "").strip()
    try:
        details = place_details(place_id, session_token=session_token)
    except PlacesProxyError as exc:
        return JsonResponse(
            {
                "error": exc.code,
                "message": "Destination details are unavailable right now. Try again shortly.",
            },
            status=exc.status_code,
        )

    return JsonResponse(
        {
            "place": details,
            "remaining": decision["remaining"],
        }
    )
