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
    instagram_url: str = ""
    avatar_url: str = ""
    cover_photo_url: str = ""
    travel_tags: tuple[str, ...] = ()
    gallery_photos: tuple[str, ...] = ()


DEMO_USERS: tuple[DemoUserSeed, ...] = (
    DemoUserSeed(
        username="mei",
        email="mei@tapne.local",
        first_name="Mei",
        last_name="Tanaka",
        display_name="Mei Tanaka",
        bio="Street-food mapper and trip host focused on practical city itineraries.",
        location="Kyoto, Japan",
        instagram_url="https://instagram.com/mei.travels",
        avatar_url="https://images.unsplash.com/photo-1531123897727-8f129e1688ce?w=400&q=80",
        cover_photo_url="https://images.unsplash.com/photo-1545569341-9eb8b30979d9?w=1600&q=80",
        travel_tags=("street food", "city walks", "temples", "night markets"),
        gallery_photos=(
            "https://images.unsplash.com/photo-1542640244-7e672d6cef4e?w=1200&q=80",
            "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?w=1200&q=80",
            "https://images.unsplash.com/photo-1528360983277-13d401cdc186?w=1200&q=80",
            "https://images.unsplash.com/photo-1490806843957-31f4c9a91c65?w=1200&q=80",
        ),
    ),
    DemoUserSeed(
        username="arun",
        email="arun@tapne.local",
        first_name="Arun",
        last_name="Nair",
        display_name="Arun N.",
        bio="Mountain route planner sharing first-light trekking ops playbooks.",
        location="El Chalten, Argentina",
        instagram_url="https://instagram.com/arun.alpine",
        avatar_url="https://images.unsplash.com/photo-1528892952291-009c663ce843?w=400&q=80",
        cover_photo_url="https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=1600&q=80",
        travel_tags=("trekking", "alpine", "photography", "remote camping"),
        gallery_photos=(
            "https://images.unsplash.com/photo-1454496522488-7a8e488e8606?w=1200&q=80",
            "https://images.unsplash.com/photo-1486870591958-9b9d0d1dda99?w=1200&q=80",
            "https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=1200&q=80",
            "https://images.unsplash.com/photo-1483728642387-6c3bdd6c93e5?w=1200&q=80",
        ),
    ),
    DemoUserSeed(
        username="sahar",
        email="sahar@tapne.local",
        first_name="Sahar",
        last_name="Belhadi",
        display_name="Sahar Belhadi",
        bio="Market-to-desert host combining cultural routes and practical logistics.",
        location="Marrakech, Morocco",
        instagram_url="https://instagram.com/sahar.routes",
        avatar_url="https://images.unsplash.com/photo-1502323777036-f29e3972d82f?w=400&q=80",
        cover_photo_url="https://images.unsplash.com/photo-1489493585363-d69421e0edd3?w=1600&q=80",
        travel_tags=("souks", "desert", "berber culture", "riad stays"),
        gallery_photos=(
            "https://images.unsplash.com/photo-1539020140153-e479b8c83d56?w=1200&q=80",
            "https://images.unsplash.com/photo-1491555103944-7c647fd857e6?w=1200&q=80",
            "https://images.unsplash.com/photo-1518998053901-5348d3961a04?w=1200&q=80",
            "https://images.unsplash.com/photo-1517821362941-f7f753318f81?w=1200&q=80",
        ),
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
            profile.instagram_url = seed.instagram_url
            profile.avatar_url = seed.avatar_url
            profile.cover_photo_url = seed.cover_photo_url
            profile.travel_tags = list(seed.travel_tags)
            profile.gallery_photos = list(seed.gallery_photos)
            profile.save()
            self._vprint(verbose_enabled, f"Profile synced for @{seed.username}")

        self.stdout.write(
            self.style.SUCCESS(
                "Accounts bootstrap complete. "
                f"created={created_count}, updated={updated_count}, total={len(DEMO_USERS)}"
            )
        )
