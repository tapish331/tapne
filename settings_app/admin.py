from typing import TYPE_CHECKING

from django.contrib import admin

from .models import MemberSettings

if TYPE_CHECKING:
    _BaseMemberSettingsAdmin = admin.ModelAdmin[MemberSettings]
else:
    _BaseMemberSettingsAdmin = admin.ModelAdmin


@admin.register(MemberSettings)
class MemberSettingsAdmin(_BaseMemberSettingsAdmin):
    list_display = (
        "id",
        "member",
        "email_updates",
        "profile_visibility",
        "dm_privacy",
        "theme_preference",
        "search_visibility",
        "digest_enabled",
        "updated_at",
    )
    list_filter = (
        "email_updates",
        "profile_visibility",
        "dm_privacy",
        "theme_preference",
        "search_visibility",
        "digest_enabled",
        "updated_at",
    )
    search_fields = ("member__username", "member__email")
    autocomplete_fields = ("member",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-updated_at", "-id")
