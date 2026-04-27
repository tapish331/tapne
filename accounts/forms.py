from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from email_validator import EmailNotValidError, validate_email

from .models import AccountProfile

UserModel = get_user_model()


def _add_input_css_classes(form: forms.BaseForm) -> None:
    for field in form.fields.values():
        existing = field.widget.attrs.get("class", "").strip()
        merged = f"{existing} form-input".strip()
        field.widget.attrs["class"] = merged


class LoginForm(AuthenticationForm):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _add_input_css_classes(self)
        self.fields["username"].label = "Username or Email"
        self.fields["username"].widget.attrs.setdefault("autocomplete", "username email")
        self.fields["password"].widget.attrs.setdefault("autocomplete", "current-password")

    def clean(self) -> dict[str, Any]:
        identifier = str(self.cleaned_data.get("username", "") or "").strip()
        # If it looks like an email, resolve to the matching username before auth.
        if identifier and "@" in identifier:
            try:
                matched = UserModel.objects.get(email__iexact=identifier)
                self.cleaned_data["username"] = str(getattr(matched, "username", "") or "").strip()
            except (UserModel.DoesNotExist, UserModel.MultipleObjectsReturned):
                pass  # Let parent raise the invalid-credentials error
        return super().clean()


class ProfileEditForm(forms.ModelForm):
    email = forms.EmailField(required=False, max_length=254)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)

    class Meta:
        model = AccountProfile
        fields = ("display_name", "bio", "location", "website")
        widgets = {"bio": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        _add_input_css_classes(self)
        self.fields["email"].initial = self.user.email
        self.fields["first_name"].initial = self.user.first_name
        self.fields["last_name"].initial = self.user.last_name

    def clean_email(self) -> str:
        current_email = str(getattr(self.user, "email", "") or "").strip()
        submitted_email = str(self.cleaned_data.get("email", "") or "").strip()
        if not submitted_email or submitted_email.casefold() == current_email.casefold():
            return current_email.lower()
        try:
            normalized = validate_email(submitted_email, check_deliverability=False).normalized
        except EmailNotValidError as exc:
            raise forms.ValidationError(str(exc)) from exc

        email = normalized.lower()
        email_query = UserModel.objects.filter(email__iexact=email).exclude(pk=self.user.pk)
        if email_query.exists():
            raise forms.ValidationError("This email is already used by another account.")
        return email

    def save(self, commit: bool = True) -> AccountProfile:  # type: ignore[override]
        profile = super().save(commit=False)

        self.user.email = self.cleaned_data["email"].strip().lower()
        self.user.first_name = self.cleaned_data["first_name"].strip()
        self.user.last_name = self.cleaned_data["last_name"].strip()

        if commit:
            self.user.save()
            profile.save()
        return profile
