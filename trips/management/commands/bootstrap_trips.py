from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from trips.models import Trip

UserModel = get_user_model()


@dataclass(frozen=True)
class TripSeed:
    trip_id: int
    host_username: str
    title: str
    summary: str
    description: str
    destination: str
    traffic_score: int
    trip_type: str
    budget_tier: str
    difficulty_level: str
    pace_level: str
    group_size_label: str
    starts_in_days: int
    duration_days: int = 3


DEMO_TRIP_SEEDS: tuple[TripSeed, ...] = (
    TripSeed(
        trip_id=101,
        host_username="mei",
        title="Kyoto food lanes weekend",
        summary="A compact culinary walk through Nishiki, neighborhood izakaya spots, and hidden tea counters.",
        description=(
            "Two-day city format focused on reliable food windows, neighborhood pacing, and host-led context "
            "for first-time Kyoto visitors."
        ),
        destination="Kyoto, Japan",
        traffic_score=92,
        trip_type="food-culture",
        budget_tier="mid",
        difficulty_level="easy",
        pace_level="balanced",
        group_size_label="6-10 travelers",
        starts_in_days=12,
        duration_days=2,
    ),
    TripSeed(
        trip_id=102,
        host_username="arun",
        title="Patagonia first-light trekking camp",
        summary="Five-day route with sunrise ridge points, weather-safe camps, and a photographer-friendly pace.",
        description=(
            "Five-day alpine route with conservative checkpoints, weather buffers, and a sunrise-first schedule "
            "for mixed-experience groups."
        ),
        destination="El Chalten, Argentina",
        traffic_score=87,
        trip_type="trekking",
        budget_tier="premium",
        difficulty_level="challenging",
        pace_level="balanced",
        group_size_label="6-8 travelers",
        starts_in_days=26,
        duration_days=5,
    ),
    TripSeed(
        trip_id=103,
        host_username="sahar",
        title="Morocco souk to desert circuit",
        summary="Markets in Marrakech, Atlas crossings, and a two-night Sahara camp for first-time route builders.",
        description=(
            "Logistics-first market-to-desert itinerary covering city staging, transfer handoffs, and camp sequencing "
            "for dependable group flow."
        ),
        destination="Marrakech to Merzouga",
        traffic_score=81,
        trip_type="desert",
        budget_tier="mid",
        difficulty_level="moderate",
        pace_level="balanced",
        group_size_label="8-12 travelers",
        starts_in_days=-8,
        duration_days=4,
    ),
)


class Command(BaseCommand):
    help = "Create or refresh demo trip rows used by list/detail/search flows."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--create-missing-hosts",
            action="store_true",
            help="Create missing trip hosts before seeding trip rows.",
        )
        parser.add_argument(
            "--demo-password",
            default="TapneDemoPass!123",
            help="Password used when --create-missing-hosts creates user rows.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print detailed progress lines for each seeded trip.",
        )

    def _vprint(self, verbose_enabled: bool, message: str) -> None:
        if verbose_enabled:
            self.stdout.write(f"[trips][verbose] {message}")

    def _resolve_host(
        self,
        *,
        username: str,
        create_missing_hosts: bool,
        demo_password: str,
        verbose_enabled: bool,
    ) -> tuple[Any | None, bool]:
        host = cast(Any | None, UserModel.objects.filter(username__iexact=username).first())
        if host:
            if host.username != username:
                host.username = username
                host.save(update_fields=["username"])
                self._vprint(verbose_enabled, f"Normalized host username casing to @{username}")
            return host, False

        if not create_missing_hosts:
            self._vprint(
                verbose_enabled,
                (
                    f"Skipping host @{username}; user does not exist and "
                    "--create-missing-hosts is disabled."
                ),
            )
            return None, False

        host = UserModel.objects.create_user(
            username=username,
            email=f"{username}@tapne.local",
            password=demo_password,
        )
        self._vprint(verbose_enabled, f"Created missing host @{username}")
        return host, True

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        verbose_enabled = bool(options.get("verbose"))
        create_missing_hosts = bool(options.get("create_missing_hosts"))
        demo_password = str(options.get("demo_password") or "TapneDemoPass!123")

        self.stdout.write("Bootstrapping trip catalog records...")
        self._vprint(verbose_enabled, f"create_missing_hosts={create_missing_hosts}")

        created_hosts_count = 0
        created_trips_count = 0
        updated_trips_count = 0
        skipped_trips_count = 0

        now = timezone.localtime(timezone.now()).replace(minute=0, second=0, microsecond=0)

        for seed in DEMO_TRIP_SEEDS:
            host, host_created = self._resolve_host(
                username=seed.host_username,
                create_missing_hosts=create_missing_hosts,
                demo_password=demo_password,
                verbose_enabled=verbose_enabled,
            )
            if host_created:
                created_hosts_count += 1

            if host is None:
                skipped_trips_count += 1
                continue

            starts_at = now + timedelta(days=seed.starts_in_days)
            ends_at = starts_at + timedelta(days=max(1, seed.duration_days))

            trip, created = Trip.objects.update_or_create(
                pk=seed.trip_id,
                defaults={
                    "host": host,
                    "title": seed.title,
                    "summary": seed.summary,
                    "description": seed.description,
                    "destination": seed.destination,
                    "trip_type": seed.trip_type,
                    "budget_tier": seed.budget_tier,
                    "difficulty_level": seed.difficulty_level,
                    "pace_level": seed.pace_level,
                    "group_size_label": seed.group_size_label,
                    "includes_label": (
                        "Host planning support, route guidance, and group coordination. "
                        "Bookings are self-managed by members."
                    ),
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "traffic_score": seed.traffic_score,
                    "is_published": True,
                },
            )

            if created:
                created_trips_count += 1
                self._vprint(verbose_enabled, f"Created trip id={trip.pk} for @{seed.host_username}")
            else:
                updated_trips_count += 1
                self._vprint(verbose_enabled, f"Updated trip id={trip.pk} for @{seed.host_username}")

        self.stdout.write(
            self.style.SUCCESS(
                "Trips bootstrap complete. "
                f"created_hosts={created_hosts_count}, "
                f"created_trips={created_trips_count}, "
                f"updated_trips={updated_trips_count}, "
                f"skipped={skipped_trips_count}"
            )
        )
