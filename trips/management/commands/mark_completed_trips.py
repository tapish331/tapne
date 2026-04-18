from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from trips.models import Trip, ensure_trip_status_fresh


class Command(BaseCommand):
    help = (
        "Sweep trips and run ensure_trip_status_fresh() on every candidate row. "
        "Flips published→completed once starts_at passes, closes pending enrollments, "
        "and sets review_prompts_sent=True once ends_at passes. Safe to run on a "
        "cron (idempotent)."
    )

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        now = timezone.now()
        candidates = list(
            Trip.objects.filter(
                # published rows whose start has passed (status-flip candidates)
                # OR completed rows that haven't yet received review prompts
                # and whose end has passed.
            )
            .filter(
                status__in=[Trip.STATUS_PUBLISHED, Trip.STATUS_COMPLETED],
            )
        )
        status_flipped = 0
        prompts_marked = 0
        for trip in candidates:
            prev_status = trip.status
            prev_prompts = trip.review_prompts_sent
            changed = ensure_trip_status_fresh(trip)
            if not changed:
                continue
            if prev_status == Trip.STATUS_PUBLISHED and trip.status == Trip.STATUS_COMPLETED:
                status_flipped += 1
            if not prev_prompts and trip.review_prompts_sent:
                prompts_marked += 1

        self.stdout.write(
            self.style.SUCCESS(
                "mark_completed_trips done. "
                f"status_flipped={status_flipped}, review_prompts_sent={prompts_marked}, "
                f"now={now.isoformat()}"
            )
        )
