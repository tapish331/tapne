from __future__ import annotations

from datetime import datetime, timezone as datetime_timezone
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

from django.conf import settings
from django.db import DatabaseError
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

SITEMAP_STATIC_PATHS: tuple[str, ...] = (
    "/",
    "/about/",
    "/how-it-works/",
    "/safety/",
    "/contact/",
    "/terms/",
    "/privacy/",
    "/search/",
    "/trips/",
    "/blogs/",
)


def _normalize_host(value: str) -> str:
    candidate = value.strip()
    if "://" in candidate:
        parsed = urlsplit(candidate)
        if parsed.hostname:
            return parsed.hostname.strip().lower()
    return candidate.split(":", 1)[0].strip().lower()


def _normalize_request_host(value: str) -> str:
    candidate = value.strip()
    if "://" in candidate:
        parsed = urlsplit(candidate)
        if parsed.netloc:
            return parsed.netloc.strip().lower()
    return candidate.lower()


def get_canonical_host(request: HttpRequest) -> str:
    configured_host = str(getattr(settings, "CANONICAL_HOST", "") or "").strip()
    if configured_host:
        return _normalize_host(configured_host)
    return _normalize_request_host(request.get_host())


def get_canonical_scheme(request: HttpRequest) -> str:
    configured_scheme = str(getattr(settings, "CANONICAL_SCHEME", "") or "").strip().lower()
    if configured_scheme in {"http", "https"}:
        return configured_scheme
    return "https" if request.is_secure() else "http"


def build_absolute_url(request: HttpRequest, path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{get_canonical_scheme(request)}://{get_canonical_host(request)}{normalized_path}"


def build_canonical_url(request: HttpRequest) -> str:
    return build_absolute_url(request, request.path)


def _collect_sitemap_entries(request: HttpRequest) -> list[tuple[str, datetime | None]]:
    entries: list[tuple[str, datetime | None]] = []
    now_value = timezone.now()
    for path in SITEMAP_STATIC_PATHS:
        entries.append((build_absolute_url(request, path), now_value))

    # Keep sitemap generation resilient even during early boot/migration windows.
    try:
        from blogs.models import Blog
        from trips.models import Trip

        for trip in Trip.objects.filter(is_published=True).only("pk", "updated_at").order_by("pk"):
            entries.append((build_absolute_url(request, trip.get_absolute_url()), trip.updated_at))

        for blog in Blog.objects.filter(is_published=True).only("slug", "updated_at").order_by("pk"):
            entries.append((build_absolute_url(request, blog.get_absolute_url()), blog.updated_at))
    except DatabaseError:
        pass

    return entries


def _render_sitemap(entries: list[tuple[str, datetime | None]]) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']

    for url, last_modified in entries:
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(url)}</loc>")
        if last_modified is not None:
            normalized_last_modified = last_modified
            if timezone.is_naive(normalized_last_modified):
                normalized_last_modified = timezone.make_aware(normalized_last_modified, timezone.get_current_timezone())
            last_modified_iso_date = normalized_last_modified.astimezone(datetime_timezone.utc).date().isoformat()
            lines.append(f"    <lastmod>{last_modified_iso_date}</lastmod>")
        lines.append("  </url>")

    lines.append("</urlset>")
    return "\n".join(lines)


@require_GET
def robots_txt_view(request: HttpRequest) -> HttpResponse:
    sitemap_url = build_absolute_url(request, "/sitemap.xml")
    lines = (
        "User-agent: *",
        "Allow: /",
        f"Sitemap: {sitemap_url}",
    )
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; charset=utf-8")


@require_GET
def sitemap_xml_view(request: HttpRequest) -> HttpResponse:
    sitemap_content = _render_sitemap(_collect_sitemap_entries(request))
    return HttpResponse(sitemap_content, content_type="application/xml; charset=utf-8")
