from typing import TYPE_CHECKING

from django.contrib import admin

from .models import EnrollmentRequest

if TYPE_CHECKING:
    _BaseEnrollmentRequestAdmin = admin.ModelAdmin[EnrollmentRequest]
else:
    _BaseEnrollmentRequestAdmin = admin.ModelAdmin


@admin.register(EnrollmentRequest)
class EnrollmentRequestAdmin(_BaseEnrollmentRequestAdmin):
    list_display = (
        "id",
        "trip",
        "requester",
        "status",
        "reviewed_by",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("trip__title", "trip__host__username", "requester__username", "message")
    autocomplete_fields = ("trip", "requester", "reviewed_by")
    readonly_fields = ("created_at", "updated_at", "reviewed_at")
    ordering = ("-created_at", "-id")
