from __future__ import annotations

from collections.abc import Mapping
import base64
import binascii
import json
import mimetypes
import re
import secrets
import urllib.parse
import urllib.request
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final, cast

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import login, logout
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.mail import send_mail
from django.db.models import Q
from django.core.serializers.json import DjangoJSONEncoder
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.timezone import now
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST, require_safe

from accounts.forms import LoginForm, ProfileEditForm
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

from interactions.models import (
    DirectMessage,
    DirectMessageThread,
    build_dm_thread_payload_for_member,
    get_or_create_dm_thread_for_members,
    send_dm_message,
)
from reviews.models import submit_review
from settings_app.models import build_settings_payload_for_member
from social.models import Bookmark, build_bookmarks_payload_for_member, resolve_bookmark_target
from trips.models import (
    Trip,
    TripFaqItem,
    TripItineraryDay,
    TRIP_BOOKING_STATUS_VALUES,
    build_trip_detail_payload_for_user,
    build_trip_list_payload_for_user,
)

PUBLIC_CACHE_SECONDS: Final[int] = 3600
IMMUTABLE_CACHE_SECONDS: Final[int] = 31536000
BRAND_TOKENS_MARKER: Final[str] = "frontend-brand/tokens"
BRAND_OVERRIDES_MARKER: Final[str] = "frontend-brand/overrides"
FRONTEND_RUNTIME_INLINE_ATTR: Final[str] = "data-tapne-runtime"
FRONTEND_RUNTIME_INLINE_VALUE: Final[str] = "inline-config"
FRONTEND_MIME_TYPE_OVERRIDES: Final[dict[str, str]] = {
    ".css": "text/css",
    ".ico": "image/x-icon",
    ".js": "text/javascript",
    ".json": "application/json",
    ".map": "application/json",
    ".mjs": "text/javascript",
    ".svg": "image/svg+xml",
    ".webmanifest": "application/manifest+json",
}
OTP_CACHE_TTL: Final[int] = 600  # 10 minutes
OTP_MAX_ATTEMPTS: Final[int] = 5
UserModel = get_user_model()


def _otp_cache_key(email: str) -> str:
    return f"tapne:otp:{email.lower().strip()}"


def _generate_otp() -> str:
    return str(secrets.randbelow(900000) + 100000)


def _generate_username_from_email(email: str) -> str:
    base = re.sub(r"[^a-z0-9_]", "", email.split("@")[0].lower())[:20] or "traveler"
    username = base
    counter = 1
    while UserModel.objects.filter(username__iexact=username).exists():
        username = f"{base}{counter}"
        counter += 1
    return username


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
    content_type = FRONTEND_MIME_TYPE_OVERRIDES.get(path.suffix.lower())
    if content_type is None:
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


def _normalize_itinerary_days(value: object) -> list[TripItineraryDay]:
    if not isinstance(value, list):
        return []

    cleaned: list[TripItineraryDay] = []
    for raw_day in cast(list[object], value):
        if not isinstance(raw_day, Mapping):
            continue
        day = cast(Mapping[str, object], raw_day)
        title = " ".join(str(day.get("title", "") or "").strip().split())[:180]
        description = str(day.get("description", "") or "").strip()[:2000]
        stay = " ".join(str(day.get("stay", "") or "").strip().split())[:180]
        meals = " ".join(str(day.get("meals", "") or "").strip().split())[:180]
        activities = " ".join(str(day.get("activities", "") or "").strip().split())[:280]
        is_flexible = bool(day.get("is_flexible", False))
        if not any((title, description, stay, meals, activities)):
            continue
        cleaned.append(
            {
                "title": title,
                "description": description,
                "stay": stay,
                "meals": meals,
                "activities": activities,
                "is_flexible": is_flexible,
            }
        )
    return cleaned


def _normalize_faqs(value: object) -> list[TripFaqItem]:
    if not isinstance(value, list):
        return []

    cleaned: list[TripFaqItem] = []
    for raw_faq in cast(list[object], value):
        if not isinstance(raw_faq, Mapping):
            continue
        faq = cast(Mapping[str, object], raw_faq)
        question = " ".join(str(faq.get("question", "") or "").strip().split())[:280]
        answer = str(faq.get("answer", "") or "").strip()[:2000]
        if not question and not answer:
            continue
        cleaned.append({"question": question, "answer": answer})
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


def _normalize_json_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(raw_key): raw_value
        for raw_key, raw_value in cast(Mapping[object, object], value).items()
        if str(raw_key).strip()
    }


def _save_data_url_to_image_field(
    *,
    field_file: Any,
    data_url: object,
    file_prefix: str,
) -> bool:
    raw_value = str(data_url or "").strip()
    if not raw_value.startswith("data:image/"):
        return False

    match = re.match(r"^data:image/(?P<ext>[a-zA-Z0-9.+-]+);base64,(?P<data>.+)$", raw_value)
    if match is None:
        return False

    ext = str(match.group("ext") or "png").lower()
    if ext == "jpeg":
        ext = "jpg"

    try:
        decoded = base64.b64decode(match.group("data"), validate=True)
    except (ValueError, binascii.Error):
        return False

    if not decoded:
        return False

    safe_name = f"{file_prefix}_{secrets.token_hex(8)}.{ext}"
    field_file.save(safe_name, ContentFile(decoded), save=False)
    return True


def _apply_trip_payload(trip: Trip, payload: dict[str, object]) -> None:
    trip.title = _normalize_string(payload.get("title", trip.title))
    trip.destination = _normalize_string(payload.get("destination", trip.destination))
    trip.summary = _normalize_string(payload.get("summary", trip.summary))
    trip.description = str(payload.get("description", trip.description) or "").strip()
    trip.trip_type = _normalize_string(payload.get("trip_type", trip.trip_type)).lower()
    trip.currency = _normalize_string(payload.get("currency", trip.currency)).upper() or "INR"
    trip.difficulty_level = _normalize_string(payload.get("difficulty_level", trip.difficulty_level)).lower()
    trip.pace_level = _normalize_string(payload.get("pace_level", trip.pace_level)).lower()
    trip.cancellation_policy = str(payload.get("cancellation_policy", trip.cancellation_policy) or "").strip()
    trip.code_of_conduct = str(payload.get("code_of_conduct", trip.code_of_conduct) or "").strip()
    trip.general_policies = str(payload.get("general_policies", trip.general_policies) or "").strip()
    trip.access_type = _normalize_string(payload.get("access_type", trip.access_type)).lower() or "open"
    trip.payment_method = _normalize_string(payload.get("payment_method", trip.payment_method)).lower() or "direct_contact"
    trip.payment_details = str(payload.get("payment_details", trip.payment_details) or "").strip()
    trip.medical_declaration_required = bool(payload.get("medical_declaration_required", trip.medical_declaration_required))
    trip.emergency_contact_required = bool(payload.get("emergency_contact_required", trip.emergency_contact_required))
    trip.contact_preference = _normalize_string(payload.get("contact_preference", trip.contact_preference)).lower() or "in_app"
    trip.co_hosts = " ".join(_normalize_string(payload.get("co_hosts", trip.co_hosts)).split())
    if "draft_form_data" in payload:
        trip.draft_form_data = _normalize_json_mapping(payload.get("draft_form_data"))

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
    if "early_bird_price" in payload:
        trip.early_bird_price = _normalize_optional_decimal(payload.get("early_bird_price"))
    if "payment_terms" in payload:
        trip.payment_terms = _normalize_string(payload.get("payment_terms", trip.payment_terms))

    if "highlights" in payload:
        trip.highlights = _normalize_string_list(payload.get("highlights"))
    if "itinerary_days" in payload:
        trip.itinerary_days = _normalize_itinerary_days(payload.get("itinerary_days"))
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
    if "faqs" in payload:
        trip.faqs = _normalize_faqs(payload.get("faqs"))
    if "banner_image_data" in payload:
        _save_data_url_to_image_field(
            field_file=trip.banner_image,
            data_url=payload.get("banner_image_data"),
            file_prefix=f"trip_{int(getattr(trip, 'pk', 0) or 0) or 'draft'}",
        )


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
        "avatar_url": str(profile.avatar_url or ""),
        "travel_tags": list(profile.travel_tags or []),
        "created_trips": created_trips,
        "joined_trips": joined_trips,
        "settings": settings_payload["settings"],
        "profile_url": "/profile",
        "public_profile_url": f"/u/{getattr(user, 'username', '')}/",
    }


