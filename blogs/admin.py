from typing import TYPE_CHECKING

from django.contrib import admin

from .models import Blog

if TYPE_CHECKING:
    _BaseBlogAdmin = admin.ModelAdmin[Blog]
else:
    _BaseBlogAdmin = admin.ModelAdmin


@admin.register(Blog)
class BlogAdmin(_BaseBlogAdmin):
    list_display = (
        "id",
        "title",
        "slug",
        "author",
        "reads",
        "reviews_count",
        "is_published",
        "updated_at",
    )
    list_filter = ("is_published", "created_at")
    search_fields = ("title", "slug", "excerpt", "author__username")
    autocomplete_fields = ("author",)
    readonly_fields = ("created_at", "updated_at")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ("-created_at", "-id")
