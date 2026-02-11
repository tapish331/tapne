from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Final, Literal, TypedDict, cast

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, models, transaction
from django.utils import timezone

RuntimeRateLimitOutcome = Literal["allowed", "blocked"]
RuntimeIdempotencyOutcome = Literal["reserved", "duplicate", "invalid"]
RuntimeCounterSnapshotOutcome = Literal["created", "updated"]
RuntimeTaskQueueMode = Literal["broker-configured", "buffered-local"]

DEFAULT_FEED_CACHE_TTL_SECONDS: Final[int] = 180
DEFAULT_SEARCH_CACHE_TTL_SECONDS: Final[int] = 120
DEFAULT_RATE_LIMIT_REQUESTS: Final[int] = 40
DEFAULT_RATE_LIMIT_WINDOW_SECONDS: Final[int] = 60
DEFAULT_IDEMPOTENCY_TTL_SECONDS: Final[int] = 900
DEFAULT_COUNTER_TTL_SECONDS: Final[int] = 86_400
DEFAULT_BROKER_SHELF_TTL_SECONDS: Final[int] = 3_600
DEFAULT_BROKER_SHELF_MAX_ITEMS: Final[int] = 200
MAX_CACHE_KEY_LENGTH: Final[int] = 230


class RuntimeRateLimitDecision(TypedDict):
    allowed: bool
    outcome: RuntimeRateLimitOutcome
    key: str
    limit: int
    current_count: int
    remaining: int
    retry_after_seconds: int


class RuntimeIdempotencyReservation(TypedDict):
    outcome: RuntimeIdempotencyOutcome
    scope: str
    idempotency_key: str
    record_id: int | None
    existing_status_code: int | None
    response_payload: dict[str, object] | None
    expires_at: datetime | None


class RuntimeTaskEnvelope(TypedDict):
    task_id: str
    task_name: str
    queue_name: str
    mode: RuntimeTaskQueueMode
    broker_url: str
    payload: dict[str, object]
    scheduled_for: str
    created_at: str


class RuntimeHealthSnapshot(TypedDict):
    checked_at: str
    cache_backend: str
    cache_ok: bool
    redis_configured: bool
    broker_configured: bool
    broker_url: str
    buffered_task_count: int
    active_idempotency_records: int
    persisted_counter_rows: int


class RuntimeIdempotencyRecord(models.Model):
    """
    Persistent idempotency ledger with expiry semantics.

    Redis keys are used as the fast path, while this table keeps a durable
    audit trail and makes behavior explicit in tests/admin/debug sessions.
    """

    scope = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=128)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="runtime_idempotency_records",
    )
    request_fingerprint = models.CharField(max_length=64, blank=True)
    status_code = models.PositiveSmallIntegerField(default=202)
    response_payload: models.JSONField[dict[str, object]] = models.JSONField(default=dict, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("scope", "idempotency_key"),
                name="runtime_idem_scope_key_uq",
            )
        ]
        indexes = [
            models.Index(fields=("scope", "owner", "created_at"), name="runtime_idem_scope_owner_idx"),
            models.Index(fields=("expires_at", "created_at"), name="runtime_idem_exp_created"),
        ]

    def __str__(self) -> str:
        return f"{self.scope}:{self.idempotency_key}"

    def is_expired(self, *, now: datetime | None = None) -> bool:
        comparison = now or timezone.now()
        return self.expires_at <= comparison


