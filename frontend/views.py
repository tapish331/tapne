from __future__ import annotations

import json
import mimetypes
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final, cast

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import login, logout
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.timezone import now
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.forms import LoginForm, ProfileEditForm, SignUpForm
from accounts.models import ensure_profile
from accounts.views import profile_trip_sections_for_member
from activity.models import build_activity_payload_for_member
from blogs.models import build_blog_detail_payload_for_user, build_blog_list_payload_for_user
from enrollment.models import (
    EnrollmentRequest,
    apply_enrollment_decision,
    build_hosting_inbox_payload_for_member,
    submit_join_request,
)
from feed.models import build_home_payload_for_user, enrich_trip_preview_fields
from interactions.models import build_dm_inbox_payload_for_member, build_dm_thread_payload_for_member
from settings_app.models import build_settings_payload_for_member
from social.models import build_bookmarks_payload_for_member
from trips.models import Trip, build_my_trips_payload_for_member, build_trip_detail_payload_for_user, build_trip_list_payload_for_user

PUBLIC_CACHE_SECONDS: Final[int] = 3600
IMMUTABLE_CACHE_SECONDS: Final[int] = 31536000
BRAND_TOKENS_MARKER: Final[str] = "frontend-brand/tokens"
BRAND_OVERRIDES_MARKER: Final[str] = "frontend-brand/overrides"
FRONTEND_RUNTIME_INLINE_ATTR: Final[str] = "data-tapne-runtime"
FRONTEND_RUNTIME_INLINE_VALUE: Final[str] = "inline-config"
UserModel = get_user_model()


def _frontend_dist_dir() -> Path:
    configured = getattr(settings, "LOVABLE_FRONTEND_DIST_DIR", settings.BASE_DIR / "artifacts" / "lovable-production-dist")
    return Path(configured)


def _frontend_index_path() -> Path:
    return _frontend_dist_dir() / "index.html"


def _read_frontend_index_html() -> str:
    index_path = _frontend_index_path()
    if not index_path.is_file():
        raise Http404("Lovable frontend build artifact is not available.")
    return index_path.read_text(encoding="utf-8")


def _safe_dist_path(relative_path: str, *, base_dir: Path | None = None) -> Path:
    root = (base_dir or _frontend_dist_dir()).resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise Http404("Frontend artifact path is outside the build directory.")
    if not candidate.is_file():
        raise Http404("Frontend artifact file not found.")
    return candidate


def _static_asset_url(path: str) -> str:
    try:
        return static(path)
    except ValueError:
        static_url = str(getattr(settings, "STATIC_URL", "/static/") or "/static/")
        return f"{static_url.rstrip('/')}/{path.lstrip('/')}"


def _frontend_json_dumps(payload: object) -> str:
    return json.dumps(
        payload,
        separators=(",", ":"),
        ensure_ascii=True,
        cls=DjangoJSONEncoder,
    )


def _file_response(path: Path, *, immutable: bool) -> FileResponse:
    content_type, _ = mimetypes.guess_type(str(path))
    response = FileResponse(path.open("rb"), content_type=content_type or "application/octet-stream")
    cache_seconds = IMMUTABLE_CACHE_SECONDS if immutable else PUBLIC_CACHE_SECONDS
    cache_suffix = ", immutable" if immutable else ""
    response["Cache-Control"] = f"public, max-age={cache_seconds}{cache_suffix}"
    return response


def _json_error(message: str, *, status: int = 400, extra: dict[str, object] | None = None) -> JsonResponse:
    payload: dict[str, object] = {"ok": False, "error": message}
    if extra:
        payload.update(extra)
    return JsonResponse(payload, status=status)


def _form_errors(form: Any) -> dict[str, list[str]]:
    errors: dict[str, list[str]] = {}
    for field_name, items in form.errors.get_json_data().items():
        key = "non_field" if field_name == "__all__" else str(field_name)
        errors[key] = [str(item.get("message", "")).strip() for item in items if str(item.get("message", "")).strip()]
    return errors


