from __future__ import annotations

from typing import Any, cast

from django import forms

from .models import MemberSettings


def _add_input_css_classes(form: forms.BaseForm) -> None:
    for field in form.fields.values():
        existing = str(field.widget.attrs.get("class", "")).strip()
        merged = f"{existing} form-input".strip()
        field.widget.attrs["class"] = merged


class MemberSettingsForm(forms.ModelForm):
    class Meta:
        model = MemberSettings
        fields = (
            "email_updates",
            "profile_visibility",
            "dm_privacy",
            "theme_preference",
            "color_scheme",
            "search_visibility",
            "digest_enabled",
        )
        widgets: dict[str, forms.Widget] = cast(
            dict[str, forms.Widget],
            {
                "email_updates": forms.Select(),
                "profile_visibility": forms.Select(),
                "dm_privacy": forms.Select(),
                "theme_preference": forms.Select(),
                "color_scheme": forms.Select(),
                "search_visibility": forms.CheckboxInput(),
                "digest_enabled": forms.CheckboxInput(),
            },
        )
        help_texts = {
            "email_updates": "Choose how frequently account updates are sent.",
            "profile_visibility": "Control who can view your public profile details.",
            "dm_privacy": "Decide who can initiate new direct messages.",
            "theme_preference": "Choose whether your account prefers light, dark, or system mode.",
            "color_scheme": "Set the accent palette used across the site UI.",
            "search_visibility": "Hide or show your profile in discovery ranking surfaces.",
            "digest_enabled": "Enable periodic activity digest notifications.",
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _add_input_css_classes(self)

    def clean_email_updates(self) -> str:
        return str(self.cleaned_data.get("email_updates", "")).strip().lower()

    def clean_profile_visibility(self) -> str:
        return str(self.cleaned_data.get("profile_visibility", "")).strip().lower()

    def clean_dm_privacy(self) -> str:
        return str(self.cleaned_data.get("dm_privacy", "")).strip().lower()

    def clean_theme_preference(self) -> str:
        return str(self.cleaned_data.get("theme_preference", "")).strip().lower()

    def clean_color_scheme(self) -> str:
        return str(self.cleaned_data.get("color_scheme", "")).strip().lower()

    def save(self, commit: bool = True) -> MemberSettings:  # type: ignore[override]
        settings_row = super().save(commit=False)
        settings_row.email_updates = settings_row.email_updates.strip().lower()
        settings_row.profile_visibility = settings_row.profile_visibility.strip().lower()
        settings_row.dm_privacy = settings_row.dm_privacy.strip().lower()
        settings_row.theme_preference = settings_row.theme_preference.strip().lower()
        settings_row.color_scheme = settings_row.color_scheme.strip().lower()

        if commit:
            settings_row.save()
        return settings_row