def _runtime_config_payload(request: HttpRequest) -> dict[str, object]:
    request_user = getattr(request, "user", None)
    dm_inbox_url = reverse("frontend:api-dm-inbox")
    if request.path.rstrip("/") == "/inbox":
        dm_username = str(request.GET.get("dm", "") or "").strip()
        if dm_username:
            dm_inbox_url = f"{dm_inbox_url}?{urllib.parse.urlencode({'dm': dm_username})}"
    return {
        "app_name": "tapne",
        "generated_at": now().isoformat(),
        "frontend_mode": "lovable-spa",
        "frontend_enabled": True,
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
            "dm_inbox": dm_inbox_url,
            "trip_drafts": reverse("frontend:api-trip-draft-create"),
            "manage_trip": "/frontend-api/manage-trip/",
            "messages": "/frontend-api/messages/",
            "trip_chat": "/frontend-api/trip-chat/",
            "users_search": reverse("frontend:api-users-search"),
            "notifications": reverse("frontend:api-notifications"),
            "trip_reviews": "/frontend-api/trips/",
            "trip_review": "/frontend-api/trips/",
            "reviews": reverse("frontend:api-reviews-list"),
            "followers": reverse("frontend:api-profile-followers"),
            "following": reverse("frontend:api-profile-following"),
            "dm_start": reverse("frontend:api-dm-start-thread"),
            "account_deactivate": reverse("frontend:api-account-deactivate"),
            "account_delete": reverse("frontend:api-account-delete"),
        },
        "routes": {
            "home": "/",
            "trips": "/trips",
            "stories": "/stories",
            "profile": "/profile",
            "profile_edit": "/profile/edit",
            "trip_new": "/trips/new",
            "story_new": "/stories/new",
            "search": "/search",
            "messages": "/messages",
            "bookmarks": "/bookmarks",
            "notifications": "/notifications",
            "settings": "/settings",
            "dashboard": "/dashboard",
            "dashboard_trips": "/dashboard/trips",
            "dashboard_stories": "/dashboard/stories",
            "dashboard_reviews": "/dashboard/reviews",
            "dashboard_subscriptions": "/dashboard/subscriptions",
        },
        "google_oauth_url": (
            reverse("frontend:api-google-oauth-start")
            if getattr(settings, "GOOGLE_CLIENT_ID", "").strip()
            else ""
        ),
        "auth": {
            # Auth is handled entirely via the Lovable modal + /frontend-api/auth/* endpoints.
            # No Django-rendered auth pages exist — the legacy /accounts/login/ etc. routes
            # were removed in the SPA cutover.
        },
        "csrf": {
            "cookie_name": settings.CSRF_COOKIE_NAME,
            # settings.CSRF_HEADER_NAME is stored as a Django META key ("HTTP_X_CSRFTOKEN").
            # Convert to the HTTP wire format ("X-Csrftoken") that fetch() uses as a header name.
            # HTTP headers are case-insensitive; Django normalises back to the META key on receipt.
            "header_name": "-".join(
                p.capitalize()
                for p in settings.CSRF_HEADER_NAME.removeprefix("HTTP_").split("_")
            ),
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
        # mode.ts in the dual-mode Lovable bundle checks window.TAPNE_RUNTIME_CONFIG
        # to distinguish Django production from Lovable dev mode (IS_DEV_MODE).
        # Keep both names in sync so both the legacy @frontend bundle and the new
        # dual-mode bundle read the same config object.
        "window.TAPNE_RUNTIME_CONFIG = window.__TAPNE_FRONTEND_CONFIG__;"
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
@require_safe
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
    payload = dict(_request_payload(request))
    if "username" not in payload:
        email = _normalize_string(payload.get("email", ""))
        if email:
            payload["username"] = email
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
    email = _normalize_string(payload.get("email", ""))
    password = _normalize_string(payload.get("password", ""))
    first_name = _normalize_string(payload.get("first_name", ""))

    if not email or not password:
        return _json_error("Email and password are required.", extra={"errors": {"email": ["Required."]}})

    from email_validator import EmailNotValidError, validate_email as _validate_email
    try:
        normalized_email = _validate_email(email, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        return _json_error(str(exc), extra={"errors": {"email": [str(exc)]}})

    if UserModel.objects.filter(email__iexact=normalized_email).exists():
        return _json_error("An account with this email already exists.", extra={"errors": {"email": ["An account with this email already exists."]}})

    if len(password) < 8:
        return _json_error("Password must be at least 8 characters.", extra={"errors": {"password": ["Password must be at least 8 characters."]}})

    username = _generate_username_from_email(normalized_email)
    try:
        user = UserModel.objects.create_user(
            username=username,
            email=normalized_email,
            password=password,
            first_name=first_name,
        )
    except Exception:
        return _json_error("Signup failed. Please try again.")

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
    response_payload["featured_trips"] = list(cast(list[dict[str, object]], response_payload["trips"]))
    response_payload["blogs"] = _enrich_blog_cards([dict(row) for row in payload.get("blogs", [])])

    # Build community_profiles — shape required by CommunityProfile interface:
    # { username, display_name, avatar_url?, travel_tags?, location?, bio? }
    enriched_profiles = _enrich_profile_cards([dict(row) for row in payload.get("profiles", [])])
    community_profiles: list[dict[str, object]] = []
    for p in enriched_profiles:
        community_profiles.append({
            "username": str(p.get("username", "") or ""),
            "display_name": str(p.get("display_name", "") or p.get("username", "") or ""),
            "bio": str(p.get("bio", "") or ""),
            "location": str(p.get("location", "") or ""),
        })
    response_payload["community_profiles"] = community_profiles

    # Real stats from DB, filtered the same way as public catalog surfaces.
    from accounts.models import AccountProfile
    from trips.models import Trip as _Trip
    from tapne.features import _demo_qs_filter, demo_catalog_visible

    profile_filter: dict[str, bool] = {} if demo_catalog_visible() else {"is_demo": False}
    total_users = int(AccountProfile.objects.filter(**profile_filter).count())
    trips_hosted = int(_Trip.objects.filter(is_published=True, **_demo_qs_filter()).count())
    distinct_destinations = int(
        _Trip.objects.filter(is_published=True, destination__gt="", **_demo_qs_filter())
        .values("destination").distinct().count()
    )
    response_payload["stats"] = {
        "travelers": total_users,
        "travelers_count": total_users,
        "trips_hosted": trips_hosted,
        "trips_hosted_count": trips_hosted,
        "destinations": distinct_destinations,
        "destinations_count": distinct_destinations,
    }

    # No testimonials model yet — return empty; section hides itself when empty
    response_payload["testimonials"] = []

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
    trips = [dict(row) for row in payload.get("trips", [])]

    query = str(request.GET.get("q", "") or "").strip().lower()
    if query:
        def _matches(card: dict[str, object]) -> bool:
            haystack = " ".join(
                str(card.get(field, "") or "")
                for field in ("title", "destination", "summary", "description")
            ).lower()
            return query in haystack
        trips = [card for card in trips if _matches(card)]

    sort_order = str(request.GET.get("sort", "") or "").strip().lower()
    if sort_order == "recent":
        trips.sort(
            key=lambda card: str(card.get("starts_at") or card.get("created_at") or ""),
            reverse=True,
        )

    response_payload["trips"] = _enrich_trip_cards(trips)
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

    # Completed trips are only visible to the host or approved enrollees.
    # Others (guests, non-participating travelers) get 404 — trip exists but is hidden.
    if trip_row.status == Trip.STATUS_COMPLETED:
        viewer_id = int(getattr(request.user, "pk", 0) or 0)
        trip_host_id = int(getattr(trip_row, "host_id", 0) or 0)
        is_host = request.user.is_authenticated and viewer_id == trip_host_id
        is_enrollee = False
        if request.user.is_authenticated and viewer_id > 0 and not is_host:
            is_enrollee = EnrollmentRequest.objects.filter(
                trip_id=trip_row.pk,
                requester_id=viewer_id,
                status=EnrollmentRequest.STATUS_APPROVED,
            ).exists()
        if not (is_host or is_enrollee):
            return _json_error("Trip not found.", status=404)

    trip_payload = dict(payload.get("trip", {}))
    host_identity = _member_identity_payload(trip_row.host)

    co_hosts_str = str(getattr(trip_row, "co_hosts", "") or "").strip()
    co_host_usernames = [u for u in co_hosts_str.split() if u]
    co_host_profiles = list(_identity_map_for_usernames(co_host_usernames).values()) if co_host_usernames else []

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
            .filter(status=Trip.STATUS_PUBLISHED, trip_type=trip_row.trip_type)
            .exclude(pk=trip_row.pk)
            .order_by("-traffic_score", "starts_at", "pk")
        )
    destination_hint = str(trip_row.destination or "").split(",")[0].strip()
    if destination_hint:
        similar_querysets.append(
            Trip.objects.select_related("host", "host__account_profile")
            .filter(status=Trip.STATUS_PUBLISHED, destination__icontains=destination_hint)
            .exclude(pk=trip_row.pk)
            .order_by("-traffic_score", "starts_at", "pk")
        )
    similar_querysets.append(
        Trip.objects.select_related("host", "host__account_profile")
        .filter(status=Trip.STATUS_PUBLISHED)
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
            trip_payload["join_request_status"] = str(existing_request.status or "").strip().lower()
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
            "co_host_profiles": co_host_profiles,
            "participants": participants,
            "similar_trips": [_serialize_trip_for_frontend(row) for row in similar_rows],
            "join_request": join_request_payload,
        }
    )


