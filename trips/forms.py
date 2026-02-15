from __future__ import annotations

from typing import Any, cast

from django import forms
from django.utils import timezone

from .models import Trip


class ResilientClearableFileInput(forms.ClearableFileInput):
    def is_initial(self, value: object) -> bool:
        if not value:
            return False
        try:
            return bool(getattr(value, "url", False))
        except Exception:
            return False


def _add_input_css_classes(form: forms.BaseForm) -> None:
    for field in form.fields.values():
        input_type = str(getattr(field.widget, "input_type", "") or "").strip().lower()
        if input_type in {"checkbox", "radio"}:
            continue
        existing = str(field.widget.attrs.get("class", "")).strip()
        merged = f"{existing} form-input".strip()
        field.widget.attrs["class"] = merged


class TripForm(forms.ModelForm):
    class Meta:
        model = Trip
        fields = (
            "title",
            "summary",
            "description",
            "destination",
            "banner_image",
            "trip_type",
            "budget_tier",
            "difficulty_level",
            "pace_level",
            "group_size_label",
            "includes_label",
            "starts_at",
            "ends_at",
            "is_published",
        )
        widgets: dict[str, forms.Widget] = cast(
            dict[str, forms.Widget],
            {
                "description": forms.Textarea(attrs={"rows": 6, "maxlength": 4000}),
                "includes_label": forms.Textarea(attrs={"rows": 2, "maxlength": 280}),
                "banner_image": ResilientClearableFileInput(attrs={"accept": "image/*"}),
                "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
                "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            },
        )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _add_input_css_classes(self)

        metadata_defaults = {
            "trip_type": "adventure",
            "budget_tier": "mid",
            "difficulty_level": "moderate",
            "pace_level": "balanced",
            "group_size_label": "6-10 travelers",
        }
        includes_default = (
            "Host planning support, route guidance, and group coordination. "
            "Bookings are self-managed by members."
        )

        for field_name in metadata_defaults:
            self.fields[field_name].required = True

        banner_field = self.fields.get("banner_image")
        if banner_field is not None:
            banner_field.required = False
            banner_field.help_text = (
                "Optional. Upload a banner image or leave empty to use a cute default "
                "banner based on trip type."
            )

        if bool(getattr(self.instance, "pk", None)):
            preview_data: dict[str, object] = {}
            try:
                from feed.models import enrich_trip_preview_fields

                preview_data = dict(enrich_trip_preview_fields(self.instance.to_trip_data()))
            except (AttributeError, TypeError, ValueError):
                preview_data = {}

            for field_name, fallback in metadata_defaults.items():
                current_value = str(getattr(self.instance, field_name, "") or "").strip()
                if current_value:
                    continue
                suggested = str(preview_data.get(field_name, "") or "").strip() or fallback
                self.initial.setdefault(field_name, suggested)

            current_includes = str(getattr(self.instance, "includes_label", "") or "").strip()
            if not current_includes:
                suggested_includes = str(preview_data.get("includes_label", "") or "").strip() or includes_default
                self.initial.setdefault("includes_label", suggested_includes)
        else:
            for field_name, fallback in metadata_defaults.items():
                self.initial.setdefault(field_name, fallback)
            self.initial.setdefault("includes_label", includes_default)

        for field_name in ("starts_at", "ends_at"):
            value = self.initial.get(field_name) or getattr(self.instance, field_name, None)
            if value:
                try:
                    localized = timezone.localtime(value)
                    self.initial[field_name] = localized.strftime("%Y-%m-%dT%H:%M")
                except (TypeError, ValueError, OverflowError):
                    # Keep form rendering resilient even if timezone conversion fails.
                    pass

    def clean_title(self) -> str:
        title = str(self.cleaned_data.get("title", "")).strip()
        if not title:
            raise forms.ValidationError("Title is required.")
        return title

    def clean_summary(self) -> str:
        return str(self.cleaned_data.get("summary", "")).strip()

    def clean_description(self) -> str:
        description = str(self.cleaned_data.get("description", "")).strip()
        if len(description) > 4000:
            raise forms.ValidationError("Description must be 4000 characters or fewer.")
        return description

    def clean_destination(self) -> str:
        return str(self.cleaned_data.get("destination", "")).strip()

    def clean_includes_label(self) -> str:
        includes_label = str(self.cleaned_data.get("includes_label", "")).strip()
        if len(includes_label) > 280:
            raise forms.ValidationError("Includes details must be 280 characters or fewer.")
        return includes_label

    def save(self, commit: bool = True) -> Trip:  # type: ignore[override]
        trip = super().save(commit=False)
        trip.title = trip.title.strip()
        trip.summary = trip.summary.strip()
        trip.description = trip.description.strip()
        trip.destination = trip.destination.strip()
        trip.trip_type = str(trip.trip_type or "").strip().lower()
        trip.budget_tier = str(trip.budget_tier or "").strip().lower()
        trip.difficulty_level = str(trip.difficulty_level or "").strip().lower()
        trip.pace_level = str(trip.pace_level or "").strip().lower()
        trip.group_size_label = str(trip.group_size_label or "").strip()
        trip.includes_label = str(trip.includes_label or "").strip()

        if commit:
            trip.save()
        return trip
