from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser

from feed.models import MemberFeedPreference

UserModel = get_user_model()


@dataclass(frozen=True)
class FeedPreferenceSeed:
    username: str
    followed_usernames: tuple[str, ...]
    interest_keywords: tuple[str, ...]


DEMO_MEMBER_PREFERENCES: tuple[FeedPreferenceSeed, ...] = (
    FeedPreferenceSeed(
        username="mei",
        followed_usernames=("arun",),
        interest_keywords=("food", "city", "guide"),
    ),
    FeedPreferenceSeed(
        username="arun",
        followed_usernames=("sahar",),
        interest_keywords=("mountain", "trek", "camp"),
    ),
    FeedPreferenceSeed(
        username="sahar",
        followed_usernames=("mei",),
        interest_keywords=("desert", "market", "route"),
    ),
)


class Command(BaseCommand):
    help = "Create or refresh feed personalization preference rows for demo members."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--create-missing-members",
            action="store_true",
            help="Create missing seeded members before creating feed preferences.",
        )
        parser.add_argument(
            "--demo-password",
            default="TapneDemoPass!123",
            help="Password used only when --create-missing-members creates new users.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print detailed progress lines for each preference seed step.",
        )

    def _vprint(self, verbose_enabled: bool, message: str) -> None:
        if verbose_enabled:
            self.stdout.write(f"[feed][verbose] {message}")

    def _get_or_create_seed_user(
        self,
        seed: FeedPreferenceSeed,
        *,
        create_missing_members: bool,
        demo_password: str,
        verbose_enabled: bool,
    ) -> tuple[Any | None, bool]:
        user = cast(Any | None, UserModel.objects.filter(username__iexact=seed.username).first())
        if user:
            if user.username != seed.username:
                user.username = seed.username
                user.save(update_fields=["username"])
                self._vprint(verbose_enabled, f"Normalized username casing for @{seed.username}")
            return user, False

        if not create_missing_members:
            self._vprint(
                verbose_enabled,
                f"Skipping @{seed.username}; account does not exist and --create-missing-members is disabled.",
            )
            return None, False

        user = UserModel.objects.create_user(
            username=seed.username,
            email=f"{seed.username}@tapne.local",
            password=demo_password,
        )
        self._vprint(verbose_enabled, f"Created missing member @{seed.username}")
        return user, True

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        verbose_enabled = bool(options.get("verbose"))
        create_missing_members = bool(options.get("create_missing_members"))
        demo_password = str(options.get("demo_password") or "TapneDemoPass!123")

        self.stdout.write("Bootstrapping feed personalization records...")
        self._vprint(verbose_enabled, f"create_missing_members={create_missing_members}")

        created_users_count = 0
        seeded_preferences_count = 0
        updated_preferences_count = 0
        skipped_preferences_count = 0

        for seed in DEMO_MEMBER_PREFERENCES:
            user, user_created = self._get_or_create_seed_user(
                seed,
                create_missing_members=create_missing_members,
                demo_password=demo_password,
                verbose_enabled=verbose_enabled,
            )
            if user_created:
                created_users_count += 1

            if user is None:
                skipped_preferences_count += 1
                continue

            preference, created = MemberFeedPreference.objects.get_or_create(user=user)
            preference.followed_usernames = [item.lower() for item in seed.followed_usernames]
            preference.interest_keywords = [item.lower() for item in seed.interest_keywords]
            preference.save()

            if created:
                seeded_preferences_count += 1
                self._vprint(verbose_enabled, f"Created preference row for @{seed.username}")
            else:
                updated_preferences_count += 1
                self._vprint(verbose_enabled, f"Updated preference row for @{seed.username}")

        self.stdout.write(
            self.style.SUCCESS(
                "Feed bootstrap complete. "
                f"created_users={created_users_count}, "
                f"created_preferences={seeded_preferences_count}, "
                f"updated_preferences={updated_preferences_count}, "
                f"skipped={skipped_preferences_count}"
            )
        )