@require_GET
def my_trips_api_view(request: HttpRequest) -> JsonResponse:
    # The frontend (MyTrips.tsx + DraftContext) fetches once and filters all tabs client-side.
    # We must return all trips (drafts + published + past) in a single call.
    # Build each tab separately and merge so all trip data is available.
    from trips.models import Trip as _Trip, enrich_trip_preview_fields as _enrich, ensure_trip_status_fresh

    viewer = request.user
    if not bool(getattr(viewer, "is_authenticated", False)):
        return _member_only_error()

    hosted_qs = _Trip.objects.select_related("host").filter(host=viewer)
    # Self-heal stale 'published' rows whose starts_at has passed.
    for _trip in hosted_qs.filter(status=_Trip.STATUS_PUBLISHED):
        ensure_trip_status_fresh(_trip)
    hosted_qs = _Trip.objects.select_related("host").filter(host=viewer)

    draft_rows = list(hosted_qs.filter(status=_Trip.STATUS_DRAFT).order_by("-updated_at", "-pk"))
    published_rows = list(hosted_qs.filter(status=_Trip.STATUS_PUBLISHED).order_by("starts_at", "pk"))
    past_rows = list(hosted_qs.filter(status=_Trip.STATUS_COMPLETED).order_by("-starts_at", "-pk"))

    all_trips = [dict(_enrich(t.to_trip_data())) for t in draft_rows + published_rows + past_rows]
    enriched = _enrich_trip_cards(all_trips)
    for trip in enriched:
        trip["can_manage"] = True

    return JsonResponse({
        "ok": True,
        "trips": enriched,
        "active_tab": "created",
        "tab_counts": {
            "drafts": len(draft_rows),
            "published": len(published_rows),
            "past": len(past_rows),
        },
    })


@require_http_methods(["GET", "POST"])
def blog_list_api_view(request: HttpRequest) -> JsonResponse:
    if request.method == "POST":
        return blog_create_api_view(request)

    from blogs.models import Blog

    author_filter = str(request.GET.get("author", "") or "").strip().lower()
    if author_filter == "me":
        if not request.user.is_authenticated:
            return _member_only_error()
        rows = (
            Blog.objects.select_related("author", "author__account_profile")
            .filter(author=request.user)
            .order_by("-created_at", "-id")
        )
        blogs = []
        for row in rows:
            card: dict[str, object] = dict(row.to_blog_data())
            card["status"] = "published" if bool(row.is_published) else "draft"
            blogs.append(card)
        response_payload: dict[str, object] = {
            "blogs": _enrich_blog_cards(blogs),
            "mode": "live-db",
            "reason": "author-me",
            "source": "live-db",
        }
        return JsonResponse({"ok": True, **response_payload})

    payload = build_blog_list_payload_for_user(request.user)
    response_payload = dict(payload)
    blogs = [dict(row) for row in payload.get("blogs", [])]

    query = str(request.GET.get("q", "") or "").strip().lower()
    if query:
        def _matches(card: dict[str, object]) -> bool:
            haystack = " ".join(
                str(card.get(field, "") or "")
                for field in ("title", "excerpt", "short_description", "summary", "location", "body")
            ).lower()
            return query in haystack
        blogs = [card for card in blogs if _matches(card)]

    response_payload["blogs"] = _enrich_blog_cards(blogs)
    return JsonResponse({"ok": True, **response_payload})


@require_http_methods(["GET", "PATCH", "DELETE"])
def blog_detail_api_view(request: HttpRequest, slug: str) -> JsonResponse:
    from blogs.models import Blog

    if request.method == "PATCH":
        if not request.user.is_authenticated:
            return _member_only_error()
        blog = Blog.objects.filter(slug=slug, author=request.user).first()
        if blog is None:
            return _json_error("Experience not found.", status=404)

        payload = _request_payload(request)
        title = _normalize_string(payload.get("title", blog.title))
        if not title:
            return _json_error("Title is required.", extra={"errors": {"title": ["Required."]}})

        blog.title = title
        blog.excerpt = _normalize_string(payload.get("short_description", payload.get("excerpt", blog.excerpt)))
        blog.body = str(payload.get("body", blog.body) or "").strip()
        blog.cover_image_url = str(payload.get("cover_image_url", blog.cover_image_url) or "").strip()
        blog.location = _normalize_string(payload.get("location", blog.location))
        blog.tags = _normalize_string_list(payload.get("tags"), max_items=12, max_length=40)
        blog.save()
        return JsonResponse({"ok": True, "blog": blog.to_blog_data()})

    if request.method == "DELETE":
        if not request.user.is_authenticated:
            return _member_only_error()
        blog = Blog.objects.filter(slug=slug, author=request.user).first()
        if blog is None:
            return _json_error("Experience not found.", status=404)
        blog.delete()
        return JsonResponse({"ok": True})

    payload = build_blog_detail_payload_for_user(request.user, slug=slug)
    source = str(payload.get("source", "") or "").strip()
    if _live_data_required() and source != "live-db":
        return _json_error("Blog not found.", status=404)
    blog_payload = dict(payload.get("blog", {}))
    blog_rows = _enrich_blog_cards([blog_payload])
    return JsonResponse({"ok": True, **payload, "blog": blog_rows[0] if blog_rows else blog_payload})


@require_GET
def blog_cover_image_view(request: HttpRequest, slug: str) -> HttpResponse | FileResponse:
    from blogs.models import Blog, build_demo_blog_cover_storage_name
    from tapne.features import demo_catalog_visible

    blog = Blog.objects.only("id", "slug", "author_id", "is_demo", "is_published").filter(slug=slug).first()
    if blog is None or not bool(getattr(blog, "is_demo", False)):
        raise Http404("Blog cover not found.")

    viewer_id = int(getattr(request.user, "pk", 0) or 0)
    blog_author_id = int(getattr(blog, "author_id", 0) or 0)
    is_owner = bool(request.user.is_authenticated and blog_author_id == viewer_id)
    is_publicly_visible = bool(getattr(blog, "is_published", False)) and demo_catalog_visible()
    if not is_publicly_visible and not is_owner:
        raise Http404("Blog cover not found.")

    file_name = build_demo_blog_cover_storage_name(slug=str(getattr(blog, "slug", "") or ""), blog_id=int(blog.pk or 0))
    if not default_storage.exists(file_name):
        raise Http404("Blog cover not found.")

    try:
        blog_cover = default_storage.open(file_name, "rb")
    except Exception as exc:
        raise Http404("Blog cover not found.") from exc

    content_type, _ = mimetypes.guess_type(file_name)
    response = FileResponse(blog_cover, content_type=content_type or "application/octet-stream")
    response["Cache-Control"] = "public, max-age=300" if is_publicly_visible else "private, max-age=60"
    return response


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
        if "avatar_url" in payload:
            refreshed_profile.avatar_url = str(payload.get("avatar_url") or "")
        raw_tags = payload.get("travel_tags")
        if isinstance(raw_tags, list):
            refreshed_profile.travel_tags = [str(tag).strip() for tag in raw_tags if str(tag).strip()]
        if "avatar_url" in payload or isinstance(raw_tags, list):
            refreshed_profile.save(update_fields=["avatar_url", "travel_tags", "updated_at"])
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
                    "avatar_url": str(refreshed_profile.avatar_url or ""),
                    "travel_tags": list(refreshed_profile.travel_tags or []),
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
                "avatar_url": str(profile.avatar_url or ""),
                "travel_tags": list(profile.travel_tags or []),
                "email": str(getattr(request.user, "email", "") or "").strip(),
            },
            "created_trips": _enrich_trip_cards([dict(row) for row in created_trips]),
            "joined_trips": _enrich_trip_cards([dict(row) for row in joined_trips]),
            "mode": "member-profile",
            "reason": "Profile loaded from persisted account data.",
        }
    )


