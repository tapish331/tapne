from __future__ import annotations

from django.conf import settings


def demo_catalog_enabled() -> bool:
    """
    Decide whether demo catalog rows may be used as user-facing fallbacks.

    Production-style deployments should disable this so list/home/search/profile
    surfaces stay live-data only and consistent with each other.
    """

    explicit_flag = getattr(settings, "TAPNE_ENABLE_DEMO_DATA", None)
    if explicit_flag is not None:
        return bool(explicit_flag)
    return bool(getattr(settings, "TAPNE_PLACEHOLDER_MODE", False))


def demo_catalog_visible() -> bool:
    """
    Controls whether is_demo=True rows appear on public-facing surfaces.

    Independent of demo_catalog_enabled() — that controls fallback-to-constants
    behavior when the DB is empty. This controls visibility of seeded demo rows.

    Default: True in DEBUG (local dev), False in production.
    Set TAPNE_DEMO_CATALOG_VISIBLE=true in production env to expose demo catalog
    for traffic simulation without a code deploy.
    """
    explicit_flag = getattr(settings, "TAPNE_DEMO_CATALOG_VISIBLE", None)
    if explicit_flag is not None:
        return bool(explicit_flag)
    return bool(getattr(settings, "DEBUG", False))


def _demo_qs_filter() -> dict[str, bool]:
    """
    Returns ORM filter kwargs to apply to every public-facing Trip/Blog query.

    Returns {} when demo rows are visible (no restriction on is_demo).
    Returns {"is_demo": False} when demo rows should be hidden.

    Usage:
        Trip.objects.filter(status="published", **_demo_qs_filter())
    """
    if demo_catalog_visible():
        return {}
    return {"is_demo": False}
