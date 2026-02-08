from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class ComplexityPasswordValidator:
    """
    Require mixed character classes for stronger account passwords.
    """

    def validate(self, password: str, user: object | None = None) -> None:
        errors: list[str] = []

        if not re.search(r"[A-Z]", password):
            errors.append(_("Password must contain at least one uppercase letter."))
        if not re.search(r"[a-z]", password):
            errors.append(_("Password must contain at least one lowercase letter."))
        if not re.search(r"\d", password):
            errors.append(_("Password must contain at least one digit."))
        if not re.search(r"[^A-Za-z0-9]", password):
            errors.append(_("Password must contain at least one symbol."))
        if re.search(r"\s", password):
            errors.append(_("Password must not contain whitespace."))

        if errors:
            raise ValidationError(" ".join(errors))

    def get_help_text(self) -> str:
        return _(
            "Your password must include uppercase, lowercase, digit, and symbol characters, and contain no spaces."
        )
