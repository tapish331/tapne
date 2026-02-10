from typing import TYPE_CHECKING

from django.contrib import admin

from .models import Review

if TYPE_CHECKING:
    _BaseReviewAdmin = admin.ModelAdmin[Review]
else:
    _BaseReviewAdmin = admin.ModelAdmin


@admin.register(Review)
class ReviewAdmin(_BaseReviewAdmin):
    list_display = (
        "id",
        "author",
        "target_type",
        "target_key",
        "rating",
        "created_at",
    )
    list_filter = ("target_type", "rating", "created_at")
    search_fields = ("author__username", "target_key", "target_label", "headline", "body")
    autocomplete_fields = ("author",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at", "-id")
