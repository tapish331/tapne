from __future__ import annotations

from urllib.parse import quote, urlparse


def _is_web_usable_url(candidate: str) -> bool:
    if candidate.startswith("/"):
        return True

    parsed = urlparse(candidate)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def should_use_fallback_file_url(resolved_url: str) -> bool:
    normalized = str(resolved_url or "").strip()
    if not normalized:
        return True
    return not normalized.startswith("/")


def build_file_cache_key(*, file_name: str = "", updated_at: object = None) -> str:
    normalized_name = str(file_name or "").strip().replace("\\", "-").replace("/", "-")
    updated_token = ""
    try:
        timestamp_fn = getattr(updated_at, "timestamp", None)
        if callable(timestamp_fn):
            timestamp_value = timestamp_fn()
            if isinstance(timestamp_value, (int, float, str)):
                updated_token = str(int(float(timestamp_value)))
    except Exception:
        updated_token = ""

    if updated_token and normalized_name:
        return f"{updated_token}-{normalized_name}"
    if updated_token:
        return updated_token
    return normalized_name


def build_trip_banner_fallback_url(*, trip_id: int, file_name: str = "", updated_at: object = None) -> str:
    normalized_trip_id = int(trip_id or 0)
    if normalized_trip_id <= 0:
        return ""

    base_url = f"/trips/{normalized_trip_id}/banner/"
    cache_key = build_file_cache_key(file_name=file_name, updated_at=updated_at)
    if not cache_key:
        return base_url
    return f"{base_url}?v={quote(cache_key, safe='')}"


def resolve_file_url(file_field: object) -> str:
    if not file_field:
        return ""

    try:
        resolved = str(getattr(file_field, "url", "") or "").strip()
        if resolved and _is_web_usable_url(resolved):
            return resolved
    except Exception:
        return ""

    return ""
