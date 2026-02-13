from __future__ import annotations

from django.http import HttpRequest

from .models import MemberSettings, ensure_member_settings


def appearance_preferences(request: HttpRequest) -> dict[str, object]:
    theme_preference = MemberSettings.THEME_PREFERENCE_SYSTEM
    color_scheme = MemberSettings.COLOR_SCHEME_COAST
    source = "local-storage"

    if request.user.is_authenticated:
        settings_row, _created = ensure_member_settings(request.user)
        if settings_row is not None:
            theme_preference = settings_row.theme_preference
            color_scheme = settings_row.color_scheme
            source = "member-settings"

    return {
        "appearance_theme_preference": theme_preference,
        "appearance_color_scheme": color_scheme,
        "appearance_source": source,
    }
