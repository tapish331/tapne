from typing import TYPE_CHECKING

from django.contrib import admin

from .models import RuntimeCounter, RuntimeIdempotencyRecord

if TYPE_CHECKING:
    _BaseRuntimeIdempotencyRecordAdmin = admin.ModelAdmin[RuntimeIdempotencyRecord]
    _BaseRuntimeCounterAdmin = admin.ModelAdmin[RuntimeCounter]
else:
    _BaseRuntimeIdempotencyRecordAdmin = admin.ModelAdmin
    _BaseRuntimeCounterAdmin = admin.ModelAdmin


@admin.register(RuntimeIdempotencyRecord)
class RuntimeIdempotencyRecordAdmin(_BaseRuntimeIdempotencyRecordAdmin):
    list_display = (
        "id",
        "scope",
        "idempotency_key",
        "owner",
        "status_code",
        "expires_at",
        "updated_at",
    )
    list_filter = ("scope", "status_code", "expires_at")
    search_fields = ("scope", "idempotency_key", "owner__username", "request_fingerprint")
    autocomplete_fields = ("owner",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at", "-id")


@admin.register(RuntimeCounter)
class RuntimeCounterAdmin(_BaseRuntimeCounterAdmin):
    list_display = (
        "id",
        "key",
        "value",
        "source",
        "expires_at",
        "updated_at",
    )
    list_filter = ("source", "expires_at")
    search_fields = ("key", "source")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("key",)
