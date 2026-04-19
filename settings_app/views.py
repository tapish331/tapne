from __future__ import annotations

import json
from typing import Final, cast

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from .models import ensure_member_settings, update_member_appearance

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
        print(f"[settings][verbose] {message}", flush=True)


@login_required(login_url="/")
@require_http_methods(["POST"])
def settings_appearance_update_view(request: HttpRequest) -> JsonResponse:
    """JSON-only endpoint for live theme/appearance updates from the SPA.

    The Django-rendered settings page (`settings_index_view`) was retired in
    the SPA cutover — the SPA handles the full settings UI via
    `/frontend-api/settings/`. Only the live appearance write remains here
    because it's a lightweight cookie-backed AJAX call independent of the
    `/frontend-api/*` session plumbing.
    """
    settings_row, _created = ensure_member_settings(request.user)
    if settings_row is None:
        return JsonResponse({"ok": False, "error": "invalid-member"}, status=400)

    payload: dict[str, object] = {}
    content_type = str(request.headers.get("Content-Type", "")).lower()
    if "application/json" in content_type:
        try:
            parsed_payload_obj: object = json.loads(request.body.decode("utf-8") or "{}")
            if isinstance(parsed_payload_obj, dict):
                parsed_payload_map = cast(dict[object, object], parsed_payload_obj)
                normalized_payload: dict[str, object] = {}
                for raw_key, raw_value in parsed_payload_map.items():
                    if isinstance(raw_key, str):
                        normalized_payload[raw_key] = raw_value
                payload = normalized_payload
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}

    submitted_theme_preference = payload.get(
        "theme_preference",
        request.POST.get("theme_preference", settings_row.theme_preference),
    )

    updated_row, outcome = update_member_appearance(
        member=request.user,
        theme_preference=submitted_theme_preference,
    )
    if updated_row is None:
        return JsonResponse({"ok": False, "error": "invalid-member"}, status=400)

    _vprint(
        request,
        "Appearance persisted for @{username}; outcome={outcome}; theme_preference={theme_preference}".format(
            username=request.user.username,
            outcome=outcome,
            theme_preference=updated_row.theme_preference,
        ),
    )

    return JsonResponse(
        {
            "ok": True,
            "outcome": outcome,
            "theme_preference": updated_row.theme_preference,
        }
    )
