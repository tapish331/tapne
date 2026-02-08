from __future__ import annotations

from typing import Final

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .models import build_search_payload_for_user, normalize_search_result_type

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
        print(f"[search][verbose] {message}", flush=True)


def search_page(request: HttpRequest) -> HttpResponse:
    raw_query = str(request.GET.get("q", ""))
    query = raw_query.strip()

    raw_result_type = str(request.GET.get("type", "all"))
    result_type = normalize_search_result_type(raw_result_type)
    if raw_result_type.strip().lower() != result_type:
        _vprint(
            request,
            f"Received unsupported search type '{raw_result_type}'. Falling back to 'all'.",
        )

    viewer_state = "member" if request.user.is_authenticated else "guest"
    _vprint(
        request,
        (
            "Rendering search page for viewer_state={viewer_state}, query='{query}', type={result_type}"
            .format(
                viewer_state=viewer_state,
                query=query,
                result_type=result_type,
            )
        ),
    )

    payload = build_search_payload_for_user(
        request.user,
        query=query,
        result_type=result_type,
    )
    _vprint(
        request,
        (
            "Search mode={mode}; reason={reason}; counts trips={trip_count}, profiles={profile_count}, blogs={blog_count}"
            .format(
                mode=payload["mode"],
                reason=payload["reason"],
                trip_count=len(payload["trips"]),
                profile_count=len(payload["profiles"]),
                blog_count=len(payload["blogs"]),
            )
        ),
    )

    context: dict[str, object] = {
        "trips": payload["trips"],
        "profiles": payload["profiles"],
        "blogs": payload["blogs"],
        "search_mode": payload["mode"],
        "search_reason": payload["reason"],
        "search_query": query,
        "active_type": payload["result_type"],
        "has_query": bool(query),
    }
    return render(request, "pages/search.html", context)
