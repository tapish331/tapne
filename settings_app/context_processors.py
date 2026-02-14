from __future__ import annotations

from django.http import HttpRequest

from .models import MemberSettings, ensure_member_settings


def appearance_preferences(request: HttpRequest) -> dict[str, object]:
    theme_preference = MemberSettings.THEME_PREFERENCE_SYSTEM
    source = "local-storage"

    if request.user.is_authenticated:
        settings_row, _created = ensure_member_settings(request.user)
        if settings_row is not None:
            theme_preference = settings_row.theme_preference
            source = "member-settings"

    return {
        "appearance_theme_preference": theme_preference,
        "appearance_source": source,
    }
