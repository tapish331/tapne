from __future__ import annotations

from django.http import HttpRequest

from .seo import build_canonical_url


def canonical_meta(request: HttpRequest) -> dict[str, str]:
    return {
        "canonical_url": build_canonical_url(request),
    }
