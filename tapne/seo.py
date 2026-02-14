from __future__ import annotations

import json
from datetime import datetime, timezone as datetime_timezone
from typing import NotRequired, TypedDict, cast
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import DatabaseError
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

SITE_NAME = "tapne"
DEFAULT_META_DESCRIPTION = "tapne: host trips, write blogs, and grow audiences."


class BreadcrumbItem(TypedDict):
    label: str
    url: NotRequired[str]


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


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _truncate_text(value: object, *, max_length: int) -> str:
    text = _clean_text(value)
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3].rstrip()}..."


def normalize_meta_description(value: object, *, fallback: str = DEFAULT_META_DESCRIPTION) -> str:
    cleaned = _truncate_text(value, max_length=220)
    if cleaned:
        return cleaned
    return fallback


def normalize_seo_title(value: object, *, fallback: str = SITE_NAME) -> str:
    cleaned = _truncate_text(value, max_length=120)
    if cleaned:
        return cleaned
    return fallback


def ensure_absolute_url(request: HttpRequest, value: object) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return ""

    if "://" in candidate:
        parsed = urlsplit(candidate)
        if parsed.scheme and parsed.netloc:
            return candidate
    return build_absolute_url(request, candidate)


def serialize_json_ld(payload: object) -> str:
    normalized_payload: object = payload
    if isinstance(payload, tuple):
        normalized_payload = list(cast(tuple[object, ...], payload))
    json_text = json.dumps(
        normalized_payload,
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return json_text.replace("</", "<\\/")


def combine_json_ld_payloads(*payloads: object | None) -> object | None:
    normalized: list[object] = []
    for payload in payloads:
        if payload is None:
            continue
        if isinstance(payload, list):
            list_payload = cast(list[object], payload)
            if not list_payload:
                continue
            normalized.append(list_payload)
            continue
        normalized.append(payload)

    if not normalized:
        return None
    if len(normalized) == 1:
        return normalized[0]
    return normalized


def build_breadcrumb_json_ld(request: HttpRequest, breadcrumbs: list[BreadcrumbItem]) -> dict[str, object] | None:
    item_list: list[dict[str, object]] = []
    position = 1
    for item in breadcrumbs:
        label = _clean_text(item.get("label", ""))
        url = str(item.get("url", "") or "").strip()
        if not label or not url:
            continue

        item_list.append(
            {
                "@type": "ListItem",
                "position": position,
                "name": label,
                "item": ensure_absolute_url(request, url),
            }
        )
        position += 1

    if not item_list:
        return None

    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": item_list,
    }


def build_seo_meta_context(
    request: HttpRequest,
    *,
    title: object,
    description: object,
    og_type: str = "website",
    image_url: object = "",
    twitter_card: str = "",
    json_ld_payload: object | None = None,
) -> dict[str, object]:
    normalized_title = normalize_seo_title(title)
    normalized_description = normalize_meta_description(description)
    normalized_og_type = str(og_type or "website").strip().lower() or "website"
    canonical_url = build_canonical_url(request)
    absolute_image_url = ensure_absolute_url(request, image_url)
    effective_twitter_card = (
        str(twitter_card or "").strip().lower()
        or ("summary_large_image" if absolute_image_url else "summary")
    )

    context: dict[str, object] = {
        "seo_title": normalized_title,
        "seo_description": normalized_description,
        "seo_og_title": normalized_title,
        "seo_og_description": normalized_description,
        "seo_og_type": normalized_og_type,
        "seo_url": canonical_url,
        "seo_twitter_title": normalized_title,
        "seo_twitter_description": normalized_description,
        "seo_twitter_card": effective_twitter_card,
    }

    if absolute_image_url:
        context["seo_og_image"] = absolute_image_url
        context["seo_twitter_image"] = absolute_image_url

    if json_ld_payload is not None:
        context["seo_json_ld"] = serialize_json_ld(json_ld_payload)

    return context


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
