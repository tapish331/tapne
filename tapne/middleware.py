from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import DisallowedHost
from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect

from .seo import get_canonical_scheme


def _normalize_host(value: str) -> str:
    candidate = value.strip()
    if "://" in candidate:
        parsed = urlsplit(candidate)
        if parsed.hostname:
            return parsed.hostname.strip().lower()
    return candidate.split(":", 1)[0].strip().lower()


class CanonicalHostRedirectMiddleware:
    get_response: Callable[[HttpRequest], HttpResponse]

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        redirect_url = self._build_redirect_url(request)
        if redirect_url:
            return HttpResponsePermanentRedirect(redirect_url)
        return self.get_response(request)

    def _build_redirect_url(self, request: HttpRequest) -> str:
        if not bool(getattr(settings, "CANONICAL_HOST_REDIRECT_ENABLED", False)):
            return ""

        canonical_host_raw = str(getattr(settings, "CANONICAL_HOST", "") or "").strip()
        if not canonical_host_raw:
            return ""
        canonical_host = _normalize_host(canonical_host_raw)

        try:
            request_host = _normalize_host(request.get_host())
        except DisallowedHost:
            return ""

        if not request_host or request_host == canonical_host:
            return ""

        canonical_scheme = get_canonical_scheme(request)
        return f"{canonical_scheme}://{canonical_host}{request.get_full_path()}"
