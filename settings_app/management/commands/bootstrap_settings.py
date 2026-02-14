from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser

from settings_app.models import MemberSettings, update_member_settings

UserModel = get_user_model()


@dataclass(frozen=True)
class SettingsSeed:
    username: str
    email_updates: str
    profile_visibility: str
    dm_privacy: str
    theme_preference: str
    search_visibility: bool
    digest_enabled: bool


DEMO_SETTINGS_SEEDS: tuple[SettingsSeed, ...] = (
    SettingsSeed(
        username="mei",
        email_updates=MemberSettings.EMAIL_UPDATES_IMPORTANT,
        profile_visibility=MemberSettings.PROFILE_VISIBILITY_PUBLIC,
        dm_privacy=MemberSettings.DM_PRIVACY_FOLLOWING,
        theme_preference=MemberSettings.THEME_PREFERENCE_SYSTEM,
        search_visibility=True,
        digest_enabled=True,
    ),
    SettingsSeed(
        username="arun",
        email_updates=MemberSettings.EMAIL_UPDATES_ALL,
        profile_visibility=MemberSettings.PROFILE_VISIBILITY_MEMBERS,
        dm_privacy=MemberSettings.DM_PRIVACY_EVERYONE,
        theme_preference=MemberSettings.THEME_PREFERENCE_DARK,
        search_visibility=True,
        digest_enabled=False,
    ),
    SettingsSeed(
        username="sahar",
        email_updates=MemberSettings.EMAIL_UPDATES_IMPORTANT,
        profile_visibility=MemberSettings.PROFILE_VISIBILITY_PUBLIC,
        dm_privacy=MemberSettings.DM_PRIVACY_FOLLOWING,
        theme_preference=MemberSettings.THEME_PREFERENCE_LIGHT,
        search_visibility=False,
        digest_enabled=True,
    ),
    SettingsSeed(
        username="nora",
        email_updates=MemberSettings.EMAIL_UPDATES_NONE,
        profile_visibility=MemberSettings.PROFILE_VISIBILITY_MEMBERS,
        dm_privacy=MemberSettings.DM_PRIVACY_NONE,
        theme_preference=MemberSettings.THEME_PREFERENCE_DARK,
        search_visibility=False,
        digest_enabled=False,
    ),
)


class Command(BaseCommand):
    help = "Create or refresh demo member settings rows for settings page flows."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--create-missing-members",
            action="store_true",
            help="Create missing demo members before applying settings seeds.",
        )
        parser.add_argument(
            "--demo-password",
            default="TapneDemoPass!123",
            help="Password used when --create-missing-members creates users.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print detailed progress lines for each settings seed operation.",
        )

    def _vprint(self, verbose_enabled: bool, message: str) -> None:
        if verbose_enabled:
            self.stdout.write(f"[settings][verbose] {message}")

    def _resolve_member(
        self,
        *,
        username: str,
        create_missing_members: bool,
        demo_password: str,
        verbose_enabled: bool,
    ) -> tuple[Any | None, bool]:
        member = cast(Any | None, UserModel.objects.filter(username__iexact=username).first())
        if member is not None:
            if member.username != username:
                member.username = username
                member.save(update_fields=["username"])
                self._vprint(verbose_enabled, f"Normalized username casing for @{username}")
            return member, False

        if not create_missing_members:
            self._vprint(
                verbose_enabled,
                (
                    f"Skipping @{username}; member does not exist and "
                    "--create-missing-members is disabled."
                ),
            )
            return None, False

        member = UserModel.objects.create_user(
            username=username,
            email=f"{username}@tapne.local",
            password=demo_password,
        )
        self._vprint(verbose_enabled, f"Created missing member @{username}")
        return member, True

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        verbose_enabled = bool(options.get("verbose"))
        create_missing_members = bool(options.get("create_missing_members"))
        demo_password = str(options.get("demo_password") or "TapneDemoPass!123")

        self.stdout.write("Bootstrapping settings records...")
        self._vprint(verbose_enabled, f"create_missing_members={create_missing_members}")

        created_members_count = 0
        created_settings_count = 0
        updated_settings_count = 0
        unchanged_settings_count = 0
        skipped_settings_count = 0

        for seed in DEMO_SETTINGS_SEEDS:
            member, member_created = self._resolve_member(
                username=seed.username,
                create_missing_members=create_missing_members,
                demo_password=demo_password,
                verbose_enabled=verbose_enabled,
            )
            if member_created:
                created_members_count += 1
            if member is None:
                skipped_settings_count += 1
                continue

            settings_row, outcome = update_member_settings(
                member=member,
                email_updates=seed.email_updates,
                profile_visibility=seed.profile_visibility,
                dm_privacy=seed.dm_privacy,
                theme_preference=seed.theme_preference,
                search_visibility=seed.search_visibility,
                digest_enabled=seed.digest_enabled,
            )
            if outcome == "created":
                created_settings_count += 1
            elif outcome == "updated":
                updated_settings_count += 1
            elif outcome == "unchanged":
                unchanged_settings_count += 1
            else:
                skipped_settings_count += 1

            self._vprint(
                verbose_enabled,
                (
                    "Seeded settings for @{username}; outcome={outcome}; "
                    "email_updates={email_updates}; visibility={visibility}; "
                    "dm_privacy={dm_privacy}; theme_preference={theme_preference}; "
                    "search_visibility={search_visibility}; digest_enabled={digest_enabled}; "
                    "settings_id={settings_id}"
                ).format(
                    username=seed.username,
                    outcome=outcome,
                    email_updates=seed.email_updates,
                    visibility=seed.profile_visibility,
                    dm_privacy=seed.dm_privacy,
                    theme_preference=seed.theme_preference,
                    search_visibility=seed.search_visibility,
                    digest_enabled=seed.digest_enabled,
                    settings_id=(settings_row.pk if settings_row is not None else "n/a"),
                ),
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Settings bootstrap complete. "
                f"created_members={created_members_count}, "
                f"created_settings={created_settings_count}, "
                f"updated_settings={updated_settings_count}, "
                f"unchanged_settings={unchanged_settings_count}, "
                f"skipped_settings={skipped_settings_count}"
            )
        )
