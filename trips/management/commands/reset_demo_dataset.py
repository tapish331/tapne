from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction
from django.utils import timezone

from accounts.models import ensure_profile
from enrollment.models import EnrollmentRequest
from trips.models import Trip

UserModel = get_user_model()


DEMO_HOST_USERNAME = "demo_host"
DEMO_TRAVELER_USERNAME = "demo_traveler"

DEMO_HOST_PROFILE = {
    "email": "demo_host@tapne.local",
    "first_name": "Demo",
    "last_name": "Host",
    "display_name": "Demo Host",
    "bio": "Hosts curated trips for Tapne demos.",
    "location": "Bengaluru, India",
}

DEMO_TRAVELER_PROFILE = {
    "email": "demo_traveler@tapne.local",
    "first_name": "Demo",
    "last_name": "Traveler",
    "display_name": "Demo Traveler",
    "bio": "Travels with Tapne.",
    "location": "Mumbai, India",
}


class Command(BaseCommand):
    help = (
        "Reset the demo dataset: delete all trips, recreate demo host + traveler "
        "users, seed 2 drafts + 2 published + 2 completed trips, and approve the "
        "traveler for 1 published + 1 completed trip."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--password",
            default="TapneDemoPass!123",
            help="Password assigned to demo_host and demo_traveler.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the 'this deletes all trips' confirmation prompt.",
        )

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        password = str(options["password"])
        skip_confirm = bool(options.get("yes"))

        if not skip_confirm:
            existing_count = Trip.objects.count()
            self.stdout.write(
                self.style.WARNING(
                    f"About to DELETE {existing_count} Trip rows (cascades enrollments) "
                    "and seed 6 demo trips. Type 'yes' to continue: "
                )
            )
            answer = input().strip().lower()
            if answer != "yes":
                self.stdout.write("Aborted.")
                return

        with transaction.atomic():
            deleted_count, _ = Trip.objects.all().delete()
            self.stdout.write(f"Deleted objects: {deleted_count}")

            host = self._upsert_user(DEMO_HOST_USERNAME, DEMO_HOST_PROFILE, password)
            traveler = self._upsert_user(DEMO_TRAVELER_USERNAME, DEMO_TRAVELER_PROFILE, password)

            now = timezone.now()

            # 2 drafts
            draft_a = Trip.objects.create(
                host=host,
                title="Draft — Himalayan Monastery Circuit",
                summary="Work-in-progress trek itinerary around high-altitude monasteries.",
                destination="Ladakh, India",
                starts_at=now + timedelta(days=45),
                ends_at=now + timedelta(days=52),
                status=Trip.STATUS_DRAFT,
                trip_type="trekking",
                total_seats=8,
                minimum_seats=4,
                currency="INR",
                price_per_person="45000",
                total_trip_price="360000",
            )
            draft_b = Trip.objects.create(
                host=host,
                title="Draft — Kerala Backwaters & Kochi",
                summary="Still finalizing houseboat logistics and cookery class block.",
                destination="Kochi, India",
                starts_at=now + timedelta(days=70),
                ends_at=now + timedelta(days=75),
                status=Trip.STATUS_DRAFT,
                trip_type="food-culture",
                total_seats=10,
                minimum_seats=5,
                currency="INR",
                price_per_person="32000",
                total_trip_price="320000",
            )

            # 2 published (upcoming, bookable)
            published_a = Trip.objects.create(
                host=host,
                title="Goa Coastal Road Trip",
                summary="Four-day Vespa-style loop through North + South Goa beaches and cafes.",
                destination="Goa, India",
                starts_at=now + timedelta(days=15),
                ends_at=now + timedelta(days=19),
                status=Trip.STATUS_PUBLISHED,
                trip_type="coastal",
                total_seats=6,
                minimum_seats=3,
                currency="INR",
                price_per_person="28000",
                total_trip_price="168000",
                traffic_score=80,
            )
            published_b = Trip.objects.create(
                host=host,
                title="Spiti Valley Photo Expedition",
                summary="Eight days across Spiti with golden-hour shoots and local homestays.",
                destination="Spiti, India",
                starts_at=now + timedelta(days=30),
                ends_at=now + timedelta(days=38),
                status=Trip.STATUS_PUBLISHED,
                trip_type="culture-heritage",
                total_seats=8,
                minimum_seats=4,
                currency="INR",
                price_per_person="58000",
                total_trip_price="464000",
                traffic_score=65,
            )

            # 2 completed (already happened)
            completed_a = Trip.objects.create(
                host=host,
                title="Rajasthan Desert Heritage Circuit",
                summary="Jaisalmer to Jodhpur desert route with palace stays.",
                destination="Rajasthan, India",
                starts_at=now - timedelta(days=30),
                ends_at=now - timedelta(days=24),
                status=Trip.STATUS_COMPLETED,
                review_prompts_sent=False,
                trip_type="desert",
                total_seats=10,
                minimum_seats=5,
                currency="INR",
                price_per_person="38000",
                total_trip_price="380000",
            )
            completed_b = Trip.objects.create(
                host=host,
                title="Meghalaya Living Root Bridges",
                summary="Double-decker root bridge trek + Cherrapunji waterfalls.",
                destination="Meghalaya, India",
                starts_at=now - timedelta(days=60),
                ends_at=now - timedelta(days=54),
                status=Trip.STATUS_COMPLETED,
                review_prompts_sent=False,
                trip_type="trekking",
                total_seats=6,
                minimum_seats=3,
                currency="INR",
                price_per_person="42000",
                total_trip_price="252000",
            )

            # Demo traveler joins 1 published + 1 completed — approved by host.
            for trip in (published_a, completed_a):
                EnrollmentRequest.objects.create(
                    trip=trip,
                    requester=traveler,
                    status=EnrollmentRequest.STATUS_APPROVED,
                    reviewed_by=host,
                    reviewed_at=timezone.now(),
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Demo dataset ready.\n"
                f"  Users: @{DEMO_HOST_USERNAME} (host), @{DEMO_TRAVELER_USERNAME} (traveler)\n"
                f"  Password: {password}\n"
                f"  Trips: 2 drafts, 2 published, 2 completed (total 6)\n"
                f"  Enrollments: @{DEMO_TRAVELER_USERNAME} approved on "
                f"'{published_a.title}' and '{completed_a.title}'.\n"
                "Run `python manage.py mark_completed_trips` to fire review prompts."
            )
        )

    def _upsert_user(self, username: str, profile: dict, password: str):  # type: ignore[no-untyped-def]
        user = UserModel.objects.filter(username__iexact=username).first()
        if user is None:
            user = UserModel.objects.create_user(
                username=username,
                email=profile["email"],
                first_name=profile["first_name"],
                last_name=profile["last_name"],
            )
            user.set_password(password)
            user.save()
        else:
            user.email = profile["email"]
            user.first_name = profile["first_name"]
            user.last_name = profile["last_name"]
            user.set_password(password)
            user.save()

        profile_row = ensure_profile(user)
        profile_row.display_name = profile["display_name"]
        profile_row.bio = profile["bio"]
        profile_row.location = profile["location"]
        profile_row.save()
        return user
