from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from django.http import HttpRequest

from .forms import LoginForm, SignUpForm

AUTH_MODAL_FEEDBACK_SESSION_KEY = "auth_modal_feedback"


@dataclass(frozen=True)
class NormalizedFeedback:
    mode: str
    fields: dict[str, str]
    errors: dict[str, list[str]]


def _normalize_feedback(raw_feedback: object) -> NormalizedFeedback:
    if not isinstance(raw_feedback, dict):
        return NormalizedFeedback(mode="", fields={}, errors={})

    feedback_map = cast(dict[str, object], raw_feedback)
    mode = str(feedback_map.get("mode", "")).strip().lower()
    if mode not in {"login", "signup"}:
        return NormalizedFeedback(mode="", fields={}, errors={})

    fields: dict[str, str] = {}
    raw_fields = feedback_map.get("fields", {})
    if isinstance(raw_fields, dict):
        raw_fields_map = cast(dict[str, object], raw_fields)
        for key, value in raw_fields_map.items():
            key = str(key).strip()
            if not key:
                continue
            fields[key] = str(value).strip()

    errors: dict[str, list[str]] = {}
    raw_errors = feedback_map.get("errors", {})
    if isinstance(raw_errors, dict):
        raw_errors_map = cast(dict[str, object], raw_errors)
        for key, values_obj in raw_errors_map.items():
            if not isinstance(values_obj, list):
                continue

            key = str(key).strip()
            if not key:
                continue

            typed_values = cast(list[object], values_obj)
            cleaned_values = [str(value).strip() for value in typed_values if str(value).strip()]
            if cleaned_values:
                errors[key] = cleaned_values

    return NormalizedFeedback(mode=mode, fields=fields, errors=errors)


def auth_modal_forms(request: HttpRequest) -> dict[str, object]:
    """
    Provide login/signup forms for the shared auth modal on every page.
    """

    if request.user.is_authenticated:
        request.session.pop(AUTH_MODAL_FEEDBACK_SESSION_KEY, None)
        return {
            "auth_modal_login_form": None,
            "auth_modal_signup_form": None,
            "auth_modal_errors": {"login": {}, "signup": {}},
        }

    feedback = _normalize_feedback(request.session.pop(AUTH_MODAL_FEEDBACK_SESSION_KEY, {}))
    mode = feedback.mode
    fields = feedback.fields
    errors = feedback.errors

    login_form = LoginForm(request=request)
    signup_form = SignUpForm()

    if mode == "login":
        login_form.fields["username"].initial = str(fields.get("username", "")).strip()
    elif mode == "signup":
        signup_form.fields["username"].initial = str(fields.get("username", "")).strip()
        signup_form.fields["email"].initial = str(fields.get("email", "")).strip()

    return {
        "auth_modal_login_form": login_form,
        "auth_modal_signup_form": signup_form,
        "auth_modal_errors": {
            "login": errors if mode == "login" else {},
            "signup": errors if mode == "signup" else {},
        },
    }
