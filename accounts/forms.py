from __future__ import annotations

from typing import Any, cast

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from email_validator import EmailNotValidError, validate_email

from .models import AccountProfile

UserModel = get_user_model()


def _add_input_css_classes(form: forms.BaseForm) -> None:
    for field in form.fields.values():
        existing = field.widget.attrs.get("class", "").strip()
        merged = f"{existing} form-input".strip()
        field.widget.attrs["class"] = merged


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True, max_length=254)

    class Meta:
        # Cast keeps Pyright strict mode happy with dynamic get_user_model typing.
        model = cast(Any, UserModel)
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _add_input_css_classes(self)
        self.fields["username"].widget.attrs.setdefault("autocomplete", "username")
        self.fields["email"].widget.attrs.setdefault("autocomplete", "email")
        self.fields["password1"].widget.attrs.setdefault("autocomplete", "new-password")
        self.fields["password2"].widget.attrs.setdefault("autocomplete", "new-password")

    def clean_email(self) -> str:
        submitted_email = self.cleaned_data["email"].strip()
        try:
            normalized = validate_email(submitted_email, check_deliverability=False).normalized
        except EmailNotValidError as exc:
            raise forms.ValidationError(str(exc)) from exc

        email = normalized.lower()
        email_taken = UserModel.objects.filter(email__iexact=email).exists()
        if email_taken:
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        duplicate_query = UserModel.objects.filter(username__iexact=username)
        if self.instance.pk:
            duplicate_query = duplicate_query.exclude(pk=self.instance.pk)

        if duplicate_query.exists():
            raise forms.ValidationError("An account with this username already exists.")
        return username

    def save(self, commit: bool = True):  # type: ignore[override]
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"].strip().lower()
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _add_input_css_classes(self)
        self.fields["username"].widget.attrs.setdefault("autocomplete", "username")
        self.fields["password"].widget.attrs.setdefault("autocomplete", "current-password")


class ProfileEditForm(forms.ModelForm):
    email = forms.EmailField(required=True, max_length=254)
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
        submitted_email = self.cleaned_data["email"].strip()
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
