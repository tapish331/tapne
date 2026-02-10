from __future__ import annotations

from typing import Final

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .models import build_activity_payload_for_member, normalize_activity_filter

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
        print(f"[activity][verbose] {message}", flush=True)


def _parse_limit(raw_limit: object, *, default: int = 80) -> int:
    raw_text = str(raw_limit or "").strip()
    if not raw_text:
        return default

    if raw_text.startswith("+"):
        raw_text = raw_text[1:]
    if not raw_text.isdigit():
        return default

    parsed_limit = int(raw_text)
    return max(5, min(parsed_limit, 250))


@login_required(login_url="accounts:login")
@require_http_methods(["GET"])
def activity_index_view(request: HttpRequest) -> HttpResponse:
    requested_filter = request.GET.get("type", "all")
    active_filter = normalize_activity_filter(requested_filter)
    if str(requested_filter or "").strip().lower() != active_filter:
        _vprint(
            request,
            (
                "Unsupported activity filter '{requested}' requested. "
                "Falling back to '{active}'."
            ).format(
                requested=requested_filter,
                active=active_filter,
            ),
        )

    limit = _parse_limit(request.GET.get("limit"), default=80)
    payload = build_activity_payload_for_member(
        request.user,
        activity_filter=active_filter,
        limit=limit,
    )
    _vprint(
        request,
        (
            "Activity page rendered for @{username}; filter={activity_filter}; "
            "count={item_count}; totals={counts}"
        ).format(
            username=request.user.username,
            activity_filter=payload["active_filter"],
            item_count=len(payload["items"]),
            counts=payload["counts"],
        ),
    )

    context: dict[str, object] = {
        "activity_items": payload["items"],
        "activity_counts": payload["counts"],
        "activity_mode": payload["mode"],
        "activity_reason": payload["reason"],
        "activity_filter": payload["active_filter"],
    }
    return render(request, "pages/activity/index.html", context)
