from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, TypedDict, cast

from django import forms
from django.utils import timezone

from .models import (
    BUDGET_TIER_CHOICES,
    CONTACT_PREFERENCE_CHOICES,
    DIFFICULTY_LEVEL_CHOICES,
    EXPERIENCE_LEVEL_CHOICES,
    FITNESS_LEVEL_CHOICES,
    GROUP_SIZE_LABEL_CHOICES,
    PACE_LEVEL_CHOICES,
    TRIP_TYPE_CHOICES,
    Trip,
)

CURRENCY_CHOICES: tuple[tuple[str, str], ...] = (
    ("INR", "INR (Rs)"),
    ("USD", "USD ($)"),
    ("EUR", "EUR (EUR)"),
    ("GBP", "GBP (GBP)"),
)
EXTRA_COST_CHOICES: tuple[tuple[str, str], ...] = (
    ("Flights", "Flights"),
    ("Local Transfers", "Local Transfers"),
    ("Personal Expenses", "Personal Expenses"),
    ("Adventure Add-ons", "Adventure Add-ons"),
    ("Meals not included", "Meals not included"),
    ("Optional Activities", "Optional Activities"),
)
SUITABLE_FOR_CHOICES: tuple[tuple[str, str], ...] = (
    ("Solo Travelers", "Solo Travelers"),
    ("Couples", "Couples"),
    ("Friends", "Friends"),
    ("All Genders", "All Genders"),
)
TRIP_VIBE_CHOICES: tuple[tuple[str, str], ...] = (
    ("Chill", "Chill"),
    ("Party", "Party"),
    ("Explorer", "Explorer"),
    ("Spiritual", "Spiritual"),
    ("Adventure", "Adventure"),
    ("Photography", "Photography"),
    ("Work + Travel", "Work + Travel"),
)


class ResilientClearableFileInput(forms.ClearableFileInput):
    def is_initial(self, value: object) -> bool:
        if not value:
            return False
        try:
            return bool(getattr(value, "url", False))
        except Exception:
            return False


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data: object, initial: object = None) -> list[object]:
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            items = cast(list[object] | tuple[object, ...], data)
            cleaned_items: list[object] = []
            for item in items:
                if not item:
                    continue
                cleaned_items.append(single_clean(item, initial))
            return cleaned_items
        if not data:
            return []
        return [single_clean(data, initial)]



def _add_input_css_classes(form: forms.BaseForm) -> None:
    for field in form.fields.values():
        input_type = str(getattr(field.widget, "input_type", "") or "").strip().lower()
        if input_type in {"checkbox", "radio", "hidden"}:
            continue
        existing = str(field.widget.attrs.get("class", "")).strip()
        merged = f"{existing} form-input".strip()
        field.widget.attrs["class"] = merged



def _apply_placeholder_examples(form: forms.BaseForm, placeholders: dict[str, str]) -> None:
    for field_name, example_text in placeholders.items():
        field = form.fields.get(field_name)
        if field is None:
            continue
        input_type = str(getattr(field.widget, "input_type", "") or "").strip().lower()
        if input_type in {"checkbox", "radio", "hidden", "file"}:
            continue
        field.widget.attrs["placeholder"] = example_text


def _safe_json_loads(raw_value: object, *, fallback: object) -> object:
    text = str(raw_value or "").strip()
    if not text:
        return fallback
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return fallback


def _safe_json_list(raw_value: object) -> list[object]:
    parsed = _safe_json_loads(raw_value, fallback=[])
    if not isinstance(parsed, list):
        return []
    return cast(list[object], parsed)