class RuntimeCounter(models.Model):
    """
    Durable snapshots of fast in-cache counters.
    """

    key = models.CharField(max_length=128, unique=True)
    value = models.BigIntegerField(default=0)
    source = models.CharField(max_length=24, default="cache")
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("key",)
        indexes = [
            models.Index(fields=("source", "updated_at"), name="runtime_counter_source_idx"),
            models.Index(fields=("expires_at",), name="runtime_counter_expires_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.key}={self.value}"


def _clean_key_part(value: object, *, fallback: str = "na") -> str:
    text = str(value or "").strip().lower()
    if not text:
        return fallback

    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", ".", ":"} else "-" for ch in text)
    normalized = cleaned.strip("-_.:")
    return normalized or fallback


def _normalize_idempotency_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > 96:
        text = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return _clean_key_part(text, fallback="")


def _normalize_payload(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        dict_value = cast(dict[object, object], value)
        normalized: dict[str, object] = {}
        for key, raw in dict_value.items():
            key_text = str(key or "").strip()
            if not key_text:
                continue
            normalized[key_text] = raw
        return normalized
    return {}


def _safe_positive_int(value: object, *, default: int) -> int:
    parsed: int
    if isinstance(value, bool):
        parsed = int(value)
    elif isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        parsed = int(value)
    elif isinstance(value, str):
        text = value.strip()
        try:
            parsed = int(text)
        except ValueError:
            parsed = int(default)
    else:
        parsed = int(default)
    return max(1, parsed)


def _as_dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []

    raw_items = cast(list[object], value)
    parsed: list[dict[str, object]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        dict_item = cast(dict[object, object], raw_item)
        parsed.append(_normalize_payload(dict_item))
    return parsed


def _read_runtime_seconds(setting_name: str, env_name: str, default: int) -> int:
    configured = getattr(settings, setting_name, None)
    if configured is None:
        configured = os.getenv(env_name)
    return _safe_positive_int(configured, default=default)


def _viewer_cache_segment(user: object) -> str:
    if bool(getattr(user, "is_authenticated", False)):
        user_id = int(getattr(user, "pk", 0) or 0)
        if user_id > 0:
            return f"user-{user_id}"
        username = _clean_key_part(getattr(user, "username", ""), fallback="member")
        return f"user-{username}"
    return "guest"


def build_runtime_cache_key(*parts: object) -> str:
    normalized_parts = [_clean_key_part(part) for part in parts if str(part or "").strip()]
    key = f"tapne:runtime:{':'.join(normalized_parts or ['default'])}"
    if len(key) <= MAX_CACHE_KEY_LENGTH:
        return key

    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    head = key[: MAX_CACHE_KEY_LENGTH - 21].rstrip(":")
    return f"{head}:{digest}"


def runtime_feed_cache_ttl_seconds() -> int:
    return _read_runtime_seconds(
        "TAPNE_RUNTIME_FEED_CACHE_TTL_SECONDS",
        "TAPNE_RUNTIME_FEED_CACHE_TTL_SECONDS",
        DEFAULT_FEED_CACHE_TTL_SECONDS,
    )


def runtime_search_cache_ttl_seconds() -> int:
    return _read_runtime_seconds(
        "TAPNE_RUNTIME_SEARCH_CACHE_TTL_SECONDS",
        "TAPNE_RUNTIME_SEARCH_CACHE_TTL_SECONDS",
        DEFAULT_SEARCH_CACHE_TTL_SECONDS,
    )


def runtime_rate_limit_window_seconds() -> int:
    return _read_runtime_seconds(
        "TAPNE_RUNTIME_RATE_LIMIT_WINDOW_SECONDS",
        "TAPNE_RUNTIME_RATE_LIMIT_WINDOW_SECONDS",
        DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
    )


def runtime_rate_limit_requests() -> int:
    return _read_runtime_seconds(
        "TAPNE_RUNTIME_RATE_LIMIT_REQUESTS",
        "TAPNE_RUNTIME_RATE_LIMIT_REQUESTS",
        DEFAULT_RATE_LIMIT_REQUESTS,
    )


def runtime_idempotency_ttl_seconds() -> int:
    return _read_runtime_seconds(
        "TAPNE_RUNTIME_IDEMPOTENCY_TTL_SECONDS",
        "TAPNE_RUNTIME_IDEMPOTENCY_TTL_SECONDS",
        DEFAULT_IDEMPOTENCY_TTL_SECONDS,
    )


def runtime_counter_ttl_seconds() -> int:
    return _read_runtime_seconds(
        "TAPNE_RUNTIME_COUNTER_TTL_SECONDS",
        "TAPNE_RUNTIME_COUNTER_TTL_SECONDS",
        DEFAULT_COUNTER_TTL_SECONDS,
    )


def runtime_broker_shelf_ttl_seconds() -> int:
    return _read_runtime_seconds(
        "TAPNE_RUNTIME_BROKER_SHELF_TTL_SECONDS",
        "TAPNE_RUNTIME_BROKER_SHELF_TTL_SECONDS",
        DEFAULT_BROKER_SHELF_TTL_SECONDS,
    )


def runtime_broker_shelf_max_items() -> int:
    return _read_runtime_seconds(
        "TAPNE_RUNTIME_BROKER_SHELF_MAX_ITEMS",
        "TAPNE_RUNTIME_BROKER_SHELF_MAX_ITEMS",
        DEFAULT_BROKER_SHELF_MAX_ITEMS,
    )


def runtime_broker_url() -> str:
    return str(
        os.getenv("CELERY_BROKER_URL", "").strip()
        or os.getenv("REDIS_URL", "").strip()
        or ""
    )


def runtime_result_backend_url() -> str:
    return str(
        os.getenv("CELERY_RESULT_BACKEND", "").strip()
        or os.getenv("REDIS_URL", "").strip()
        or ""
    )


def feed_cache_key_for_user(user: object, *, shelf: object = "home", version: object = "v1") -> str:
    return build_runtime_cache_key(
        "cache",
        "feed",
        version,
        shelf,
        _viewer_cache_segment(user),
    )


def search_cache_key_for_user(
    user: object,
    *,
    query: object = "",
    result_type: object = "all",
    version: object = "v1",
) -> str:
    normalized_query = str(query or "").strip().lower()
    query_digest = hashlib.sha1(normalized_query.encode("utf-8")).hexdigest()[:12] if normalized_query else "empty"
    return build_runtime_cache_key(
        "cache",
        "search",
        version,
        _clean_key_part(result_type, fallback="all"),
        _viewer_cache_segment(user),
        query_digest,
    )


def get_cached_payload(cache_key: object) -> dict[str, object] | None:
    key = str(cache_key or "").strip()
    if not key:
        return None

    try:
        payload = cache.get(key)
    except Exception:
        return None

    if isinstance(payload, dict):
        return cast(dict[str, object], payload)
    return None


def set_cached_payload(cache_key: object, payload: object, *, ttl_seconds: int) -> bool:
    key = str(cache_key or "").strip()
    if not key:
        return False

    normalized_payload = _normalize_payload(payload)
    if not normalized_payload:
        return False

    try:
        cache.set(key, normalized_payload, timeout=max(1, int(ttl_seconds)))
        return True
    except Exception:
        return False


def warm_feed_cache_for_user(
    user: object,
    *,
    payload: object,
    ttl_seconds: int | None = None,
    shelf: object = "home",
) -> str:
    cache_key = feed_cache_key_for_user(user, shelf=shelf)
    set_cached_payload(
        cache_key,
        payload,
        ttl_seconds=(ttl_seconds or runtime_feed_cache_ttl_seconds()),
    )
    return cache_key


def warm_search_cache_for_user(
    user: object,
    *,
    query: object,
    result_type: object,
    payload: object,
    ttl_seconds: int | None = None,
) -> str:
    cache_key = search_cache_key_for_user(user, query=query, result_type=result_type)
    set_cached_payload(
        cache_key,
        payload,
        ttl_seconds=(ttl_seconds or runtime_search_cache_ttl_seconds()),
    )
    return cache_key


def check_rate_limit(
    *,
    scope: object,
    identifier: object,
    limit: int | None = None,
    window_seconds: int | None = None,
) -> RuntimeRateLimitDecision:
    normalized_scope = _clean_key_part(scope, fallback="global")
    normalized_identifier = _clean_key_part(identifier, fallback="anonymous")
    effective_limit = _safe_positive_int(limit, default=runtime_rate_limit_requests())
    effective_window = _safe_positive_int(window_seconds, default=runtime_rate_limit_window_seconds())
    cache_key = build_runtime_cache_key("rate-limit", normalized_scope, normalized_identifier, effective_window)

    current_count = 1
    try:
        created = cache.add(cache_key, 1, timeout=effective_window)
        if created:
            current_count = 1
        else:
            try:
                current_count = int(cache.incr(cache_key))
            except Exception:
                previous_raw = cache.get(cache_key) or 0
                previous_count = int(previous_raw) if str(previous_raw).isdigit() else 0
                current_count = previous_count + 1
                cache.set(cache_key, current_count, timeout=effective_window)
    except Exception:
        current_count = 1

    allowed = current_count <= effective_limit
    return {
        "allowed": allowed,
        "outcome": "allowed" if allowed else "blocked",
        "key": cache_key,
        "limit": effective_limit,
        "current_count": current_count,
        "remaining": max(0, effective_limit - current_count),
        "retry_after_seconds": effective_window,
    }


def reserve_idempotency_key(
    *,
    scope: object,
    idempotency_key: object,
    owner: object | None = None,
    request_fingerprint: object = "",
    ttl_seconds: int | None = None,
) -> RuntimeIdempotencyReservation:
    normalized_scope = _clean_key_part(scope, fallback="")
    normalized_key = _normalize_idempotency_key(idempotency_key)
    if not normalized_scope or not normalized_key:
        return {
            "outcome": "invalid",
            "scope": normalized_scope,
            "idempotency_key": normalized_key,
            "record_id": None,
            "existing_status_code": None,
            "response_payload": None,
            "expires_at": None,
        }

    effective_ttl = _safe_positive_int(ttl_seconds, default=runtime_idempotency_ttl_seconds())
    now = timezone.now()
    expires_at = now + timedelta(seconds=effective_ttl)
    fingerprint = _normalize_idempotency_key(request_fingerprint)

    owner_instance: Any | None = None
    if owner is not None and bool(getattr(owner, "is_authenticated", False)):
        owner_id = int(getattr(owner, "pk", 0) or 0)
        if owner_id > 0:
            owner_instance = cast(Any, owner)

    with transaction.atomic():
        try:
            row, created = RuntimeIdempotencyRecord.objects.select_for_update().get_or_create(
                scope=normalized_scope,
                idempotency_key=normalized_key,
                defaults={
                    "owner": owner_instance,
                    "request_fingerprint": fingerprint,
                    "status_code": 202,
                    "response_payload": {},
                    "expires_at": expires_at,
                },
            )
        except IntegrityError:
            row = RuntimeIdempotencyRecord.objects.select_for_update().get(
                scope=normalized_scope,
                idempotency_key=normalized_key,
            )
            created = False

        if created:
            outcome: RuntimeIdempotencyOutcome = "reserved"
        elif row.is_expired(now=now):
            row.owner = owner_instance
            row.request_fingerprint = fingerprint
            row.status_code = 202
            row.response_payload = {}
            row.expires_at = expires_at
            row.save(
                update_fields=[
                    "owner",
                    "request_fingerprint",
                    "status_code",
                    "response_payload",
                    "expires_at",
                    "updated_at",
                ]
            )
            outcome = "reserved"
        else:
            outcome = "duplicate"

    # Keep a short-lived cache pointer for fast duplicate checks in hot paths.
    idempotency_cache_key = build_runtime_cache_key("idempotency", normalized_scope, normalized_key)
    try:
        cache.set(idempotency_cache_key, int(row.pk or 0), timeout=effective_ttl)
    except Exception:
        pass

    response_payload = row.response_payload if outcome == "duplicate" else None
    return {
        "outcome": outcome,
        "scope": normalized_scope,
        "idempotency_key": normalized_key,
        "record_id": int(row.pk or 0),
        "existing_status_code": int(row.status_code or 0) if outcome == "duplicate" else None,
        "response_payload": response_payload,
        "expires_at": row.expires_at,
    }


def finalize_idempotency_key(
    *,
    scope: object,
    idempotency_key: object,
    status_code: int,
    response_payload: object | None = None,
) -> RuntimeIdempotencyRecord | None:
    normalized_scope = _clean_key_part(scope, fallback="")
    normalized_key = _normalize_idempotency_key(idempotency_key)
    if not normalized_scope or not normalized_key:
        return None

    row = RuntimeIdempotencyRecord.objects.filter(
        scope=normalized_scope,
        idempotency_key=normalized_key,
    ).first()
    if row is None:
        return None

    row.status_code = max(100, min(599, int(status_code)))
    row.response_payload = _normalize_payload(response_payload)
    row.save(update_fields=["status_code", "response_payload", "updated_at"])
    return row


def purge_expired_idempotency_records(*, batch_size: int = 500) -> int:
    return RuntimeIdempotencyRecord.objects.filter(
        expires_at__lte=timezone.now()
    ).order_by("expires_at")[: max(1, int(batch_size))].delete()[0]


def increment_runtime_counter(
    counter_key: object,
    *,
    amount: int = 1,
    ttl_seconds: int | None = None,
) -> int:
    normalized_key = _clean_key_part(counter_key, fallback="runtime-counter")
    cache_key = build_runtime_cache_key("counter", normalized_key)
    effective_amount = amount if amount != 0 else 1
    effective_ttl = _safe_positive_int(ttl_seconds, default=runtime_counter_ttl_seconds())

    try:
        created = cache.add(cache_key, effective_amount, timeout=effective_ttl)
        if created:
            return int(effective_amount)
        try:
            return int(cache.incr(cache_key, delta=effective_amount))
        except Exception:
            previous_raw = cache.get(cache_key) or 0
            previous = int(previous_raw) if str(previous_raw).lstrip("-").isdigit() else 0
            current = previous + effective_amount
            cache.set(cache_key, current, timeout=effective_ttl)
            return current
    except Exception:
        return int(effective_amount)


def read_runtime_counter(counter_key: object, *, default: int = 0) -> int:
    normalized_key = _clean_key_part(counter_key, fallback="runtime-counter")
    cache_key = build_runtime_cache_key("counter", normalized_key)
    try:
        value = cache.get(cache_key)
    except Exception:
        return int(default)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return int(default)


def snapshot_runtime_counter(counter_key: object, *, source: str = "cache") -> tuple[RuntimeCounter, RuntimeCounterSnapshotOutcome]:
    normalized_key = _clean_key_part(counter_key, fallback="runtime-counter")
    value = read_runtime_counter(normalized_key, default=0)
    expiry = timezone.now() + timedelta(seconds=runtime_counter_ttl_seconds())
    row, created = RuntimeCounter.objects.update_or_create(
        key=normalized_key,
        defaults={
            "value": value,
            "source": _clean_key_part(source, fallback="cache"),
            "expires_at": expiry,
        },
    )
    return row, ("created" if created else "updated")


def queue_runtime_task(
    *,
    task_name: object,
    payload: object,
    queue_name: object = "default",
    countdown_seconds: int = 0,
) -> RuntimeTaskEnvelope:
    normalized_queue_name = _clean_key_part(queue_name, fallback="default")
    normalized_task_name = _clean_key_part(task_name, fallback="runtime-task")
    now = timezone.now()
    run_at = now + timedelta(seconds=max(0, int(countdown_seconds or 0)))
    broker_url = runtime_broker_url()
    mode: RuntimeTaskQueueMode = "broker-configured" if broker_url else "buffered-local"

    envelope: RuntimeTaskEnvelope = {
        "task_id": uuid.uuid4().hex,
        "task_name": normalized_task_name,
        "queue_name": normalized_queue_name,
        "mode": mode,
        "broker_url": broker_url,
        "payload": _normalize_payload(payload),
        "scheduled_for": run_at.isoformat(),
        "created_at": now.isoformat(),
    }

    shelf_key = build_runtime_cache_key("broker", "queue", normalized_queue_name)
    shelf_ttl = runtime_broker_shelf_ttl_seconds()
    max_items = runtime_broker_shelf_max_items()

    try:
        existing = cache.get(shelf_key)
        rows = _as_dict_list(existing)
        rows.append(_normalize_payload(envelope))
        cache.set(shelf_key, rows[-max_items:], timeout=shelf_ttl)
    except Exception:
        pass

    increment_runtime_counter("broker.queued.total", amount=1, ttl_seconds=shelf_ttl)
    if mode == "buffered-local":
        increment_runtime_counter("broker.queued.buffered", amount=1, ttl_seconds=shelf_ttl)

    return envelope


def get_buffered_runtime_tasks(*, queue_name: object = "default", limit: int = 20) -> list[RuntimeTaskEnvelope]:
    normalized_queue_name = _clean_key_part(queue_name, fallback="default")
    shelf_key = build_runtime_cache_key("broker", "queue", normalized_queue_name)
    effective_limit = max(1, int(limit or 20))

    try:
        raw_rows = cache.get(shelf_key)
    except Exception:
        return []

    typed_rows = _as_dict_list(raw_rows)
    if not typed_rows:
        return []

    parsed: list[RuntimeTaskEnvelope] = []
    for item in typed_rows[-effective_limit:]:
        parsed.append(
            {
                "task_id": str(item.get("task_id", "")).strip(),
                "task_name": str(item.get("task_name", "")).strip(),
                "queue_name": str(item.get("queue_name", "")).strip(),
                "mode": cast(RuntimeTaskQueueMode, str(item.get("mode", "buffered-local")).strip() or "buffered-local"),
                "broker_url": str(item.get("broker_url", "")).strip(),
                "payload": _normalize_payload(item.get("payload", {})),
                "scheduled_for": str(item.get("scheduled_for", "")).strip(),
                "created_at": str(item.get("created_at", "")).strip(),
            }
        )
    return parsed


def build_runtime_health_snapshot() -> RuntimeHealthSnapshot:
    cache_backend = str(settings.CACHES.get("default", {}).get("BACKEND", "")).strip()
    probe_key = build_runtime_cache_key("health", "probe", uuid.uuid4().hex[:8])
    probe_token = uuid.uuid4().hex

    cache_ok = False
    try:
        cache.set(probe_key, probe_token, timeout=5)
        cache_ok = cache.get(probe_key) == probe_token
        cache.delete(probe_key)
    except Exception:
        cache_ok = False

    queue_depth = read_runtime_counter("broker.queued.total", default=0)
    if queue_depth <= 0:
        queue_depth = len(get_buffered_runtime_tasks(limit=runtime_broker_shelf_max_items()))
    now = timezone.now()
    return {
        "checked_at": now.isoformat(),
        "cache_backend": cache_backend,
        "cache_ok": cache_ok,
        "redis_configured": "redis" in cache_backend.lower(),
        "broker_configured": bool(runtime_broker_url()),
        "broker_url": runtime_broker_url(),
        "buffered_task_count": queue_depth,
        "active_idempotency_records": RuntimeIdempotencyRecord.objects.filter(expires_at__gt=now).count(),
        "persisted_counter_rows": RuntimeCounter.objects.count(),
    }
