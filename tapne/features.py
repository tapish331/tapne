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