def _as_datetime_or_none(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    return None


def _as_int_or_none(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
    return None


def _as_decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return None


def _as_clean_string_list(raw_value: object) -> list[str]:
    if not isinstance(raw_value, list):
        return []
    cleaned: list[str] = []
    for item in cast(list[object], raw_value):
        normalized = " ".join(str(item or "").strip().split())
        if normalized:
            cleaned.append(normalized)
    return cleaned


class ItineraryDayPayload(TypedDict):
    is_flexible: bool
    title: str
    description: str
    stay: str
    meals: str
    activities: str


class FaqPayload(TypedDict):
    question: str
    answer: str



def _unique_non_empty_lines(raw_text: object, *, max_length: int = 280) -> list[str]:
    lines = str(raw_text or "").splitlines()
    cleaned: list[str] = []
    seen: set[str] = set()
    for line in lines:
        normalized = " ".join(line.strip().split())
        if not normalized:
            continue
        trimmed = normalized[:max_length]
        lowered = trimmed.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(trimmed)
    return cleaned



def _json_dump(payload: object) -> str:
    try:
        return json.dumps(payload, ensure_ascii=True)
    except (TypeError, ValueError):
        return "[]"


class TripForm(forms.ModelForm):
    gallery_images = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={"accept": "image/*", "multiple": True}),
        help_text="Upload multiple images to showcase the trip experience.",
    )
    extra_costs_not_included_choices = forms.MultipleChoiceField(
        required=False,
        choices=EXTRA_COST_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    extra_costs_not_included_custom = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "maxlength": 500}),
        help_text="Optional custom extra-cost items, one per line.",
    )
    suitable_for_choices = forms.MultipleChoiceField(
        required=False,
        choices=SUITABLE_FOR_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    trip_vibe_choices = forms.MultipleChoiceField(
        required=False,
        choices=TRIP_VIBE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )

    highlights_payload = forms.CharField(required=False, widget=forms.HiddenInput())
    included_items_payload = forms.CharField(required=False, widget=forms.HiddenInput())
    not_included_items_payload = forms.CharField(required=False, widget=forms.HiddenInput())
    things_to_carry_payload = forms.CharField(required=False, widget=forms.HiddenInput())
    itinerary_days_payload = forms.CharField(required=False, widget=forms.HiddenInput())
    faqs_payload = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Trip
        fields = (
            "title",
            "destination",
            "trip_type",
            "summary",
            "description",
            "starts_at",
            "ends_at",
            "booking_closes_at",
            "total_seats",
            "minimum_seats",
            "banner_image",
            "video_link",
            "currency",
            "total_trip_price",
            "price_per_person",
            "early_bird_price",
            "has_early_bird_discount",
            "payment_terms",
            "cost_breakdown_accommodation",
            "cost_breakdown_transportation",
            "cost_breakdown_activities",
            "cost_breakdown_guide",
            "cost_breakdown_miscellaneous",
            "includes_label",
            "approximate_flight_cost",
            "optional_activities_cost",
            "buffer_budget_suggestion",
            "personal_shopping_estimate",
            "experience_level_required",
            "fitness_level_required",
            "gender_preference",
            "age_preference",
            "code_of_conduct",
            "cancellation_policy",
            "medical_declaration_required",
            "emergency_contact_required",
            "contact_preference",
            "co_hosts",
            "budget_tier",
            "difficulty_level",
            "pace_level",
            "group_size_label",
            "is_published",
        )
        widgets: dict[str, forms.Widget] = cast(
            dict[str, forms.Widget],
            {
                "description": forms.Textarea(attrs={"rows": 5, "maxlength": 4000}),
                "payment_terms": forms.Textarea(attrs={"rows": 3, "maxlength": 1200}),
                "includes_label": forms.Textarea(attrs={"rows": 2, "maxlength": 280}),
                "code_of_conduct": forms.Textarea(attrs={"rows": 4, "maxlength": 2000}),
                "cancellation_policy": forms.Textarea(attrs={"rows": 4, "maxlength": 2000}),
                "banner_image": ResilientClearableFileInput(attrs={"accept": "image/*"}),
                "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
                "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
                "booking_closes_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
                "currency": forms.Select(choices=CURRENCY_CHOICES),
                "trip_type": forms.Select(choices=TRIP_TYPE_CHOICES),
                "budget_tier": forms.Select(choices=BUDGET_TIER_CHOICES),
                "difficulty_level": forms.Select(choices=DIFFICULTY_LEVEL_CHOICES),
                "pace_level": forms.Select(choices=PACE_LEVEL_CHOICES),
                "group_size_label": forms.Select(choices=GROUP_SIZE_LABEL_CHOICES),
                "experience_level_required": forms.Select(
                    choices=(("", "Select level"), *EXPERIENCE_LEVEL_CHOICES)
                ),
                "fitness_level_required": forms.Select(choices=(("", "Select level"), *FITNESS_LEVEL_CHOICES)),
                "contact_preference": forms.Select(choices=CONTACT_PREFERENCE_CHOICES),
            },
        )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        _add_input_css_classes(self)

        metadata_defaults = {
            "trip_type": "adventure",
            "budget_tier": "mid",
            "difficulty_level": "moderate",
            "pace_level": "balanced",
            "group_size_label": "6-10 travelers",
            "currency": "INR",
            "contact_preference": "in_app",
        }

        self.fields["title"].label = "Trip Title"
        self.fields["destination"].label = "Destination"
        self.fields["trip_type"].label = "Trip Category"
        self.fields["summary"].label = "Trip Summary"
        self.fields["banner_image"].label = "Hero Image"
        self.fields["starts_at"].label = "Start Date"
        self.fields["ends_at"].label = "End Date"
        self.fields["booking_closes_at"].label = "Booking Closes"
        self.fields["total_seats"].label = "Total Seats"
        self.fields["minimum_seats"].label = "Minimum Seats"
        self.fields["total_trip_price"].label = "Total Trip Price"
        self.fields["price_per_person"].label = "Price Per Person"
        self.fields["early_bird_price"].label = "Early Bird Price"
        self.fields["has_early_bird_discount"].label = "Offer a discount for early sign-ups"
        self.fields["payment_terms"].label = "Payment Terms"

        self.fields["summary"].help_text = "A 2-3 line pitch. This appears on the trip card."
        self.fields["description"].help_text = "Optional long-form context and storyline for the trip."
        self.fields["destination"].help_text = "City + Country"
        self.fields["title"].help_text = "A catchy name that grabs attention."
        self.fields["banner_image"].help_text = "Main cover photo for your trip."
        self.fields["video_link"].help_text = "YouTube or Instagram reel link."
        self.fields["minimum_seats"].help_text = "Trip proceeds only if minimum seats are filled."

        self.fields["extra_costs_not_included_choices"].label = "Extra Costs Not Included"
        self.fields["suitable_for_choices"].label = "Suitable For"
        self.fields["trip_vibe_choices"].label = "Trip Vibe"

        self.fields["experience_level_required"].label = "Experience Level Required"
        self.fields["fitness_level_required"].label = "Fitness Level Required"
        self.fields["contact_preference"].label = "Contact Preference"
        self.fields["co_hosts"].label = "Co-hosts"

        _apply_placeholder_examples(
            self,
            {
                "title": "e.g. Sunrise Escape to Meghalaya",
                "destination": "e.g. Shillong, India",
                "summary": "e.g. 3 days of waterfalls, local food, and scenic drives with a fun crew.",
                "description": "Tell the trip story, who it is for, and what makes it memorable.",
                "starts_at": "YYYY-MM-DDTHH:MM",
                "ends_at": "YYYY-MM-DDTHH:MM",
                "booking_closes_at": "YYYY-MM-DDTHH:MM",
                "total_seats": "e.g. 12",
                "minimum_seats": "e.g. 6",
                "video_link": "e.g. https://www.youtube.com/watch?v=abc123",
                "total_trip_price": "e.g. 18000",
                "price_per_person": "Auto-calculated from total and seats, or enter manually.",
                "early_bird_price": "e.g. 15999",
                "payment_terms": "e.g. 40% at booking, 60% seven days before departure.",
                "extra_costs_not_included_custom": "e.g. Visa fees\ne.g. Personal snacks",
                "cost_breakdown_accommodation": "e.g. 6500",
                "cost_breakdown_transportation": "e.g. 3200",
                "cost_breakdown_activities": "e.g. 2600",
                "cost_breakdown_guide": "e.g. 1800",
                "cost_breakdown_miscellaneous": "e.g. 900",
                "includes_label": "e.g. Stay, local transport, and host support included.",
                "approximate_flight_cost": "e.g. INR 5000 - INR 8000",
                "optional_activities_cost": "e.g. INR 1200 - INR 3000",
                "buffer_budget_suggestion": "e.g. INR 3000",
                "personal_shopping_estimate": "e.g. INR 2500",
                "gender_preference": "e.g. Women only (leave blank for all genders)",
                "age_preference": "e.g. 22-35",
                "code_of_conduct": "e.g. Respect group timings, local culture, and fellow travelers.",
                "cancellation_policy": "e.g. 100% refund up to 10 days; 50% up to 5 days.",
                "co_hosts": "e.g. @riya, @arjun",
            },
        )

        self.fields["title"].required = True
        self.fields["destination"].required = True
        self.fields["trip_type"].required = True
        self.fields["summary"].required = True
        self.fields["starts_at"].required = True
        self.fields["ends_at"].required = True
        self.fields["total_seats"].required = True
        self.fields["total_trip_price"].required = True

        is_edit_mode = bool(getattr(self.instance, "pk", None))
        self.fields["banner_image"].required = not is_edit_mode

        for field_name, fallback in metadata_defaults.items():
            self.initial.setdefault(field_name, fallback)

        self.initial.setdefault("minimum_seats", 4)
        self.initial.setdefault("total_seats", 10)

        if is_edit_mode:
            existing_extra_costs = [
                str(item or "").strip()
                for item in cast(list[object], getattr(self.instance, "extra_costs_not_included", []) or [])
                if str(item or "").strip()
            ]
            preset_extra_costs = {choice for choice, _label in EXTRA_COST_CHOICES}
            self.initial.setdefault(
                "extra_costs_not_included_choices",
                [item for item in existing_extra_costs if item in preset_extra_costs],
            )
            self.initial.setdefault(
                "extra_costs_not_included_custom",
                "\n".join(item for item in existing_extra_costs if item not in preset_extra_costs),
            )
            self.initial.setdefault("suitable_for_choices", getattr(self.instance, "suitable_for", []) or [])
            self.initial.setdefault("trip_vibe_choices", getattr(self.instance, "trip_vibe", []) or [])
        else:
            self.initial.setdefault("extra_costs_not_included_choices", [])
            self.initial.setdefault("suitable_for_choices", ["Solo Travelers", "Friends", "All Genders"])
            self.initial.setdefault("trip_vibe_choices", ["Explorer"])

        self.initial.setdefault("highlights_payload", _json_dump(getattr(self.instance, "highlights", []) or []))
        self.initial.setdefault("included_items_payload", _json_dump(getattr(self.instance, "included_items", []) or []))
        self.initial.setdefault(
            "not_included_items_payload",
            _json_dump(getattr(self.instance, "not_included_items", []) or []),
        )
        self.initial.setdefault("things_to_carry_payload", _json_dump(getattr(self.instance, "things_to_carry", []) or []))
        self.initial.setdefault("itinerary_days_payload", _json_dump(getattr(self.instance, "itinerary_days", []) or []))
        self.initial.setdefault("faqs_payload", _json_dump(getattr(self.instance, "faqs", []) or []))

        for field_name in ("starts_at", "ends_at", "booking_closes_at"):
            value = self.initial.get(field_name) or getattr(self.instance, field_name, None)
            if value:
                try:
                    localized = timezone.localtime(value)
                    self.initial[field_name] = localized.strftime("%Y-%m-%dT%H:%M")
                except (TypeError, ValueError, OverflowError):
                    # Keep form rendering resilient even if timezone conversion fails.
                    pass

    def _parse_text_payload(self, field_name: str, *, item_label: str) -> list[str]:
        raw_payload = self.cleaned_data.get(field_name, "")
        parsed = _safe_json_list(raw_payload)

        cleaned: list[str] = []
        for item in parsed:
            value = " ".join(str(item or "").strip().split())
            if not value:
                continue
            cleaned.append(value[:280])
        return cleaned

    def _parse_itinerary_payload(self) -> list[ItineraryDayPayload]:
        raw_payload = self.cleaned_data.get("itinerary_days_payload", "")
        parsed = _safe_json_list(raw_payload)

        itinerary_days: list[ItineraryDayPayload] = []
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            entry_map = cast(dict[object, object], entry)

            title = " ".join(str(entry_map.get("title", "") or "").strip().split())[:180]
            description = str(entry_map.get("description", "") or "").strip()[:2000]
            stay = " ".join(str(entry_map.get("stay", "") or "").strip().split())[:180]
            meals = " ".join(str(entry_map.get("meals", "") or "").strip().split())[:180]
            activities = " ".join(str(entry_map.get("activities", "") or "").strip().split())[:280]
            is_flexible = bool(entry_map.get("is_flexible", False))

            if not any((title, description, stay, meals, activities)):
                continue

            itinerary_days.append(
                {
                    "is_flexible": is_flexible,
                    "title": title,
                    "description": description,
                    "stay": stay,
                    "meals": meals,
                    "activities": activities,
                }
            )
        return itinerary_days

    def _parse_faqs_payload(self) -> list[FaqPayload]:
        raw_payload = self.cleaned_data.get("faqs_payload", "")
        parsed = _safe_json_list(raw_payload)

        faqs: list[FaqPayload] = []
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            entry_map = cast(dict[object, object], entry)

            question = " ".join(str(entry_map.get("question", "") or "").strip().split())[:280]
            answer = str(entry_map.get("answer", "") or "").strip()[:2000]
            if not question and not answer:
                continue
            faqs.append({"question": question, "answer": answer})
        return faqs

    def clean_title(self) -> str:
        title = str(self.cleaned_data.get("title", "")).strip()
        if not title:
            raise forms.ValidationError("Trip title is required.")
        return title

    def clean_destination(self) -> str:
        destination = str(self.cleaned_data.get("destination", "")).strip()
        if not destination:
            raise forms.ValidationError("Destination is required.")
        return destination

    def clean_summary(self) -> str:
        summary = str(self.cleaned_data.get("summary", "")).strip()
        if not summary:
            raise forms.ValidationError("Trip summary is required.")
        return summary

    def clean_description(self) -> str:
        description = str(self.cleaned_data.get("description", "")).strip()
        if len(description) > 4000:
            raise forms.ValidationError("Description must be 4000 characters or fewer.")
        return description

    def clean_includes_label(self) -> str:
        includes_label = str(self.cleaned_data.get("includes_label", "")).strip()
        if len(includes_label) > 280:
            raise forms.ValidationError("Includes details must be 280 characters or fewer.")
        return includes_label

    def clean(self) -> dict[str, object]:
        cleaned_data = cast(dict[str, object], super().clean())

        try:
            cleaned_data["highlights"] = self._parse_text_payload("highlights_payload", item_label="Highlights")
            cleaned_data["included_items"] = self._parse_text_payload(
                "included_items_payload",
                item_label="Included items",
            )
            cleaned_data["not_included_items"] = self._parse_text_payload(
                "not_included_items_payload",
                item_label="Not included items",
            )
            cleaned_data["things_to_carry"] = self._parse_text_payload(
                "things_to_carry_payload",
                item_label="Things to carry",
            )
            cleaned_data["itinerary_days"] = self._parse_itinerary_payload()
            cleaned_data["faqs"] = self._parse_faqs_payload()
        except forms.ValidationError as exc:
            self.add_error(None, exc)

        selected_extra_costs = _as_clean_string_list(cleaned_data.get("extra_costs_not_included_choices", []))
        custom_extra_costs = _unique_non_empty_lines(cleaned_data.get("extra_costs_not_included_custom", ""), max_length=120)
        merged_extra_costs: list[str] = []
        seen_extra_costs: set[str] = set()
        for value in (*selected_extra_costs, *custom_extra_costs):
            lowered = value.lower()
            if lowered in seen_extra_costs:
                continue
            seen_extra_costs.add(lowered)
            merged_extra_costs.append(value)
        cleaned_data["extra_costs_not_included"] = merged_extra_costs

        cleaned_data["suitable_for"] = _as_clean_string_list(cleaned_data.get("suitable_for_choices", []))
        cleaned_data["trip_vibe"] = _as_clean_string_list(cleaned_data.get("trip_vibe_choices", []))

        starts_at = _as_datetime_or_none(cleaned_data.get("starts_at"))
        ends_at = _as_datetime_or_none(cleaned_data.get("ends_at"))
        booking_closes_at = _as_datetime_or_none(cleaned_data.get("booking_closes_at"))
        total_seats = _as_int_or_none(cleaned_data.get("total_seats"))
        minimum_seats = _as_int_or_none(cleaned_data.get("minimum_seats"))
        total_trip_price = _as_decimal_or_none(cleaned_data.get("total_trip_price"))
        price_per_person = _as_decimal_or_none(cleaned_data.get("price_per_person"))
        has_early_bird_discount = bool(cleaned_data.get("has_early_bird_discount"))
        early_bird_price = _as_decimal_or_none(cleaned_data.get("early_bird_price"))

        if starts_at and ends_at and ends_at < starts_at:
            self.add_error("ends_at", "End date must be after start date.")

        if booking_closes_at and starts_at and booking_closes_at > starts_at:
            self.add_error("booking_closes_at", "Booking close time must be before the trip start.")

        if total_seats is not None and minimum_seats is not None and minimum_seats > total_seats:
            self.add_error("minimum_seats", "Minimum seats cannot exceed total seats.")

        if has_early_bird_discount and not early_bird_price:
            self.add_error("early_bird_price", "Provide an early-bird price when discount is enabled.")
        if not has_early_bird_discount:
            cleaned_data["early_bird_price"] = None

        if (
            total_trip_price is not None
            and total_seats
            and int(total_seats) > 0
            and price_per_person is None
        ):
            auto_price = (total_trip_price / Decimal(total_seats)).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            cleaned_data["price_per_person"] = auto_price

        includes_label = str(cleaned_data.get("includes_label", "") or "").strip()
        if not includes_label:
            included_items = cast(list[str], cleaned_data.get("included_items", []) or [])
            if included_items:
                includes_label = "; ".join(included_items[:3])
            cleaned_data["includes_label"] = includes_label[:280]

        return cleaned_data

    def save(self, commit: bool = True) -> Trip:  # type: ignore[override]
        trip = super().save(commit=False)
        trip.title = trip.title.strip()
        trip.summary = trip.summary.strip()
        trip.description = trip.description.strip()
        trip.destination = trip.destination.strip()
        trip.video_link = str(trip.video_link or "").strip()
        trip.currency = str(trip.currency or "INR").strip().upper() or "INR"
        trip.trip_type = str(trip.trip_type or "").strip().lower()
        trip.budget_tier = str(trip.budget_tier or "").strip().lower()
        trip.difficulty_level = str(trip.difficulty_level or "").strip().lower()
        trip.pace_level = str(trip.pace_level or "").strip().lower()
        trip.group_size_label = str(trip.group_size_label or "").strip()
        trip.includes_label = str(trip.includes_label or "").strip()
        trip.payment_terms = str(trip.payment_terms or "").strip()
        trip.approximate_flight_cost = " ".join(str(trip.approximate_flight_cost or "").strip().split())
        trip.optional_activities_cost = " ".join(str(trip.optional_activities_cost or "").strip().split())
        trip.buffer_budget_suggestion = " ".join(str(trip.buffer_budget_suggestion or "").strip().split())
        trip.personal_shopping_estimate = " ".join(str(trip.personal_shopping_estimate or "").strip().split())
        trip.gender_preference = " ".join(str(trip.gender_preference or "").strip().split())
        trip.age_preference = " ".join(str(trip.age_preference or "").strip().split())
        trip.code_of_conduct = str(trip.code_of_conduct or "").strip()
        trip.cancellation_policy = str(trip.cancellation_policy or "").strip()
        trip.contact_preference = str(trip.contact_preference or "in_app").strip().lower() or "in_app"
        trip.co_hosts = " ".join(str(trip.co_hosts or "").strip().split())

        trip.extra_costs_not_included = cast(list[str], self.cleaned_data.get("extra_costs_not_included", []) or [])
        trip.highlights = cast(list[str], self.cleaned_data.get("highlights", []) or [])
        trip.itinerary_days = cast(list[ItineraryDayPayload], self.cleaned_data.get("itinerary_days", []) or [])
        trip.included_items = cast(list[str], self.cleaned_data.get("included_items", []) or [])
        trip.not_included_items = cast(list[str], self.cleaned_data.get("not_included_items", []) or [])
        trip.things_to_carry = cast(list[str], self.cleaned_data.get("things_to_carry", []) or [])
        trip.suitable_for = cast(list[str], self.cleaned_data.get("suitable_for", []) or [])
        trip.trip_vibe = cast(list[str], self.cleaned_data.get("trip_vibe", []) or [])
        trip.faqs = cast(list[FaqPayload], self.cleaned_data.get("faqs", []) or [])

        if commit:
            trip.save()
        return trip