@require_http_methods(["POST", "DELETE"])
def profile_follow_api_view(request: HttpRequest, profile_id: str) -> JsonResponse:
    """Follow (POST) or unfollow (DELETE) a user."""
    if not request.user.is_authenticated:
        return _member_only_error()

    target_user = None
    if profile_id.isdigit():
        target_user = UserModel.objects.filter(pk=int(profile_id)).first()
    if target_user is None:
        target_user = UserModel.objects.filter(username=profile_id).first()
    if target_user is None:
        return _json_error("Profile not found.", status=404)

    if getattr(target_user, "pk", None) == getattr(request.user, "pk", None):
        return _json_error("You cannot follow yourself.", status=400)

    from social.models import FollowRelation
    if request.method == "POST":
        FollowRelation.objects.get_or_create(follower=request.user, following=target_user)
    else:
        FollowRelation.objects.filter(follower=request.user, following=target_user).delete()

    followers_count = int(FollowRelation.objects.filter(following=target_user).count())
    is_following = FollowRelation.objects.filter(follower=request.user, following=target_user).exists()
    return JsonResponse({"ok": True, "followers_count": followers_count, "is_following": is_following})


@require_GET
def profile_detail_api_view(request: HttpRequest, profile_id: str) -> JsonResponse:
    """Public profile endpoint used by Profile.tsx: GET /frontend-api/profile/<username_or_id>/"""
    # Resolve by username first, then by numeric PK.
    target_user = None
    if profile_id.isdigit():
        target_user = UserModel.objects.filter(pk=int(profile_id)).first()
    if target_user is None:
        target_user = UserModel.objects.filter(username=profile_id).first()
    if target_user is None:
        return _json_error("Profile not found.", status=404)

    profile = ensure_profile(target_user)
    viewer = request.user
    is_following = False
    followers_count = 0
    try:
        from social.models import FollowRelation
        followers_count = int(FollowRelation.objects.filter(following=target_user).count())
        if bool(getattr(viewer, "is_authenticated", False)):
            is_following = FollowRelation.objects.filter(follower=viewer, following=target_user).exists()
    except Exception:
        pass

    from accounts.views import profile_trip_sections_for_member
    created_trips, joined_trips = profile_trip_sections_for_member(target_user)

    return JsonResponse({
        "ok": True,
        "profile": {
            "username": str(getattr(target_user, "username", "") or ""),
            "display_name": str(profile.effective_display_name),
            "bio": str(profile.bio or ""),
            "location": str(profile.location or ""),
            "website": str(profile.website or ""),
            "avatar_url": str(profile.avatar_url or ""),
            "email": str(getattr(target_user, "email", "") or "") if (
                bool(getattr(viewer, "is_authenticated", False)) and
                getattr(viewer, "pk", None) == getattr(target_user, "pk", None)
            ) else "",
            "trips_hosted": len(created_trips),
            "trips_joined": len(joined_trips),
            "followers_count": followers_count,
            "is_following": is_following,
            "travel_tags": list(profile.travel_tags or []),
            "average_rating": None,
            "reviews_count": 0,
            "travelers_hosted": 0,
        },
        "trips_hosted": _enrich_trip_cards([dict(row) for row in created_trips]),
        "trips_joined": _enrich_trip_cards([dict(row) for row in joined_trips]),
        "reviews": [],
        "gallery": [],
    })


def _user_list_payload(users: list[Any]) -> list[dict[str, str]]:
    usernames = [str(getattr(u, "username", "") or "").strip() for u in users]
    identity_map = _identity_map_for_usernames([u for u in usernames if u])
    rows: list[dict[str, str]] = []
    for user in users:
        username = str(getattr(user, "username", "") or "").strip()
        identity = identity_map.get(username, {})
        rows.append({
            "username": username,
            "display_name": identity.get("display_name", username or "Tapne member"),
            "bio": identity.get("bio", ""),
            "location": identity.get("location", ""),
        })
    return rows


