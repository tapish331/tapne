from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser

from accounts.models import ensure_profile

UserModel = get_user_model()


@dataclass(frozen=True)
class DemoUserSeed:
    username: str
    email: str
    first_name: str
    last_name: str
    display_name: str
    bio: str
    location: str
    website: str = ""


DEMO_USERS: tuple[DemoUserSeed, ...] = (
    DemoUserSeed(
        username="mei",
        email="mei@tapne.local",
        first_name="Mei",
        last_name="Tanaka",
        display_name="Mei Tanaka",
        bio="Street-food mapper and trip host focused on practical city itineraries.",
        location="Kyoto, Japan",
    ),
    DemoUserSeed(
        username="arun",
        email="arun@tapne.local",
        first_name="Arun",
        last_name="Nair",
        display_name="Arun N.",
        bio="Mountain route planner sharing first-light trekking ops playbooks.",
        location="El Chalten, Argentina",
    ),
    DemoUserSeed(
        username="sahar",
        email="sahar@tapne.local",
        first_name="Sahar",
        last_name="Belhadi",
        display_name="Sahar Belhadi",
        bio="Market-to-desert host combining cultural routes and practical logistics.",
        location="Marrakech, Morocco",
    ),
)


class Command(BaseCommand):
    help = (
        "Create or refresh demo accounts/profile records used by the tapne "
        "README contract."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--demo-password",
            default="TapneDemoPass!123",
            help="Password assigned to demo accounts when they are created/reset.",
        )
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Reset passwords for existing demo users too.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print detailed progress lines for each seed step.",
        )

    def _vprint(self, verbose_enabled: bool, message: str) -> None:
        if verbose_enabled:
            self.stdout.write(f"[accounts][verbose] {message}")

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        verbose_enabled = bool(options.get("verbose"))
        demo_password = str(options["demo_password"])
        reset_passwords = bool(options.get("reset_passwords"))

        self.stdout.write("Bootstrapping accounts demo records...")
        self._vprint(verbose_enabled, f"Reset passwords flag: {reset_passwords}")

        created_count = 0
        updated_count = 0
        for seed in DEMO_USERS:
            existing_user = UserModel.objects.filter(username__iexact=seed.username).first()
            created = existing_user is None
            if created:
                user = UserModel.objects.create_user(
                    username=seed.username,
                    email=seed.email,
                    first_name=seed.first_name,
                    last_name=seed.last_name,
                )
            else:
                user = existing_user

            if created:
                user.set_password(demo_password)
                user.save()
                created_count += 1
                self._vprint(verbose_enabled, f"Created user @{seed.username}")
            else:
                changed = False
                if user.email != seed.email:
                    user.email = seed.email
                    changed = True
                if user.first_name != seed.first_name:
                    user.first_name = seed.first_name
                    changed = True
                if user.last_name != seed.last_name:
                    user.last_name = seed.last_name
                    changed = True
                if user.username != seed.username:
                    # Keep seeded usernames canonical even if existing rows differ by case.
                    user.username = seed.username
                    changed = True
                if reset_passwords:
                    user.set_password(demo_password)
                    changed = True
                    self._vprint(
                        verbose_enabled,
                        f"Password reset for existing user @{seed.username}",
                    )
                if changed:
                    user.save()
                    updated_count += 1

            profile = ensure_profile(user)
            profile.display_name = seed.display_name
            profile.bio = seed.bio
            profile.location = seed.location
            profile.website = seed.website
            profile.save()
            self._vprint(verbose_enabled, f"Profile synced for @{seed.username}")

        self.stdout.write(
            self.style.SUCCESS(
                "Accounts bootstrap complete. "
                f"created={created_count}, updated={updated_count}, total={len(DEMO_USERS)}"
            )
        )
