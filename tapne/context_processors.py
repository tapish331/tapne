from __future__ import annotations

from django.http import HttpRequest

from .seo import DEFAULT_META_DESCRIPTION, SITE_NAME, build_canonical_url


def canonical_meta(request: HttpRequest) -> dict[str, str]:
    canonical_url = build_canonical_url(request)
    return {
        "canonical_url": canonical_url,
        "seo_site_name": SITE_NAME,
        "seo_title": SITE_NAME,
        "seo_description_default": DEFAULT_META_DESCRIPTION,
        "seo_description": DEFAULT_META_DESCRIPTION,
        "seo_og_type": "website",
        "seo_og_title": SITE_NAME,
        "seo_og_description": DEFAULT_META_DESCRIPTION,
        "seo_url": canonical_url,
        "seo_twitter_card": "summary",
        "seo_twitter_title": SITE_NAME,
        "seo_twitter_description": DEFAULT_META_DESCRIPTION,
    }
