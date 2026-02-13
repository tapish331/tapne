from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Final, Literal, TypedDict, cast

from django.conf import settings
from django.db import models

EmailUpdates = Literal["all", "important", "none"]
ProfileVisibility = Literal["public", "members"]
DmPrivacy = Literal["everyone", "following", "none"]
ThemePreference = Literal["system", "light", "dark"]
ColorScheme = Literal["coast", "ember", "forest"]
UpdateMemberSettingsOutcome = Literal[
    "member-required",
    "invalid-member",
    "created",
    "updated",
    "unchanged",
]

ALLOWED_EMAIL_UPDATES: Final[set[str]] = {"all", "important", "none"}
ALLOWED_PROFILE_VISIBILITY: Final[set[str]] = {"public", "members"}
ALLOWED_DM_PRIVACY: Final[set[str]] = {"everyone", "following", "none"}
ALLOWED_THEME_PREFERENCE: Final[set[str]] = {"system", "light", "dark"}
ALLOWED_COLOR_SCHEME: Final[set[str]] = {"coast", "ember", "forest"}
TRUE_VALUES: Final[set[str]] = {"1", "true", "yes", "on"}
FALSE_VALUES: Final[set[str]] = {"0", "false", "no", "off"}


class MemberSettingsData(TypedDict):
    id: int
    member_username: str
    email_updates: str
    profile_visibility: str
    dm_privacy: str
    theme_preference: str
    color_scheme: str
    search_visibility: bool
    digest_enabled: bool
    created_at: datetime
    updated_at: datetime


class MemberSettingsPayload(TypedDict):
    settings: MemberSettingsData | None
    mode: str
    reason: str


