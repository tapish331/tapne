from typing import TYPE_CHECKING

from django.contrib import admin

from .models import MemberFeedPreference

if TYPE_CHECKING:
    _BaseMemberFeedPreferenceAdmin = admin.ModelAdmin[MemberFeedPreference]
else:
    _BaseMemberFeedPreferenceAdmin = admin.ModelAdmin


@admin.register(MemberFeedPreference)
class MemberFeedPreferenceAdmin(_BaseMemberFeedPreferenceAdmin):
    list_display = (
        "user",
        "followed_count",
        "interest_count",
        "updated_at",
    )
    search_fields = ("user__username",)
    readonly_fields = ("created_at", "updated_at")

    def followed_count(self, obj: MemberFeedPreference) -> int:
        return len(obj.clean_followed_usernames())

    def interest_count(self, obj: MemberFeedPreference) -> int:
        return len(obj.clean_interest_keywords())
