from __future__ import annotations

from typing import Final

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from .models import (
    build_runtime_health_snapshot,
    feed_cache_key_for_user,
    get_buffered_runtime_tasks,
    get_cached_payload,
    search_cache_key_for_user,
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
        print(f"[runtime][verbose] {message}", flush=True)


@require_GET
def runtime_health_view(request: HttpRequest) -> JsonResponse:
    snapshot = build_runtime_health_snapshot()
    _vprint(
        request,
        (
            "Runtime health check cache_ok={cache_ok}; redis_configured={redis_configured}; "
            "broker_configured={broker_configured}; buffered_task_count={buffered_task_count}; "
            "idempotency_rows={active_idempotency_records}; counters={persisted_counter_rows}"
        ).format(
            cache_ok=snapshot["cache_ok"],
            redis_configured=snapshot["redis_configured"],
            broker_configured=snapshot["broker_configured"],
            buffered_task_count=snapshot["buffered_task_count"],
            active_idempotency_records=snapshot["active_idempotency_records"],
            persisted_counter_rows=snapshot["persisted_counter_rows"],
        ),
    )
    return JsonResponse(snapshot)


@login_required(login_url="accounts:login")
@require_GET
def runtime_cache_preview_view(request: HttpRequest) -> JsonResponse:
    query = str(request.GET.get("q", "")).strip()
    result_type = str(request.GET.get("type", "all") or "all").strip().lower() or "all"

    feed_key = feed_cache_key_for_user(request.user)
    search_key = search_cache_key_for_user(
        request.user,
        query=query,
        result_type=result_type,
    )
    feed_payload = get_cached_payload(feed_key)
    search_payload = get_cached_payload(search_key)
    buffered_tasks = get_buffered_runtime_tasks(limit=10)
    feed_hit = feed_payload is not None
    search_hit = search_payload is not None
    buffered_tasks_count = len(buffered_tasks)

    response_payload: dict[str, object] = {
        "feed_cache_key": feed_key,
        "feed_cache_hit": feed_hit,
        "search_cache_key": search_key,
        "search_cache_hit": search_hit,
        "result_type": result_type,
        "query": query,
        "buffered_tasks_count": buffered_tasks_count,
    }

    _vprint(
        request,
        (
            "Cache preview for @{username}; feed_hit={feed_hit}; search_hit={search_hit}; "
            "query='{query}'; type={result_type}; buffered_tasks={buffered_tasks_count}"
        ).format(
            username=request.user.username,
            feed_hit=feed_hit,
            search_hit=search_hit,
            query=query,
            result_type=result_type,
            buffered_tasks_count=buffered_tasks_count,
        ),
    )
    return JsonResponse(response_payload)