@require_GET
def profile_followers_api_view(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()
    from social.models import FollowRelation
    rows = (
        FollowRelation.objects.select_related("follower", "follower__account_profile")
        .filter(following=request.user)
        .order_by("-created_at", "-id")
    )
    users = [relation.follower for relation in rows]
    return JsonResponse({"ok": True, "users": _user_list_payload(users)})


@require_GET
def profile_following_api_view(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()
    from social.models import FollowRelation
    rows = (
        FollowRelation.objects.select_related("following", "following__account_profile")
        .filter(follower=request.user)
        .order_by("-created_at", "-id")
    )
    users = [relation.following for relation in rows]
    return JsonResponse({"ok": True, "users": _user_list_payload(users)})


@require_http_methods(["POST"])
def trip_draft_create_api_view(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()

    trip = Trip(host=request.user, is_published=False)
    _apply_trip_payload(trip, _request_payload(request))
    trip.save()
    return JsonResponse({"ok": True, "draft": _serialize_trip_for_frontend(trip)}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def trip_draft_detail_api_view(request: HttpRequest, trip_id: int) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()

    trip = (
        Trip.objects.select_related("host", "host__account_profile")
        .filter(pk=trip_id, host=request.user)
        .first()
    )
    if trip is None:
        return _json_error("Trip not found.", status=404)

    trip_payload = _serialize_trip_for_frontend(trip)

    if request.method == "GET":
        return JsonResponse({"ok": True, "draft": trip_payload, "trip": trip_payload})

    if request.method == "PATCH":
        _apply_trip_payload(trip, _request_payload(request))
        trip.save()
        trip_payload = _serialize_trip_for_frontend(trip)
        return JsonResponse({"ok": True, "draft": trip_payload, "trip": trip_payload})

    if trip.is_published:
        return _json_error("Published trips cannot be deleted via the draft endpoint.", status=400)

    trip.delete()
    return JsonResponse({"ok": True})


@require_http_methods(["POST"])
def trip_draft_publish_api_view(request: HttpRequest, trip_id: int) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()

    trip = (
        Trip.objects.select_related("host", "host__account_profile")
        .filter(pk=trip_id, host=request.user)
        .first()
    )
    if trip is None:
        return _json_error("Trip not found.", status=404)

    _apply_trip_payload(trip, _request_payload(request))
    if not trip.is_published:
        trip.is_published = True
    trip.save()
    trip_payload = _serialize_trip_for_frontend(trip)
    return JsonResponse({"ok": True, "draft": trip_payload, "trip": trip_payload})


@require_GET
def bookmarks_api_view(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()
    payload = build_bookmarks_payload_for_member(request.user)
    return JsonResponse({"ok": True, **payload})


@require_GET
def activity_api_view(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()
    payload = build_activity_payload_for_member(request.user, activity_filter=request.GET.get("filter", "all"))
    return JsonResponse({"ok": True, **payload})


@require_GET
def settings_api_view(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()
    payload = build_settings_payload_for_member(request.user)
    return JsonResponse({"ok": True, **payload})


@require_GET
def hosting_inbox_api_view(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()
    payload = build_hosting_inbox_payload_for_member(request.user, status=request.GET.get("status", "pending"))
    return JsonResponse({"ok": True, **payload})


@require_GET
def dm_inbox_api_view(request: HttpRequest) -> JsonResponse:
    viewer = request.user
    if not bool(getattr(viewer, "is_authenticated", False)):
        return JsonResponse({"ok": True, "threads": []})

    viewer_id = int(getattr(viewer, "pk", 0) or 0)
    viewer_username = str(getattr(viewer, "username", "") or "").strip()
    viewer_profile = ensure_profile(viewer)
    viewer_display_name = str(viewer_profile.effective_display_name)

    dm_username = str(request.GET.get("dm", "") or "").strip()
    if dm_username and dm_username != viewer_username:
        other_user = UserModel.objects.filter(username=dm_username).first()
        if other_user is not None:
            get_or_create_dm_thread_for_members(
                member=viewer,
                other_member=other_user,
            )

    thread_rows = list(
        DirectMessageThread.objects
        .select_related("member_one", "member_two")
        .filter(Q(member_one_id=viewer_id) | Q(member_two_id=viewer_id))
        .order_by("-updated_at", "-pk")[:30]
    )

    threads_data: list[dict[str, object]] = []
    for thread in thread_rows:
        peer = thread.other_participant(viewer)
        if peer is None:
            continue
        peer_username = str(getattr(peer, "username", "") or "").strip()
        peer_profile = ensure_profile(peer)
        peer_display_name = str(peer_profile.effective_display_name)

        # Load messages; senders are always one of the two participants so no extra queries.
        message_rows = list(
            DirectMessage.objects
            .select_related("sender")
            .filter(thread_id=thread.pk)
            .order_by("created_at", "pk")[:50]
        )

        messages: list[dict[str, object]] = []
        last_message = ""
        last_sent_at: str | None = None
        for msg in message_rows:
            sender_username = str(getattr(msg.sender, "username", "") or "").strip()
            sender_display_name = (
                viewer_display_name if sender_username == viewer_username
                else peer_display_name if sender_username == peer_username
                else sender_username
            )
            sent_at = msg.created_at.isoformat() if msg.created_at else ""
            messages.append({
                "id": int(msg.pk or 0),
                "thread_id": int(thread.pk or 0),
                "sender_username": sender_username,
                "sender_display_name": sender_display_name,
                "body": str(msg.body or "").strip(),
                "sent_at": sent_at,
            })
            last_message = str(msg.body or "")[:120]
            last_sent_at = sent_at

        threads_data.append({
            "id": int(thread.pk or 0),
            "type": "dm",
            "title": peer_display_name or peer_username,
            "participants": [
                {"username": viewer_username, "display_name": viewer_display_name},
                {"username": peer_username, "display_name": peer_display_name},
            ],
            "last_message": last_message,
            "last_sent_at": last_sent_at or (thread.updated_at.isoformat() if thread.updated_at else None),
            "unread_count": 0,
            "messages": messages,
        })

    return JsonResponse({"ok": True, "threads": threads_data})


@require_GET
def dm_thread_api_view(request: HttpRequest, thread_id: int) -> JsonResponse:
    payload = build_dm_thread_payload_for_member(request.user, thread_id=thread_id)
    return JsonResponse({"ok": True, **payload})


@require_POST
def dm_send_message_api_view(request: HttpRequest, thread_id: int) -> JsonResponse:
    """POST /frontend-api/dm/inbox/<thread_id>/messages/ — send a message to a thread."""
    if not request.user.is_authenticated:
        return _member_only_error()
    thread = DirectMessageThread.objects.filter(pk=thread_id).first()
    if thread is None:
        return _json_error("Thread not found.", status=404)
    payload = _request_payload(request)
    _, outcome = send_dm_message(
        thread=thread,
        sender=request.user,
        body=payload.get("body", ""),
    )
    if outcome == "not-participant":
        return _json_error("You are not a participant in this thread.", status=403)
    if outcome == "empty-message":
        return _json_error("Message body cannot be empty.", status=400)
    if outcome == "too-long":
        return _json_error("Message is too long.", status=400)
    return JsonResponse({"ok": outcome == "sent", "outcome": outcome})


@require_http_methods(["POST", "DELETE"])
def bookmark_trip_api_view(request: HttpRequest, trip_id: int) -> JsonResponse:
    """
    POST   /frontend-api/bookmarks/<trip_id>/ — add a trip bookmark.
    DELETE /frontend-api/bookmarks/<trip_id>/ — remove a trip bookmark.
    """
    if not request.user.is_authenticated:
        return _member_only_error()

    if request.method == "DELETE":
        deleted, _ = Bookmark.objects.filter(
            member=request.user,
            target_type=Bookmark.TARGET_TRIP,
            target_key=str(trip_id),
        ).delete()
        return JsonResponse({"ok": True, "removed": deleted > 0})

    # POST — add bookmark
    resolution = resolve_bookmark_target("trip", trip_id)
    if resolution is None:
        return _json_error("Trip not found.", status=404)
    Bookmark.objects.get_or_create(
        member=request.user,
        target_type=Bookmark.TARGET_TRIP,
        target_key=resolution.target_key,
        defaults={
            "target_label": resolution.target_label,
            "target_url": resolution.target_url,
        },
    )
    return JsonResponse({"ok": True})


@require_POST
def trip_duplicate_api_view(request: HttpRequest, trip_id: int) -> JsonResponse:
    """POST /frontend-api/trips/<trip_id>/duplicate/ — copy a trip as a new draft."""
    if not request.user.is_authenticated:
        return _member_only_error()
    trip = Trip.objects.filter(pk=trip_id, host=request.user).first()
    if trip is None:
        return _json_error("Trip not found.", status=404)

    trip.pk = None  # clear PK so save() creates a new row
    trip.title = f"Copy of {trip.title}"
    trip.is_published = False
    trip.traffic_score = 0
    trip.save()
    return JsonResponse({"ok": True, "trip_id": trip.pk})


@require_POST
def trip_join_request_api_view(request: HttpRequest, trip_id: int) -> JsonResponse:
    trip = (
        Trip.objects.select_related("host")
        .filter(pk=trip_id, status=Trip.STATUS_PUBLISHED)
        .first()
    )
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


# ── Manage Trip ───────────────────────────────────────────────────────────────


def _manage_trip_participant_payload(req: EnrollmentRequest) -> dict[str, object]:
    requester = req.requester
    profile = getattr(requester, "account_profile", None)
    display_name = (
        getattr(profile, "effective_display_name", None)
        or getattr(requester, "first_name", "")
        or getattr(requester, "username", "")
    )
    joined_ts = req.reviewed_at or req.updated_at or req.created_at
    return {
        "id": int(req.pk or 0),
        "user_id": int(getattr(requester, "pk", 0) or 0),
        "username": str(getattr(requester, "username", "") or ""),
        "display_name": str(display_name or ""),
        "status": "confirmed",
        "joined_at": joined_ts.isoformat() if joined_ts else req.created_at.isoformat(),
    }


def _manage_trip_application_payload(req: EnrollmentRequest, trip_row: Trip) -> dict[str, object]:
    requester = req.requester
    profile = getattr(requester, "account_profile", None)
    display_name = (
        getattr(profile, "effective_display_name", None)
        or getattr(requester, "first_name", "")
        or getattr(requester, "username", "")
    )
    return {
        "id": int(req.pk or 0),
        "trip_id": int(trip_row.pk or 0),
        "trip_title": str(trip_row.title or ""),
        "requester_username": str(getattr(requester, "username", "") or ""),
        "requester_display_name": str(display_name or ""),
        "message": str(req.message or ""),
        "status": str(req.status or ""),
        "created_at": req.created_at.isoformat(),
        "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
    }


@require_GET
def manage_trip_api_view(request: HttpRequest, trip_id: int) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()

    trip_row = (
        Trip.objects.select_related("host", "host__account_profile")
        .filter(pk=trip_id, host=request.user)
        .first()
    )
    if trip_row is None:
        return _json_error("Trip not found or you are not the host.", status=404)

    approved_reqs = list(
        EnrollmentRequest.objects.select_related("requester", "requester__account_profile")
        .filter(trip=trip_row, status=EnrollmentRequest.STATUS_APPROVED)
        .order_by("-updated_at", "-pk")
    )
    all_reqs = list(
        EnrollmentRequest.objects.select_related("requester", "requester__account_profile")
        .filter(trip=trip_row)
        .order_by("-created_at", "-pk")
    )

    participants = [_manage_trip_participant_payload(r) for r in approved_reqs]
    applications = [_manage_trip_application_payload(r, trip_row) for r in all_reqs]

    total_seats = trip_row.total_seats
    if total_seats is not None:
        spots_left = max(0, int(total_seats) - len(participants))
        booking_status = "full" if spots_left == 0 else "open"
    else:
        spots_left = None
        booking_status = "open"

    trip_data = _serialize_trip_for_frontend(trip_row)
    trip_data["can_manage"] = True
    trip_data["booking_status"] = booking_status
    trip_data["access_type"] = str(trip_data.get("access_type") or ("apply" if applications else "open"))
    trip_data["participants_count"] = len(participants)
    trip_data["applications_count"] = sum(1 for a in applications if a["status"] == "pending")
    if spots_left is not None:
        trip_data["spots_left"] = spots_left

    return JsonResponse({"ok": True, "trip": trip_data, "participants": participants, "applications": applications})


@require_POST
def manage_trip_booking_status_view(request: HttpRequest, trip_id: int) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()
    trip_row = Trip.objects.filter(pk=trip_id, host=request.user).first()
    if trip_row is None:
        return _json_error("Trip not found.", status=404)
    payload = _request_payload(request)
    new_status = str(payload.get("status", "") or "").strip().lower()
    if new_status in TRIP_BOOKING_STATUS_VALUES:
        draft = dict(
            cast(Mapping[str, object], trip_row.draft_form_data)
            if isinstance(trip_row.draft_form_data, Mapping)
            else {}
        )
        draft["booking_status"] = new_status
        trip_row.draft_form_data = draft
        trip_row.save(update_fields=["draft_form_data"])
    return JsonResponse({"ok": True})


@require_POST
def manage_trip_remove_participant_view(request: HttpRequest, trip_id: int, participant_id: int) -> JsonResponse:
    """Remove a confirmed participant by setting their enrollment to denied."""
    if not request.user.is_authenticated:
        return _member_only_error()
    trip_row = Trip.objects.filter(pk=trip_id, host=request.user).first()
    if trip_row is None:
        return _json_error("Trip not found.", status=404)
    req = EnrollmentRequest.objects.filter(pk=participant_id, trip=trip_row).first()
    if req is None:
        return _json_error("Participant not found.", status=404)
    req.status = EnrollmentRequest.STATUS_DENIED
    req.reviewed_by = request.user  # type: ignore[assignment]
    req.reviewed_at = timezone.now()
    req.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    return JsonResponse({"ok": True})


@require_POST
def manage_trip_cancel_view(request: HttpRequest, trip_id: int) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()
    trip_row = Trip.objects.filter(pk=trip_id, host=request.user).first()
    if trip_row is None:
        return _json_error("Trip not found.", status=404)
    # Unpublish the trip as the closest available cancellation signal.
    # A dedicated status/cancelled field is tracked in the backlog.
    trip_row.is_published = False
    trip_row.save(update_fields=["is_published", "updated_at"])
    return JsonResponse({"ok": True})


@require_POST
def manage_trip_message_view(request: HttpRequest, trip_id: int) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()
    trip_row = Trip.objects.filter(pk=trip_id, host=request.user).first()
    if trip_row is None:
        return _json_error("Trip not found.", status=404)
    message = str(_request_payload(request).get("message") or "").strip()
    if not message:
        return _json_error("Message is required.", status=400)

    approved_reqs = list(
        EnrollmentRequest.objects.select_related("requester")
        .filter(trip=trip_row, status=EnrollmentRequest.STATUS_APPROVED)
        .order_by("requester_id", "pk")
    )
    if not approved_reqs:
        return _json_error("There are no confirmed participants to message.", status=400)

    sent_count = 0
    seen_requester_ids: set[int] = set()
    for req in approved_reqs:
        requester = req.requester
        requester_id = int(getattr(requester, "pk", 0) or 0)
        if requester_id <= 0 or requester_id in seen_requester_ids:
            continue
        seen_requester_ids.add(requester_id)
        thread, _created, outcome = get_or_create_dm_thread_for_members(
            member=request.user,
            other_member=requester,
        )
        if outcome not in ("created", "existing") or thread is None:
            continue
        _message, send_outcome = send_dm_message(
            thread=thread,
            sender=request.user,
            body=message,
        )
        if send_outcome == "sent":
            sent_count += 1

    if sent_count == 0:
        return _json_error("Could not deliver the message to participants.", status=400)

    return JsonResponse({"ok": True, "sent_count": sent_count})


@require_POST
def trip_remove_participant_view(request: HttpRequest, trip_id: int, user_id: int) -> JsonResponse:
    """Remove a confirmed participant by user PK.

    ApplicationManager sends removeTarget.user_id (the traveler's User PK),
    not the enrollment-request PK, so the lookup differs from the older
    manage_trip_remove_participant_view which used enrollment PK.
    """
    if not request.user.is_authenticated:
        return _member_only_error()
    trip_row = Trip.objects.filter(pk=trip_id, host=request.user).first()
    if trip_row is None:
        return _json_error("Trip not found.", status=404)
    req = (
        EnrollmentRequest.objects.filter(
            trip=trip_row,
            requester_id=user_id,
            status=EnrollmentRequest.STATUS_APPROVED,
        )
        .first()
    )
    if req is None:
        return _json_error("Participant not found.", status=404)
    req.status = EnrollmentRequest.STATUS_DENIED
    req.reviewed_by = request.user  # type: ignore[assignment]
    req.reviewed_at = timezone.now()
    req.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    return JsonResponse({"ok": True})


@require_GET
def notifications_api_view(request: HttpRequest) -> JsonResponse:
    """Return real activity events shaped for Navbar's notification dropdown."""
    if not request.user.is_authenticated:
        return JsonResponse({"ok": True, "notifications": [], "unread_count": 0})

    from activity.models import build_activity_payload_for_member

    payload = build_activity_payload_for_member(request.user, activity_filter="all", limit=20)
    items = payload.get("items", [])

    _GROUP_ICON: dict[str, str] = {
        "follows": "👤",
        "enrollment": "✅",
        "comments": "💬",
        "replies": "💬",
        "bookmarks": "🔖",
        "reviews": "⭐",
        "review_prompt": "⭐",
    }

    def _rel_time(occurred_at: object) -> str:
        if not occurred_at:
            return ""
        try:
            from django.utils.timezone import now as _now
            diff = _now() - cast(datetime, occurred_at)
            secs = int(diff.total_seconds())
            if secs < 60:
                return "Just now"
            if secs < 3600:
                return f"{secs // 60}m ago"
            if secs < 86400:
                return f"{secs // 3600}h ago"
            return f"{secs // 86400}d ago"
        except Exception:
            return ""

    notifications: list[dict[str, object]] = []
    for item in items:
        group = str(item.get("group", "") or "")
        action = str(item.get("action", "") or "")
        actor = str(item.get("actor_username", "") or "")
        target = str(item.get("target_label", "") or "")
        message = f"@{actor} {action}" if actor else action
        if target and target not in message:
            message = f"{message}: {target}"
        notifications.append({
            "id": str(item.get("id", "")),
            "icon": _GROUP_ICON.get(group, "🔔"),
            "message": message,
            "time": _rel_time(item.get("occurred_at")),
            "unread": True,
        })

    return JsonResponse({
        "ok": True,
        "notifications": notifications,
        "unread_count": len(notifications),
    })


@require_GET
def google_oauth_start_view(request: HttpRequest) -> HttpResponse:
    """Redirect the browser to Google's OAuth consent screen."""
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        return HttpResponse("Google OAuth is not configured.", status=501)

    state = secrets.token_urlsafe(24)
    request.session["google_oauth_state"] = state
    next_url = request.GET.get("next", "/")
    request.session["google_oauth_next"] = next_url

    base_url = getattr(settings, "BASE_URL", "").rstrip("/")
    redirect_uri = f"{base_url}/frontend-api/auth/google/callback/"

    params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    })
    return HttpResponse(
        status=302,
        headers={"Location": f"https://accounts.google.com/o/oauth2/v2/auth?{params}"},
    )


def google_oauth_callback_view(request: HttpRequest) -> HttpResponse:
    """Exchange code for tokens, resolve/create the user, log them in."""
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "").strip()
    client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return HttpResponse("Google OAuth is not configured.", status=501)

    error = request.GET.get("error", "")
    if error:
        return HttpResponse(f"Google OAuth error: {error}", status=400)

    code = request.GET.get("code", "")
    state = request.GET.get("state", "")
    stored_state = request.session.pop("google_oauth_state", "")
    next_url = request.session.pop("google_oauth_next", "/")

    if not code or not state or state != stored_state:
        return HttpResponse("OAuth state mismatch. Please try again.", status=400)

    base_url = getattr(settings, "BASE_URL", "").rstrip("/")
    redirect_uri = f"{base_url}/frontend-api/auth/google/callback/"

    # Exchange code for tokens
    token_data = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode()
    try:
        token_req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=token_data,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(token_req, timeout=10) as resp:
            token_json = json.loads(resp.read())
    except Exception as exc:
        return HttpResponse(f"Token exchange failed: {exc}", status=502)

    id_token_str = token_json.get("id_token", "")
    if not id_token_str:
        return HttpResponse("No id_token in Google response.", status=502)

    # Decode id_token payload (no signature verification needed — we just got it directly from Google over TLS)
    try:
        payload_b64 = id_token_str.split(".")[1]
        # Fix padding
        payload_b64 += "=" * (-len(payload_b64) % 4)
        import base64
        userinfo = json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception as exc:
        return HttpResponse(f"Failed to decode id_token: {exc}", status=502)

    google_email = str(userinfo.get("email", "")).strip().lower()
    google_name = str(userinfo.get("name", "")).strip()
    google_given = str(userinfo.get("given_name", "")).strip()
    google_family = str(userinfo.get("family_name", "")).strip()

    if not google_email:
        return HttpResponse("Google did not return an email address.", status=502)

    # Find or create user by email
    user = UserModel.objects.filter(email__iexact=google_email).first()
    if user is None:
        # Derive a unique username from the email local part
        base_username = re.sub(r"[^a-z0-9_]", "", google_email.split("@")[0].lower()) or "user"
        username = base_username
        suffix = 1
        while UserModel.objects.filter(username=username).exists():
            username = f"{base_username}{suffix}"
            suffix += 1
        user = UserModel.objects.create_user(  # type: ignore[union-attr]
            username=username,
            email=google_email,
            password=None,  # unusable password — login only via Google
            first_name=google_given or google_name.split()[0] if google_name else "",
            last_name=google_family,
        )
        ensure_profile(user)
    elif google_given and not getattr(user, "first_name", "").strip():
        user.first_name = google_given  # type: ignore[assignment]
        user.last_name = google_family  # type: ignore[assignment]
        user.save(update_fields=["first_name", "last_name"])

    # Log the user in — Django sessions
    login(request, cast(Any, user), backend="django.contrib.auth.backends.ModelBackend")

    # Redirect back into the SPA
    safe_next = next_url if next_url.startswith("/") else "/"
    return HttpResponse(status=302, headers={"Location": safe_next})


@require_GET
def users_search_api_view(request: HttpRequest) -> JsonResponse:
    """Search users by username or display name (used by CreateTrip invite flow)."""
    q = request.GET.get("q", "").strip()
    if not q or len(q) < 2:
        return JsonResponse({"ok": True, "users": []})
    qs = (
        UserModel.objects.filter(username__icontains=q)
        | UserModel.objects.filter(first_name__icontains=q)
        | UserModel.objects.filter(last_name__icontains=q)
    )
    users: list[dict[str, object]] = []
    for u in qs.distinct()[:10]:
        profile = ensure_profile(u)
        users.append({
            "username": str(u.username),
            "display_name": str(profile.effective_display_name),
        })
    return JsonResponse({"ok": True, "users": users})


@require_http_methods(["POST"])
def trip_review_submit_api_view(request: HttpRequest, trip_id: int) -> JsonResponse:
    """Submit a review for a trip. Creates or updates the member's review."""
    if not request.user.is_authenticated:
        return _member_only_error()

    payload = _request_payload(request)
    rating = payload.get("rating")
    body = payload.get("body", "")
    headline = payload.get("headline", "")

    review, outcome, _target = submit_review(
        member=request.user,
        target_type="trip",
        target_id=trip_id,
        rating=rating,
        headline=headline,
        body=body,
    )

    if outcome in ("created", "updated") and review is not None:
        return JsonResponse({
            "ok": True,
            "outcome": outcome,
            "review": {
                "id": review.pk,
                "rating": int(review.rating or 0),
                "headline": review.headline,
                "body": review.body,
                "author": str(getattr(review.author, "username", "")),
                "created_at": review.created_at.isoformat() if review.created_at else None,
            },
        })

    _error_messages: dict[str, str] = {
        "member-required": "You must be logged in to submit a review.",
        "invalid-member": "Invalid user account.",
        "invalid-target-type": "Invalid review target.",
        "target-not-found": "Trip not found.",
        "invalid-rating": "Rating must be between 1 and 5.",
        "too-long-headline": "Headline is too long.",
        "empty-body": "Review body cannot be empty.",
        "too-long-body": "Review is too long.",
    }
    return _json_error(_error_messages.get(str(outcome), "Could not submit review."), status=400)


@require_GET
def reviews_list_api_view(request: HttpRequest) -> JsonResponse:
    """List reviews written by (`?author=me`) or received on items owned by
    (`?recipient=me`) the current user. Used by the Dashboard Reviews hub."""
    if not request.user.is_authenticated:
        return _member_only_error()

    from blogs.models import Blog
    from reviews.models import Review

    author_filter = str(request.GET.get("author", "") or "").strip().lower()
    recipient_filter = str(request.GET.get("recipient", "") or "").strip().lower()

    viewer = request.user
    viewer_id = int(getattr(viewer, "pk", 0) or 0)
    viewer_identity = _member_identity_payload(viewer)
    viewer_display_name = viewer_identity["display_name"]

    if author_filter == "me":
        review_rows = list(
            Review.objects.select_related("author", "author__account_profile")
            .filter(author=viewer)
            .order_by("-created_at", "-id")
        )
    elif recipient_filter == "me":
        trip_ids_owned = [
            str(pk) for pk in Trip.objects.filter(host=viewer).values_list("pk", flat=True)
        ]
        blog_slugs_owned = list(
            Blog.objects.filter(author=viewer).values_list("slug", flat=True)
        )
        qs = Review.objects.select_related("author", "author__account_profile")
        filter_q = Q()
        if trip_ids_owned:
            filter_q |= Q(target_type=Review.TARGET_TRIP, target_key__in=trip_ids_owned)
        if blog_slugs_owned:
            filter_q |= Q(target_type=Review.TARGET_BLOG, target_key__in=blog_slugs_owned)
        review_rows = list(qs.filter(filter_q).order_by("-created_at", "-id")) if filter_q else []
    else:
        return _json_error("Specify ?author=me or ?recipient=me.", status=400)

    author_usernames = sorted({
        str(getattr(review.author, "username", "") or "").strip()
        for review in review_rows
        if getattr(review.author, "username", "")
    })
    author_identity_map = _identity_map_for_usernames(author_usernames)

    target_owner_identity_cache: dict[tuple[str, str], str] = {}

    def _target_owner_display_name(review: Review) -> str:
        cache_key = (review.target_type, review.target_key)
        if cache_key in target_owner_identity_cache:
            return target_owner_identity_cache[cache_key]

        owner_display_name = ""
        if review.target_type == Review.TARGET_TRIP and str(review.target_key or "").isdigit():
            trip_row = Trip.objects.select_related("host", "host__account_profile").filter(pk=int(review.target_key)).first()
            if trip_row is not None and trip_row.host is not None:
                owner_display_name = _member_identity_payload(trip_row.host)["display_name"]
        elif review.target_type == Review.TARGET_BLOG:
            blog_row = Blog.objects.select_related("author", "author__account_profile").filter(slug=review.target_key).first()
            if blog_row is not None and blog_row.author is not None:
                owner_display_name = _member_identity_payload(blog_row.author)["display_name"]

        target_owner_identity_cache[cache_key] = owner_display_name
        return owner_display_name

    reviews_out: list[dict[str, object]] = []
    for review in review_rows:
        author_username = str(getattr(review.author, "username", "") or "").strip()
        reviewer_name = author_identity_map.get(author_username, {}).get("display_name", author_username or "Tapne member")

        if recipient_filter == "me":
            reviewee_name = viewer_display_name
        else:
            reviewee_name = _target_owner_display_name(review)

        body_text = str(review.body or "").strip()
        headline_text = str(review.headline or "").strip()
        combined_text = f"{headline_text}\n\n{body_text}".strip() if headline_text else body_text

        reviews_out.append({
            "id": int(review.pk or 0),
            "reviewer_name": reviewer_name,
            "reviewee_name": reviewee_name,
            "rating": int(review.rating or 0),
            "text": combined_text,
            "trip_title": str(review.target_label or "").strip(),
            "created_at": review.created_at.isoformat() if review.created_at else "",
            "is_mine": int(getattr(review, "author_id", 0) or 0) == viewer_id,
        })

    return JsonResponse({"ok": True, "reviews": reviews_out})


@require_http_methods(["POST"])
def dm_start_thread_api_view(request: HttpRequest) -> JsonResponse:
    """Get or create a DM thread between the current user and another user.

    Request body: { "host_username": <str> }  OR  { "host_id": <int> }
    Response:     { "ok": true, "thread_id": <int> }
    """
    if not request.user.is_authenticated:
        return _member_only_error()

    payload = _request_payload(request)

    host_username = str(payload.get("host_username") or "").strip()
    if host_username:
        other_user = UserModel.objects.filter(username=host_username).first()
    else:
        host_id_raw = payload.get("host_id")
        try:
            host_id = int(str(host_id_raw or 0))
        except (TypeError, ValueError):
            return _json_error("host_username or host_id is required.", status=400)
        if host_id <= 0:
            return _json_error("host_username or host_id is required.", status=400)
        other_user = UserModel.objects.filter(pk=host_id).first()

    if other_user is None:
        return _json_error("Host not found.", status=404)

    thread, _created, outcome = get_or_create_dm_thread_for_members(
        member=request.user,
        other_member=other_user,
    )

    if outcome in ("created", "existing") and thread is not None:
        return JsonResponse({"ok": True, "thread_id": thread.pk})

    _outcome_errors: dict[str, str] = {
        "member-required": "You must be logged in.",
        "invalid-member": "Invalid user account.",
        "self-thread-blocked": "You cannot send a message to yourself.",
    }
    return _json_error(_outcome_errors.get(str(outcome), "Could not start conversation."), status=400)


# ── User Search ───────────────────────────────────────────────────────────────


@require_GET
def user_search_api_view(request: HttpRequest) -> JsonResponse:
    q = str(request.GET.get("q", "") or "").strip()
    if len(q) < 2:
        return JsonResponse({"ok": True, "users": []})
    users = (
        UserModel.objects.select_related("account_profile")
        .filter(Q(username__icontains=q) | Q(account_profile__display_name__icontains=q))
        .distinct()[:8]
    )
    return JsonResponse({"ok": True, "users": [_member_identity_payload(u) for u in users]})


# ── OTP Signup ────────────────────────────────────────────────────────────────


@require_POST
def send_otp_api_view(request: HttpRequest) -> JsonResponse:
    from runtime.models import check_rate_limit
    from email_validator import EmailNotValidError, validate_email as _validate_email

    payload = _request_payload(request)
    email = _normalize_string(payload.get("email", ""))

    if not email or "@" not in email:
        return _json_error("A valid email address is required.")

    try:
        normalized_email = _validate_email(email, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        return _json_error(str(exc), extra={"errors": {"email": [str(exc)]}})

    if UserModel.objects.filter(email__iexact=normalized_email).exists():
        return _json_error(
            "An account with this email already exists.",
            extra={"errors": {"email": ["An account with this email already exists."]}},
        )

    rate = check_rate_limit(scope="otp-send", identifier=normalized_email, limit=3, window_seconds=600)
    if not rate["allowed"]:
        return _json_error("Too many requests. Please wait before requesting another code.", status=429)

    otp_code = _generate_otp()
    cache.set(_otp_cache_key(normalized_email), {"otp": otp_code, "attempts": 0}, timeout=OTP_CACHE_TTL)

    try:
        send_mail(
            subject="Your Tapne verification code",
            message=(
                f"Your Tapne verification code is: {otp_code}\n\n"
                "This code expires in 10 minutes. Do not share it with anyone."
            ),
            from_email=None,  # uses DEFAULT_FROM_EMAIL from settings
            recipient_list=[normalized_email],
            fail_silently=True,
        )
    except Exception:
        pass  # OTP is stored — delivery failure is non-fatal

    return JsonResponse({"ok": True, "email": normalized_email})


@require_POST
def verify_otp_api_view(request: HttpRequest) -> JsonResponse:
    from email_validator import EmailNotValidError, validate_email as _validate_email

    payload = _request_payload(request)
    email = _normalize_string(payload.get("email", ""))
    otp = _normalize_string(payload.get("otp", ""))
    first_name = _normalize_string(payload.get("first_name", ""))
    password = _normalize_string(payload.get("password", ""))

    if not email or not otp:
        return _json_error("Email and verification code are required.")
    if not password:
        return _json_error("Password is required.")

    try:
        normalized_email = _validate_email(email, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        return _json_error(str(exc))

    cache_key = _otp_cache_key(normalized_email)
    stored = cache.get(cache_key)

    if stored is None:
        return _json_error("Verification code has expired. Please request a new one.", status=400)

    attempts = int(stored.get("attempts", 0)) + 1
    if attempts > OTP_MAX_ATTEMPTS:
        cache.delete(cache_key)
        return _json_error("Too many incorrect attempts. Please request a new code.", status=400)

    if stored.get("otp") != otp:
        cache.set(cache_key, {"otp": stored["otp"], "attempts": attempts}, timeout=OTP_CACHE_TTL)
        remaining = OTP_MAX_ATTEMPTS - attempts
        return _json_error(
            f"Incorrect code. {remaining} attempt{'s' if remaining != 1 else ''} remaining.",
            status=400,
        )

    cache.delete(cache_key)

    # Guard against race — check email still available
    if UserModel.objects.filter(email__iexact=normalized_email).exists():
        return _json_error(
            "An account with this email already exists.",
            extra={"errors": {"email": ["An account with this email already exists."]}},
        )

    if len(password) < 8:
        return _json_error("Password must be at least 8 characters.", extra={"errors": {"password": ["Password must be at least 8 characters."]}})

    username = _generate_username_from_email(normalized_email)
    try:
        user = UserModel.objects.create_user(
            username=username,
            email=normalized_email,
            password=password,
            first_name=first_name,
        )
    except Exception:
        return _json_error("Account creation failed. Please try again.")

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


# ── Trip Review ───────────────────────────────────────────────────────────────


@require_POST
def trip_review_create_api_view(request: HttpRequest, trip_id: int) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()

    trip = Trip.objects.filter(pk=trip_id, is_published=True).first()
    if trip is None:
        return _json_error("Trip not found.", status=404)

    from reviews.models import Review

    payload = _request_payload(request)
    raw_rating = _normalize_optional_int(payload.get("rating"))
    rating = max(1, min(5, raw_rating if raw_rating is not None else 5))
    body = " ".join(str(payload.get("body", "") or "").strip().split())
    headline = " ".join(str(payload.get("headline", "") or "").strip().split())

    if not body:
        return _json_error("Review body is required.", extra={"errors": {"body": ["Required."]}})

    review, created = Review.objects.update_or_create(
        author=request.user,
        target_type=Review.TARGET_TRIP,
        target_key=str(trip_id),
        defaults={
            "rating": rating,
            "body": body,
            "headline": headline,
            "target_label": str(trip.title or "").strip(),
            "target_url": f"/trips/{trip_id}/",
        },
    )
    return JsonResponse(
        {
            "ok": True,
            "created": created,
            "review": {
                "id": int(review.pk or 0),
                "rating": review.rating,
                "body": review.body,
                "headline": review.headline,
            },
        },
        status=201 if created else 200,
    )


# ── Blog / Experience Create ───────────────────────────────────────────────────


def blog_create_api_view(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()

    from blogs.models import Blog
    from django.utils.text import slugify

    payload = _request_payload(request)
    title = _normalize_string(payload.get("title", ""))
    if not title:
        return _json_error("Title is required.", extra={"errors": {"title": ["Required."]}})

    base_slug = slugify(title)[:150] or "experience"
    slug = base_slug
    counter = 1
    while Blog.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1

    blog = Blog(
        author=request.user,
        slug=slug,
        title=title,
        excerpt=_normalize_string(payload.get("short_description", "")),
        body=str(payload.get("body", "") or "").strip(),
        cover_image_url=str(payload.get("cover_image_url", "") or "").strip(),
        location=_normalize_string(payload.get("location", "")),
        tags=_normalize_string_list(payload.get("tags"), max_items=12, max_length=40),
        is_published=True,
    )
    blog.save()
    return JsonResponse({"ok": True, "blog": blog.to_blog_data()}, status=201)


# ── Account Management ────────────────────────────────────────────────────────


@require_POST
def account_deactivate_api_view(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()

    user = cast(Any, request.user)
    logout(request)
    user.is_active = False
    user.save(update_fields=["is_active"])
    return JsonResponse({"ok": True, "deactivated": True})


@require_POST
def account_delete_api_view(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return _member_only_error()

    user = request.user
    logout(request)
    user.delete()
    return JsonResponse({"ok": True, "deleted": True})
