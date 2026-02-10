from typing import TYPE_CHECKING

from django.contrib import admin

from .models import MediaAsset, MediaAttachment

if TYPE_CHECKING:
    _BaseMediaAssetAdmin = admin.ModelAdmin[MediaAsset]
    _BaseMediaAttachmentAdmin = admin.ModelAdmin[MediaAttachment]
else:
    _BaseMediaAssetAdmin = admin.ModelAdmin
    _BaseMediaAttachmentAdmin = admin.ModelAdmin


@admin.register(MediaAsset)
class MediaAssetAdmin(_BaseMediaAssetAdmin):
    list_display = (
        "id",
        "owner",
        "kind",
        "original_name",
        "size_bytes",
        "created_at",
    )
    list_filter = ("kind", "created_at")
    search_fields = ("owner__username", "original_name", "content_type", "checksum_sha256")
    autocomplete_fields = ("owner",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at", "-id")


@admin.register(MediaAttachment)
class MediaAttachmentAdmin(_BaseMediaAttachmentAdmin):
    list_display = (
        "id",
        "asset",
        "target_type",
        "target_key",
        "created_at",
    )
    list_filter = ("target_type", "created_at")
    search_fields = (
        "asset__owner__username",
        "target_key",
        "target_label",
        "target_url",
        "asset__original_name",
    )
    autocomplete_fields = ("asset",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at", "-id")
