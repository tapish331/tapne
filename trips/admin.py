from typing import TYPE_CHECKING

from django.contrib import admin

from .models import Trip

if TYPE_CHECKING:
    _BaseTripAdmin = admin.ModelAdmin[Trip]
else:
    _BaseTripAdmin = admin.ModelAdmin


@admin.register(Trip)
class TripAdmin(_BaseTripAdmin):
    list_display = (
        "id",
        "title",
        "host",
        "destination",
        "starts_at",
        "traffic_score",
        "is_published",
        "updated_at",
    )
    list_filter = ("is_published", "starts_at")
    search_fields = ("title", "summary", "destination", "host__username")
    autocomplete_fields = ("host",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-starts_at", "-id")
