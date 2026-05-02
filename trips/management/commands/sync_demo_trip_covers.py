from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from trips.demo_covers import DEMO_TRIP_COVER_IMAGES, sync_demo_trip_cover_images


class Command(BaseCommand):
    help = "Download the curated Pexels demo trip cover manifest into configured storage."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-download and overwrite curated cover objects even when they already exist.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print source and attribution details for each curated image.",
        )

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        force = bool(options.get("force"))
        verbose = bool(options.get("verbose"))

        self.stdout.write(f"Syncing {len(DEMO_TRIP_COVER_IMAGES)} curated demo trip cover images...")
        results = sync_demo_trip_cover_images(force=force)

        synced_count = 0
        skipped_count = 0
        failed_count = 0
        for result in results:
            if result.status == "synced":
                synced_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[synced] {result.slot}: {result.file_name} ({result.bytes_written} bytes)"
                    )
                )
            elif result.status == "skipped":
                skipped_count += 1
                self.stdout.write(f"[skipped] {result.slot}: {result.file_name}")
            else:
                failed_count += 1
                self.stdout.write(self.style.WARNING(f"[failed] {result.slot}: {result.error}"))

            if verbose:
                entry = next(item for item in DEMO_TRIP_COVER_IMAGES if item.slot == result.slot)
                self.stdout.write(
                    f"  source={entry.source_name}; photographer={entry.photographer}; page={entry.source_url}"
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Demo trip cover sync complete. "
                f"synced={synced_count}, skipped={skipped_count}, failed={failed_count}"
            )
        )