class MemberSettings(models.Model):
    """
    Member-scoped preference row that powers the settings page.

    This row is persisted per member and initialized from environment-driven
    defaults so local and production can share code while using different
    runtime configuration values.
    """

    EMAIL_UPDATES_ALL: Final[str] = "all"
    EMAIL_UPDATES_IMPORTANT: Final[str] = "important"
    EMAIL_UPDATES_NONE: Final[str] = "none"
    EMAIL_UPDATES_CHOICES: Final[tuple[tuple[str, str], ...]] = (
        (EMAIL_UPDATES_ALL, "All activity"),
        (EMAIL_UPDATES_IMPORTANT, "Only important updates"),
        (EMAIL_UPDATES_NONE, "No email updates"),
    )

    PROFILE_VISIBILITY_PUBLIC: Final[str] = "public"
    PROFILE_VISIBILITY_MEMBERS: Final[str] = "members"
    PROFILE_VISIBILITY_CHOICES: Final[tuple[tuple[str, str], ...]] = (
        (PROFILE_VISIBILITY_PUBLIC, "Public"),
        (PROFILE_VISIBILITY_MEMBERS, "Members only"),
    )

    DM_PRIVACY_EVERYONE: Final[str] = "everyone"
    DM_PRIVACY_FOLLOWING: Final[str] = "following"
    DM_PRIVACY_NONE: Final[str] = "none"
    DM_PRIVACY_CHOICES: Final[tuple[tuple[str, str], ...]] = (
        (DM_PRIVACY_EVERYONE, "Everyone"),
        (DM_PRIVACY_FOLLOWING, "People you follow"),
        (DM_PRIVACY_NONE, "No one"),
    )

    THEME_PREFERENCE_SYSTEM: Final[str] = "system"
    THEME_PREFERENCE_LIGHT: Final[str] = "light"
    THEME_PREFERENCE_DARK: Final[str] = "dark"
    THEME_PREFERENCE_CHOICES: Final[tuple[tuple[str, str], ...]] = (
        (THEME_PREFERENCE_SYSTEM, "Follow system"),
        (THEME_PREFERENCE_LIGHT, "Light"),
        (THEME_PREFERENCE_DARK, "Dark"),
    )

    COLOR_SCHEME_COAST: Final[str] = "coast"
    COLOR_SCHEME_EMBER: Final[str] = "ember"
    COLOR_SCHEME_FOREST: Final[str] = "forest"
    COLOR_SCHEME_CHOICES: Final[tuple[tuple[str, str], ...]] = (
        (COLOR_SCHEME_COAST, "Coast"),
        (COLOR_SCHEME_EMBER, "Ember"),
        (COLOR_SCHEME_FOREST, "Forest"),
    )

    member = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tapne_member_settings",
    )
    email_updates = models.CharField(
        max_length=16,
        choices=EMAIL_UPDATES_CHOICES,
        default=EMAIL_UPDATES_IMPORTANT,
    )
    profile_visibility = models.CharField(
        max_length=16,
        choices=PROFILE_VISIBILITY_CHOICES,
        default=PROFILE_VISIBILITY_PUBLIC,
    )
    dm_privacy = models.CharField(
        max_length=16,
        choices=DM_PRIVACY_CHOICES,
        default=DM_PRIVACY_FOLLOWING,
    )
    theme_preference = models.CharField(
        max_length=16,
        choices=THEME_PREFERENCE_CHOICES,
        default=THEME_PREFERENCE_SYSTEM,
    )
    color_scheme = models.CharField(
        max_length=16,
        choices=COLOR_SCHEME_CHOICES,
        default=COLOR_SCHEME_COAST,
    )
    search_visibility = models.BooleanField(
        default=True,
        help_text="When false, this profile is de-prioritized from discovery surfaces.",
    )
    digest_enabled = models.BooleanField(
        default=True,
        help_text="When true, member activity digest emails can be sent.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-id")
        indexes = [
            models.Index(fields=("email_updates", "updated_at"), name="settings_email_updated_idx"),
            models.Index(fields=("profile_visibility", "updated_at"), name="settings_visibility_idx"),
            models.Index(fields=("dm_privacy", "updated_at"), name="settings_dm_privacy_idx"),
        ]

    def __str__(self) -> str:
        username = str(getattr(self.member, "username", "") or "").strip()
        return f"Settings for @{username}"

    def to_member_settings_data(self) -> MemberSettingsData:
        username = str(getattr(self.member, "username", "") or "").strip()
        return {
            "id": int(self.pk or 0),
            "member_username": username,
            "email_updates": str(self.email_updates or "").strip().lower(),
            "profile_visibility": str(self.profile_visibility or "").strip().lower(),
            "dm_privacy": str(self.dm_privacy or "").strip().lower(),
            "theme_preference": str(self.theme_preference or "").strip().lower(),
            "color_scheme": str(self.color_scheme or "").strip().lower(),
            "search_visibility": bool(self.search_visibility),
            "digest_enabled": bool(self.digest_enabled),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _normalize_choice(raw_value: object, *, allowed: set[str], fallback: str) -> str:
    normalized = str(raw_value or "").strip().lower()
    if normalized in allowed:
        return normalized
    return fallback


def normalize_email_updates(raw_value: object) -> EmailUpdates:
    return cast(
        EmailUpdates,
        _normalize_choice(
            raw_value,
            allowed=ALLOWED_EMAIL_UPDATES,
            fallback=MemberSettings.EMAIL_UPDATES_IMPORTANT,
        ),
    )


def normalize_profile_visibility(raw_value: object) -> ProfileVisibility:
    return cast(
        ProfileVisibility,
        _normalize_choice(
            raw_value,
            allowed=ALLOWED_PROFILE_VISIBILITY,
            fallback=MemberSettings.PROFILE_VISIBILITY_PUBLIC,
        ),
    )


def normalize_dm_privacy(raw_value: object) -> DmPrivacy:
    return cast(
        DmPrivacy,
        _normalize_choice(
            raw_value,
            allowed=ALLOWED_DM_PRIVACY,
            fallback=MemberSettings.DM_PRIVACY_FOLLOWING,
        ),
    )


def normalize_theme_preference(raw_value: object) -> ThemePreference:
    return cast(
        ThemePreference,
        _normalize_choice(
            raw_value,
            allowed=ALLOWED_THEME_PREFERENCE,
            fallback=MemberSettings.THEME_PREFERENCE_SYSTEM,
        ),
    )


def normalize_color_scheme(raw_value: object) -> ColorScheme:
    return cast(
        ColorScheme,
        _normalize_choice(
            raw_value,
            allowed=ALLOWED_COLOR_SCHEME,
            fallback=MemberSettings.COLOR_SCHEME_COAST,
        ),
    )


def normalize_bool(raw_value: object, *, default: bool) -> bool:
    if isinstance(raw_value, bool):
        return raw_value

    normalized = str(raw_value or "").strip().lower()
    if not normalized:
        return default
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return default


def resolve_member_settings_defaults() -> dict[str, object]:
    """
    Resolve defaults from env so local and production can diverge by config.
    """

    return {
        "email_updates": normalize_email_updates(
            os.getenv("TAPNE_SETTINGS_DEFAULT_EMAIL_UPDATES", MemberSettings.EMAIL_UPDATES_IMPORTANT)
        ),
        "profile_visibility": normalize_profile_visibility(
            os.getenv(
                "TAPNE_SETTINGS_DEFAULT_PROFILE_VISIBILITY",
                MemberSettings.PROFILE_VISIBILITY_PUBLIC,
            )
        ),
        "dm_privacy": normalize_dm_privacy(
            os.getenv("TAPNE_SETTINGS_DEFAULT_DM_PRIVACY", MemberSettings.DM_PRIVACY_FOLLOWING)
        ),
        "theme_preference": normalize_theme_preference(
            os.getenv("TAPNE_SETTINGS_DEFAULT_THEME_PREFERENCE", MemberSettings.THEME_PREFERENCE_SYSTEM)
        ),
        "color_scheme": normalize_color_scheme(
            os.getenv("TAPNE_SETTINGS_DEFAULT_COLOR_SCHEME", MemberSettings.COLOR_SCHEME_COAST)
        ),
        "search_visibility": normalize_bool(
            os.getenv("TAPNE_SETTINGS_DEFAULT_SEARCH_VISIBILITY", "true"),
            default=True,
        ),
        "digest_enabled": normalize_bool(
            os.getenv("TAPNE_SETTINGS_DEFAULT_DIGEST_ENABLED", "true"),
            default=True,
        ),
    }


def ensure_member_settings(member: object) -> tuple[MemberSettings | None, bool]:
    if not bool(getattr(member, "is_authenticated", False)):
        return None, False

    member_id = int(getattr(member, "pk", 0) or 0)
    if member_id <= 0:
        return None, False

    defaults = resolve_member_settings_defaults()
    settings_row, created = MemberSettings.objects.get_or_create(
        member=cast(Any, member),
        defaults=defaults,
    )

    # Keep persisted rows normalized in case enum choices changed over time.
    changed_fields: list[str] = []
    normalized_email = normalize_email_updates(settings_row.email_updates)
    if settings_row.email_updates != normalized_email:
        settings_row.email_updates = normalized_email
        changed_fields.append("email_updates")

    normalized_visibility = normalize_profile_visibility(settings_row.profile_visibility)
    if settings_row.profile_visibility != normalized_visibility:
        settings_row.profile_visibility = normalized_visibility
        changed_fields.append("profile_visibility")

    normalized_dm_privacy = normalize_dm_privacy(settings_row.dm_privacy)
    if settings_row.dm_privacy != normalized_dm_privacy:
        settings_row.dm_privacy = normalized_dm_privacy
        changed_fields.append("dm_privacy")

    normalized_theme_preference = normalize_theme_preference(settings_row.theme_preference)
    if settings_row.theme_preference != normalized_theme_preference:
        settings_row.theme_preference = normalized_theme_preference
        changed_fields.append("theme_preference")

    normalized_color_scheme = normalize_color_scheme(settings_row.color_scheme)
    if settings_row.color_scheme != normalized_color_scheme:
        settings_row.color_scheme = normalized_color_scheme
        changed_fields.append("color_scheme")

    if changed_fields:
        settings_row.save(update_fields=[*changed_fields, "updated_at"])

    return settings_row, created


def update_member_settings(
    *,
    member: object,
    email_updates: object,
    profile_visibility: object,
    dm_privacy: object,
    theme_preference: object,
    color_scheme: object,
    search_visibility: object,
    digest_enabled: object,
) -> tuple[MemberSettings | None, UpdateMemberSettingsOutcome]:
    if not bool(getattr(member, "is_authenticated", False)):
        return None, "member-required"

    settings_row, created = ensure_member_settings(member)
    if settings_row is None:
        return None, "invalid-member"

    normalized_email = normalize_email_updates(email_updates)
    normalized_visibility = normalize_profile_visibility(profile_visibility)
    normalized_dm_privacy = normalize_dm_privacy(dm_privacy)
    normalized_theme_preference = normalize_theme_preference(theme_preference)
    normalized_color_scheme = normalize_color_scheme(color_scheme)
    normalized_search_visibility = normalize_bool(
        search_visibility,
        default=bool(settings_row.search_visibility),
    )
    normalized_digest_enabled = normalize_bool(
        digest_enabled,
        default=bool(settings_row.digest_enabled),
    )

    changed_fields: list[str] = []
    if settings_row.email_updates != normalized_email:
        settings_row.email_updates = normalized_email
        changed_fields.append("email_updates")
    if settings_row.profile_visibility != normalized_visibility:
        settings_row.profile_visibility = normalized_visibility
        changed_fields.append("profile_visibility")
    if settings_row.dm_privacy != normalized_dm_privacy:
        settings_row.dm_privacy = normalized_dm_privacy
        changed_fields.append("dm_privacy")
    if settings_row.theme_preference != normalized_theme_preference:
        settings_row.theme_preference = normalized_theme_preference
        changed_fields.append("theme_preference")
    if settings_row.color_scheme != normalized_color_scheme:
        settings_row.color_scheme = normalized_color_scheme
        changed_fields.append("color_scheme")
    if settings_row.search_visibility != normalized_search_visibility:
        settings_row.search_visibility = normalized_search_visibility
        changed_fields.append("search_visibility")
    if settings_row.digest_enabled != normalized_digest_enabled:
        settings_row.digest_enabled = normalized_digest_enabled
        changed_fields.append("digest_enabled")

    if changed_fields:
        settings_row.save(update_fields=[*changed_fields, "updated_at"])
        return settings_row, ("created" if created else "updated")

    if created:
        return settings_row, "created"
    return settings_row, "unchanged"


def update_member_appearance(
    *,
    member: object,
    theme_preference: object,
    color_scheme: object,
) -> tuple[MemberSettings | None, UpdateMemberSettingsOutcome]:
    if not bool(getattr(member, "is_authenticated", False)):
        return None, "member-required"

    settings_row, created = ensure_member_settings(member)
    if settings_row is None:
        return None, "invalid-member"

    normalized_theme_preference = normalize_theme_preference(theme_preference)
    normalized_color_scheme = normalize_color_scheme(color_scheme)

    changed_fields: list[str] = []
    if settings_row.theme_preference != normalized_theme_preference:
        settings_row.theme_preference = normalized_theme_preference
        changed_fields.append("theme_preference")
    if settings_row.color_scheme != normalized_color_scheme:
        settings_row.color_scheme = normalized_color_scheme
        changed_fields.append("color_scheme")

    if changed_fields:
        settings_row.save(update_fields=[*changed_fields, "updated_at"])
        return settings_row, ("created" if created else "updated")

    if created:
        return settings_row, "created"
    return settings_row, "unchanged"


def build_settings_payload_for_member(member: object) -> MemberSettingsPayload:
    if not bool(getattr(member, "is_authenticated", False)):
        return {
            "settings": None,
            "mode": "guest-not-allowed",
            "reason": "Settings are available for members only.",
        }

    settings_row, created = ensure_member_settings(member)
    if settings_row is None:
        return {
            "settings": None,
            "mode": "member-settings",
            "reason": "No settings record is available for this account.",
        }

    reason = "Settings loaded from persisted member preferences."
    if created:
        reason = (
            "Settings were initialized using environment-driven defaults for this member."
        )

    return {
        "settings": settings_row.to_member_settings_data(),
        "mode": "member-settings",
        "reason": reason,
    }
