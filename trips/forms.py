from __future__ import annotations

from typing import Any, cast

from django import forms
from django.utils import timezone

from .models import Trip


def _add_input_css_classes(form: forms.BaseForm) -> None:
    for field in form.fields.values():
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
            "starts_at",
            "ends_at",
            "traffic_score",
            "is_published",
        )
        widgets: dict[str, forms.Widget] = cast(
            dict[str, forms.Widget],
            {
                "description": forms.Textarea(attrs={"rows": 6}),
                "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
                "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            },
        )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _add_input_css_classes(self)

        for field_name in ("starts_at", "ends_at"):
            value = self.initial.get(field_name) or getattr(self.instance, field_name, None)
            if value:
                try:
                    localized = timezone.localtime(value)
                    self.initial[field_name] = localized.strftime("%Y-%m-%dT%H:%M")
                except Exception:
                    # Keep form rendering resilient even if timezone conversion fails.
                    pass

    def clean_title(self) -> str:
        title = str(self.cleaned_data.get("title", "")).strip()
        if not title:
            raise forms.ValidationError("Title is required.")
        return title

    def clean_summary(self) -> str:
        return str(self.cleaned_data.get("summary", "")).strip()

    def clean_destination(self) -> str:
        return str(self.cleaned_data.get("destination", "")).strip()

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        starts_at = cleaned_data.get("starts_at")
        ends_at = cleaned_data.get("ends_at")

        if starts_at and ends_at and ends_at < starts_at:
            self.add_error("ends_at", "End time must be after the start time.")

        return cleaned_data

    def save(self, commit: bool = True) -> Trip:  # type: ignore[override]
        trip = super().save(commit=False)
        trip.title = trip.title.strip()
        trip.summary = trip.summary.strip()
        trip.destination = trip.destination.strip()

        if commit:
            trip.save()
        return trip