def _request_payload(request: HttpRequest) -> dict[str, object]:
    content_type = str(request.headers.get("Content-Type", "") or "").lower()
    if "application/json" in content_type:
        try:
            raw_data = json.loads(request.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        if not isinstance(raw_data, dict):
            return {}
        normalized_payload: dict[str, object] = {}
        for raw_key, raw_value in cast(dict[object, object], raw_data).items():
            if raw_value is None:
                continue
            normalized_payload[str(raw_key)] = raw_value.strip() if isinstance(raw_value, str) else raw_value
        return normalized_payload

    return {
        str(key): str(value).strip()
        for key, value in request.POST.items()
    }


def _live_data_required() -> bool:
    return bool(settings.LOVABLE_FRONTEND_REQUIRE_LIVE_DATA)


def _member_identity_payload(member: object) -> dict[str, str]:
    username = str(getattr(member, "username", "") or "").strip()
    display_name = username or "Tapne member"
    bio = ""
    location = ""
    website = ""

    profile = getattr(member, "account_profile", None)
    member_id = int(getattr(member, "pk", 0) or 0)
    if profile is None and member_id > 0:
        try:
            profile = ensure_profile(member)
        except Exception:
            profile = None

    if profile is not None:
        display_name = str(getattr(profile, "effective_display_name", "") or "").strip() or display_name
        bio = str(getattr(profile, "bio", "") or "").strip()
        location = str(getattr(profile, "location", "") or "").strip()
        website = str(getattr(profile, "website", "") or "").strip()

    if not display_name:
        full_name_getter = getattr(member, "get_full_name", None)
        if callable(full_name_getter):
            display_name = str(full_name_getter() or "").strip() or display_name

    return {
        "username": username,
        "display_name": display_name or "Tapne member",
        "bio": bio,
        "location": location,
        "website": website,
    }


def _identity_map_for_usernames(usernames: list[str]) -> dict[str, dict[str, str]]:
    normalized = sorted({str(username or "").strip() for username in usernames if str(username or "").strip()})
    if not normalized:
        return {}
    queryset = UserModel.objects.select_related("account_profile").filter(username__in=normalized)
    return {
        str(getattr(user, "username", "") or "").strip(): _member_identity_payload(user)
        for user in queryset
    }


def _enrich_trip_cards(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    cards = [dict(row) for row in rows]
    identity_map = _identity_map_for_usernames(
        [str(card.get("host_username", "") or "").strip() for card in cards]
    )
    for card in cards:
        username = str(card.get("host_username", "") or "").strip()
        identity = identity_map.get(username)
        if identity is None:
            continue
        card["host_display_name"] = identity["display_name"]
        card["host_bio"] = identity["bio"]
        card["host_location"] = identity["location"]
        card["host_website"] = identity["website"]
    return cards


def _enrich_blog_cards(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    cards = [dict(row) for row in rows]
    identity_map = _identity_map_for_usernames(
        [str(card.get("author_username", "") or "").strip() for card in cards]
    )
    for card in cards:
        username = str(card.get("author_username", "") or "").strip()
        identity = identity_map.get(username)
        if identity is None:
            continue
        card["author_display_name"] = identity["display_name"]
    return cards


def _enrich_profile_cards(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    cards = [dict(row) for row in rows]
    identity_map = _identity_map_for_usernames(
        [str(card.get("username", "") or "").strip() for card in cards]
    )
    for card in cards:
        username = str(card.get("username", "") or "").strip()
        identity = identity_map.get(username)
        if identity is None:
            continue
        card["display_name"] = identity["display_name"]
        card["bio"] = identity["bio"] or str(card.get("bio", "") or "").strip()
        card["location"] = identity["location"]
        if identity["website"]:
            card["website"] = identity["website"]
    return cards


def _serialize_trip_for_frontend(trip: Trip) -> dict[str, object]:
    row = dict(enrich_trip_preview_fields(trip.to_trip_data()))
    return _enrich_trip_cards([row])[0]


def _normalize_string(value: object) -> str:
    return str(value or "").strip()


def _normalize_string_list(value: object, *, max_items: int = 24, max_length: int = 280) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw_item in cast(list[object], value):
        item = " ".join(str(raw_item or "").strip().split())
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item[:max_length])
        if len(cleaned) >= max_items:
            break
    return cleaned


def _normalize_optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _normalize_optional_decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _normalize_optional_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    parsed = parse_datetime(str(value).strip())
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _apply_trip_payload(trip: Trip, payload: dict[str, object]) -> None:
    trip.title = _normalize_string(payload.get("title", trip.title))
    trip.destination = _normalize_string(payload.get("destination", trip.destination))
    trip.summary = _normalize_string(payload.get("summary", trip.summary))
    trip.description = str(payload.get("description", trip.description) or "").strip()
    trip.trip_type = _normalize_string(payload.get("trip_type", trip.trip_type)).lower()
    trip.cancellation_policy = str(payload.get("cancellation_policy", trip.cancellation_policy) or "").strip()
    trip.code_of_conduct = str(payload.get("code_of_conduct", trip.code_of_conduct) or "").strip()

    starts_at = _normalize_optional_datetime(payload.get("starts_at"))
    ends_at = _normalize_optional_datetime(payload.get("ends_at"))
    booking_closes_at = _normalize_optional_datetime(payload.get("booking_closes_at"))
    if starts_at is not None:
        trip.starts_at = starts_at
    if "ends_at" in payload:
        trip.ends_at = ends_at
    if "booking_closes_at" in payload:
        trip.booking_closes_at = booking_closes_at

    if "total_seats" in payload:
        trip.total_seats = _normalize_optional_int(payload.get("total_seats"))
    if "minimum_seats" in payload:
        trip.minimum_seats = _normalize_optional_int(payload.get("minimum_seats"))
    if "price_per_person" in payload:
        trip.price_per_person = _normalize_optional_decimal(payload.get("price_per_person"))
    if "total_trip_price" in payload:
        trip.total_trip_price = _normalize_optional_decimal(payload.get("total_trip_price"))

    if "highlights" in payload:
        trip.highlights = _normalize_string_list(payload.get("highlights"))
    if "included_items" in payload:
        trip.included_items = _normalize_string_list(payload.get("included_items"))
    if "not_included_items" in payload:
        trip.not_included_items = _normalize_string_list(payload.get("not_included_items"))
    if "things_to_carry" in payload:
        trip.things_to_carry = _normalize_string_list(payload.get("things_to_carry"))
    if "suitable_for" in payload:
        trip.suitable_for = _normalize_string_list(payload.get("suitable_for"), max_items=8, max_length=80)
    if "trip_vibe" in payload:
        trip.trip_vibe = _normalize_string_list(payload.get("trip_vibe"), max_items=8, max_length=80)


def _member_only_error() -> JsonResponse:
    return _json_error("Authentication required.", status=401)


def _session_user_payload(request: HttpRequest) -> dict[str, object] | None:
    user = getattr(request, "user", None)
    if not bool(getattr(user, "is_authenticated", False)):
        return None

    profile = ensure_profile(user)
    created_trips, joined_trips = profile_trip_sections_for_member(user)
    settings_payload = build_settings_payload_for_member(user)

    return {
        "id": int(getattr(user, "pk", 0) or 0),
        "username": str(getattr(user, "username", "") or "").strip(),
        "email": str(getattr(user, "email", "") or "").strip(),
        "first_name": str(getattr(user, "first_name", "") or "").strip(),
        "last_name": str(getattr(user, "last_name", "") or "").strip(),
        "display_name": profile.effective_display_name,
        "bio": str(profile.bio or ""),
        "location": str(profile.location or ""),
        "website": str(profile.website or ""),
        "created_trips": created_trips,
        "joined_trips": joined_trips,
        "settings": settings_payload["settings"],
        "profile_url": "/profile",
        "public_profile_url": f"/u/{getattr(user, 'username', '')}/",
    }


def _runtime_config_payload(request: HttpRequest) -> dict[str, object]:
    request_user = getattr(request, "user", None)
    return {
        "app_name": "tapne",
        "generated_at": now().isoformat(),
        "frontend_mode": "lovable-spa",
        "frontend_enabled": bool(settings.LOVABLE_FRONTEND_ENABLED),
        "live_data_required": bool(settings.LOVABLE_FRONTEND_REQUIRE_LIVE_DATA),
        "build_dir": str(_frontend_dist_dir()),
        "api": {
            "base": "/frontend-api",
            "session": reverse("frontend:api-session"),
            "login": reverse("frontend:api-auth-login"),
            "signup": reverse("frontend:api-auth-signup"),
            "logout": reverse("frontend:api-auth-logout"),
            "home": reverse("frontend:api-home"),
            "trips": reverse("frontend:api-trips-list"),
            "blogs": reverse("frontend:api-blogs-list"),
            "my_trips": reverse("frontend:api-my-trips"),
            "profile_me": reverse("frontend:api-profile-me"),
            "bookmarks": reverse("frontend:api-bookmarks"),
            "activity": reverse("frontend:api-activity"),
            "settings": reverse("frontend:api-settings"),
            "hosting_inbox": reverse("frontend:api-hosting-inbox"),
            "dm_inbox": reverse("frontend:api-dm-inbox"),
        },
        "routes": {
            "home": "/",
            "trips": "/trips",
            "blogs": "/blogs",
            "login": "/login",
            "signup": "/signup",
            "profile": "/profile",
            "create_trip": "/create-trip",
            "my_trips": "/my-trips",
        },
        "auth": {
            "login_form": "/accounts/login/",
            "signup_form": "/accounts/signup/",
            "logout_form": "/accounts/logout/",
        },
        "csrf": {
            "cookie_name": settings.CSRF_COOKIE_NAME,
            "header_name": settings.CSRF_HEADER_NAME,
            "token": get_token(request),
        },
        "session": {
            "authenticated": bool(getattr(request_user, "is_authenticated", False)),
            "user": _session_user_payload(request),
        },
    }


def _frontend_shell_html(request: HttpRequest) -> str:
    html = _read_frontend_index_html()
    tokens_href = _static_asset_url("frontend-brand/tokens.css")
    overrides_href = _static_asset_url("frontend-brand/overrides.css")
    runtime_href = reverse("frontend:runtime-config-js")
    runtime_payload = _frontend_json_dumps(_runtime_config_payload(request))

    head_parts: list[str] = []
    if 'name="tapne-frontend-shell"' not in html:
        head_parts.append('<meta name="tapne-frontend-shell" content="lovable">')
    if BRAND_TOKENS_MARKER not in html:
        head_parts.append(f'<link rel="stylesheet" href="{tokens_href}">')
    if BRAND_OVERRIDES_MARKER not in html:
        head_parts.append(f'<link rel="stylesheet" href="{overrides_href}">')
    if head_parts:
        head_injection = "\n".join(head_parts) + "\n"
        if "</head>" in html:
            html = html.replace("</head>", f"{head_injection}</head>", 1)
        else:
            html = f"{head_injection}{html}"

    runtime_script_pattern = re.compile(
        rf'<script\b[^>]*\bsrc=["\']{re.escape(runtime_href)}["\'][^>]*>\s*</script>\s*',
        re.IGNORECASE,
    )
    inline_runtime_pattern = re.compile(
        rf'<script\b[^>]*{FRONTEND_RUNTIME_INLINE_ATTR}=["\']{FRONTEND_RUNTIME_INLINE_VALUE}["\'][^>]*>.*?</script>\s*',
        re.IGNORECASE | re.DOTALL,
    )
    html = runtime_script_pattern.sub("", html)
    html = inline_runtime_pattern.sub("", html)

    runtime_script_tag = (
        f'<script {FRONTEND_RUNTIME_INLINE_ATTR}="{FRONTEND_RUNTIME_INLINE_VALUE}">'
        f"window.__TAPNE_FRONTEND_CONFIG__ = {runtime_payload};"
        "</script>\n"
    )
    module_script_marker = '<script type="module"'
    if module_script_marker in html:
        html = html.replace(module_script_marker, f"{runtime_script_tag}{module_script_marker}", 1)
    elif "</body>" in html:
        html = html.replace("</body>", f"{runtime_script_tag}</body>", 1)
    else:
        html = f"{html}\n{runtime_script_tag}"

    return html


@ensure_csrf_cookie
@require_GET
def runtime_config_js(request: HttpRequest) -> HttpResponse:
    payload_text = _frontend_json_dumps(_runtime_config_payload(request))
    response = HttpResponse(
        f"window.__TAPNE_FRONTEND_CONFIG__ = {payload_text};\n",
        content_type="application/javascript; charset=utf-8",
    )
    response["Cache-Control"] = "no-store"
    return response


@ensure_csrf_cookie
@require_GET
def frontend_entrypoint_view(
    request: HttpRequest,
    **_route_kwargs: object,
) -> HttpResponse:
    html = _frontend_shell_html(request)
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def frontend_asset_view(_request: HttpRequest, asset_path: str) -> FileResponse:
    path = _safe_dist_path(asset_path, base_dir=_frontend_dist_dir() / "assets")
    return _file_response(path, immutable=True)


@require_GET
def frontend_root_artifact_view(_request: HttpRequest, artifact_name: str) -> FileResponse:
    path = _safe_dist_path(artifact_name)
    return _file_response(path, immutable=False)


@ensure_csrf_cookie
@require_GET
def session_api_view(request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        {
            "ok": True,
            "authenticated": bool(getattr(request.user, "is_authenticated", False)),
            "csrf_token": get_token(request),
            "user": _session_user_payload(request),
            "runtime": _runtime_config_payload(request),
        }
    )


@require_http_methods(["POST"])
def auth_login_api_view(request: HttpRequest) -> JsonResponse:
    payload = _request_payload(request)
    form = LoginForm(request=request, data=payload)
    if not form.is_valid():
        return _json_error("Invalid credentials.", extra={"errors": _form_errors(form)})

    user = form.get_user()
    login(request, user)
    return JsonResponse(
        {
            "ok": True,
            "authenticated": True,
            "csrf_token": get_token(request),
            "user": _session_user_payload(request),
        }
    )


@require_http_methods(["POST"])
def auth_signup_api_view(request: HttpRequest) -> JsonResponse:
    payload = _request_payload(request)
    form = SignUpForm(payload)
    if not form.is_valid():
        return _json_error("Signup failed.", extra={"errors": _form_errors(form)})

    user = form.save()
    ensure_profile(user)
    login(request, user)
    return JsonResponse(
        {
            "ok": True,
            "authenticated": True,
            "csrf_token": get_token(request),
            "user": _session_user_payload(request),
        },
        status=201,
    )


@require_POST
def auth_logout_api_view(request: HttpRequest) -> JsonResponse:
    if request.user.is_authenticated:
        logout(request)
    return JsonResponse({"ok": True, "authenticated": False, "user": None})


@require_GET
def home_api_view(request: HttpRequest) -> JsonResponse:
    payload = build_home_payload_for_user(request.user, limit_per_section=None, include_profiles=True)
    response_payload: dict[str, object] = dict(payload)
    response_payload["trips"] = _enrich_trip_cards([dict(row) for row in payload.get("trips", [])])
    response_payload["profiles"] = _enrich_profile_cards([dict(row) for row in payload.get("profiles", [])])
    response_payload["blogs"] = _enrich_blog_cards([dict(row) for row in payload.get("blogs", [])])
    return JsonResponse({"ok": True, **response_payload})


@require_GET
def trip_list_api_view(request: HttpRequest) -> JsonResponse:
    payload = build_trip_list_payload_for_user(
        request.user,
        filters={
            "destination": request.GET.get("destination", ""),
            "duration": request.GET.get("duration", "all"),
            "trip_type": request.GET.get("trip_type", "all"),
            "budget": request.GET.get("budget", "all"),
            "difficulty": request.GET.get("difficulty", "all"),
        },
    )
    response_payload: dict[str, object] = dict(payload)
    response_payload["trips"] = _enrich_trip_cards([dict(row) for row in payload.get("trips", [])])
    return JsonResponse({"ok": True, **response_payload})


@require_GET
def trip_detail_api_view(request: HttpRequest, trip_id: int) -> JsonResponse:
    payload = build_trip_detail_payload_for_user(request.user, trip_id=trip_id)
    source = str(payload.get("source", "") or "").strip()
    if _live_data_required() and source != "live-db":
        return _json_error("Trip not found.", status=404)

    trip_row = Trip.objects.select_related("host", "host__account_profile").filter(pk=trip_id).first()
    if trip_row is None:
        return _json_error("Trip not found.", status=404)

    trip_payload = dict(payload.get("trip", {}))
    host_identity = _member_identity_payload(trip_row.host)

    participants: list[dict[str, str]] = [
        {
            "username": host_identity["username"],
            "display_name": host_identity["display_name"],
            "role": "host",
        }
    ]
    approved_rows = (
        EnrollmentRequest.objects.select_related("requester", "requester__account_profile")
        .filter(trip=trip_row, status=EnrollmentRequest.STATUS_APPROVED)
        .order_by("-updated_at", "-pk")[:12]
    )
    for enrollment_row in approved_rows:
        requester_identity = _member_identity_payload(enrollment_row.requester)
        participants.append(
            {
                "username": requester_identity["username"],
                "display_name": requester_identity["display_name"],
                "role": "member",
            }
        )

    similar_rows: list[Trip] = []
    seen_trip_ids: set[int] = set()
    similar_querysets: list[Any] = []
    if trip_row.trip_type:
        similar_querysets.append(
            Trip.objects.select_related("host", "host__account_profile")
            .filter(is_published=True, trip_type=trip_row.trip_type)
            .exclude(pk=trip_row.pk)
            .order_by("-traffic_score", "starts_at", "pk")
        )
    destination_hint = str(trip_row.destination or "").split(",")[0].strip()
    if destination_hint:
        similar_querysets.append(
            Trip.objects.select_related("host", "host__account_profile")
            .filter(is_published=True, destination__icontains=destination_hint)
            .exclude(pk=trip_row.pk)
            .order_by("-traffic_score", "starts_at", "pk")
        )
    similar_querysets.append(
        Trip.objects.select_related("host", "host__account_profile")
        .filter(is_published=True)
        .exclude(pk=trip_row.pk)
        .order_by("-traffic_score", "starts_at", "pk")
    )
    for queryset in similar_querysets:
        for candidate in queryset:
            candidate_id = int(getattr(candidate, "pk", 0) or 0)
            if candidate_id <= 0 or candidate_id in seen_trip_ids:
                continue
            seen_trip_ids.add(candidate_id)
            similar_rows.append(candidate)
            if len(similar_rows) >= 3:
                break
        if len(similar_rows) >= 3:
            break

    join_request_payload: dict[str, str] | None = None
    trip_host_id = int(getattr(trip_row, "host_id", 0) or 0)
    if request.user.is_authenticated and int(getattr(request.user, "pk", 0) or 0) != trip_host_id:
        existing_request = (
            EnrollmentRequest.objects.filter(trip=trip_row, requester=request.user)
            .only("status")
            .first()
        )
        if existing_request is not None:
            join_request_payload = {
                "status": str(existing_request.status or "").strip().lower(),
                "outcome": "existing",
            }

    return JsonResponse(
        {
            "ok": True,
            **payload,
            "trip": _enrich_trip_cards([trip_payload])[0],
            "host": host_identity,
            "participants": participants,
            "similar_trips": [_serialize_trip_for_frontend(row) for row in similar_rows],
            "join_request": join_request_payload,
        }
    )


@require_GET
def my_trips_api_view(request: HttpRequest) -> JsonResponse:
    payload = build_my_trips_payload_for_member(request.user, tab=request.GET.get("tab", "drafts"))
    response_payload: dict[str, object] = dict(payload)
    response_payload["trips"] = _enrich_trip_cards([dict(row) for row in payload.get("trips", [])])
    return JsonResponse({"ok": True, **response_payload})


@require_GET
def blog_list_api_view(request: HttpRequest) -> JsonResponse:
    payload = build_blog_list_payload_for_user(request.user)
    response_payload: dict[str, object] = dict(payload)
    response_payload["blogs"] = _enrich_blog_cards([dict(row) for row in payload.get("blogs", [])])
    return JsonResponse({"ok": True, **response_payload})


@require_GET
def blog_detail_api_view(request: HttpRequest, slug: str) -> JsonResponse:
    payload = build_blog_detail_payload_for_user(request.user, slug=slug)
    source = str(payload.get("source", "") or "").strip()
    if _live_data_required() and source != "live-db":
        return _json_error("Blog not found.", status=404)
    blog_payload = dict(payload.get("blog", {}))
    blog_rows = _enrich_blog_cards([blog_payload])
    return JsonResponse({"ok": True, **payload, "blog": blog_rows[0] if blog_rows else blog_payload})


@require_http_methods(["GET", "PATCH"])
def my_profile_api_view(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()

    profile = ensure_profile(request.user)
    if request.method == "PATCH":
        payload = _request_payload(request)
        form = ProfileEditForm(
            {
                "display_name": str(payload.get("display_name", profile.display_name) or "").strip(),
                "bio": str(payload.get("bio", profile.bio) or "").strip(),
                "location": str(payload.get("location", profile.location) or "").strip(),
                "website": str(payload.get("website", profile.website) or "").strip(),
                "email": str(payload.get("email", getattr(request.user, "email", "")) or "").strip(),
                "first_name": str(payload.get("first_name", getattr(request.user, "first_name", "")) or "").strip(),
                "last_name": str(payload.get("last_name", getattr(request.user, "last_name", "")) or "").strip(),
            },
            instance=profile,
            user=request.user,
        )
        if not form.is_valid():
            return _json_error("Profile update failed.", extra={"errors": _form_errors(form)})
        form.save()
        refreshed_profile = ensure_profile(request.user)
        return JsonResponse(
            {
                "ok": True,
                "profile": _session_user_payload(request),
                "member_profile": {
                    "username": str(getattr(request.user, "username", "") or "").strip(),
                    "display_name": refreshed_profile.effective_display_name,
                    "bio": str(refreshed_profile.bio or ""),
                    "location": str(refreshed_profile.location or ""),
                    "website": str(refreshed_profile.website or ""),
                    "email": str(getattr(request.user, "email", "") or "").strip(),
                },
            }
        )

    created_trips, joined_trips = profile_trip_sections_for_member(request.user)
    return JsonResponse(
        {
            "ok": True,
            "profile": {
                "username": str(getattr(request.user, "username", "") or "").strip(),
                "display_name": profile.effective_display_name,
                "bio": str(profile.bio or ""),
                "location": str(profile.location or ""),
                "website": str(profile.website or ""),
                "email": str(getattr(request.user, "email", "") or "").strip(),
            },
            "created_trips": _enrich_trip_cards([dict(row) for row in created_trips]),
            "joined_trips": _enrich_trip_cards([dict(row) for row in joined_trips]),
            "mode": "member-profile",
            "reason": "Profile loaded from persisted account data.",
        }
    )


@require_http_methods(["POST"])
def trip_draft_create_api_view(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()

    trip = Trip(host=request.user, is_published=False)
    _apply_trip_payload(trip, _request_payload(request))
    trip.save()
    return JsonResponse({"ok": True, "trip": _serialize_trip_for_frontend(trip)}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def trip_draft_detail_api_view(request: HttpRequest, trip_id: int) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()

    trip = (
        Trip.objects.select_related("host", "host__account_profile")
        .filter(pk=trip_id, host=request.user, is_published=False)
        .first()
    )
    if trip is None:
        return _json_error("Draft not found.", status=404)

    if request.method == "GET":
        return JsonResponse({"ok": True, "trip": _serialize_trip_for_frontend(trip)})

    if request.method == "PATCH":
        _apply_trip_payload(trip, _request_payload(request))
        trip.save()
        return JsonResponse({"ok": True, "trip": _serialize_trip_for_frontend(trip)})

    trip.delete()
    return JsonResponse({"ok": True})


@require_http_methods(["POST"])
def trip_draft_publish_api_view(request: HttpRequest, trip_id: int) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()

    trip = (
        Trip.objects.select_related("host", "host__account_profile")
        .filter(pk=trip_id, host=request.user, is_published=False)
        .first()
    )
    if trip is None:
        return _json_error("Draft not found.", status=404)

    _apply_trip_payload(trip, _request_payload(request))
    trip.is_published = True
    try:
        trip.full_clean()
    except ValidationError as exc:
        trip.is_published = False
        if hasattr(exc, "message_dict"):
            return _json_error("Trip cannot be published yet.", extra={"errors": exc.message_dict})
        return _json_error("Trip cannot be published yet.")

    trip.save()
    return JsonResponse({"ok": True, "trip": _serialize_trip_for_frontend(trip)})


@require_GET
def bookmarks_api_view(request: HttpRequest) -> JsonResponse:
    payload = build_bookmarks_payload_for_member(request.user)
    return JsonResponse({"ok": True, **payload})


@require_GET
def activity_api_view(request: HttpRequest) -> JsonResponse:
    payload = build_activity_payload_for_member(request.user, activity_filter=request.GET.get("filter", "all"))
    return JsonResponse({"ok": True, **payload})


@require_GET
def settings_api_view(request: HttpRequest) -> JsonResponse:
    payload = build_settings_payload_for_member(request.user)
    return JsonResponse({"ok": True, **payload})


@require_GET
def hosting_inbox_api_view(request: HttpRequest) -> JsonResponse:
    payload = build_hosting_inbox_payload_for_member(request.user, status=request.GET.get("status", "pending"))
    return JsonResponse({"ok": True, **payload})


@require_GET
def dm_inbox_api_view(request: HttpRequest) -> JsonResponse:
    payload = build_dm_inbox_payload_for_member(request.user)
    return JsonResponse({"ok": True, **payload})


@require_GET
def dm_thread_api_view(request: HttpRequest, thread_id: int) -> JsonResponse:
    payload = build_dm_thread_payload_for_member(request.user, thread_id=thread_id)
    return JsonResponse({"ok": True, **payload})


@require_POST
def trip_join_request_api_view(request: HttpRequest, trip_id: int) -> JsonResponse:
    trip = Trip.objects.select_related("host").filter(pk=trip_id, is_published=True).first()
    if trip is None:
        return _json_error("Trip not found.", status=404)

    payload = _request_payload(request)
    request_row, outcome = submit_join_request(
        member=request.user,
        trip=trip,
        message=payload.get("message", ""),
    )
    if outcome == "member-required":
        return _member_only_error()
    if outcome == "host-self-request-blocked":
        return _json_error("Hosts cannot request to join their own trip.", status=400)

    row_data = request_row.to_enrollment_request_data() if request_row is not None else None
    return JsonResponse({"ok": request_row is not None, "outcome": outcome, "request": row_data})


@require_POST
def hosting_decision_api_view(request: HttpRequest, request_id: int) -> JsonResponse:
    from enrollment.models import EnrollmentRequest

    request_row = EnrollmentRequest.objects.select_related("trip", "requester", "reviewed_by").filter(pk=request_id).first()
    if request_row is None:
        return _json_error("Join request not found.", status=404)

    payload = _request_payload(request)
    decision = str(payload.get("decision", "") or "").strip()
    outcome = apply_enrollment_decision(request_row=request_row, host=request.user, decision=decision)
    request_row.refresh_from_db()
    return JsonResponse(
        {
            "ok": outcome in {"approved", "denied", "already-approved", "already-denied"},
            "outcome": outcome,
            "request": request_row.to_enrollment_request_data(),
        }
    )
