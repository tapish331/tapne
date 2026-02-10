from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser

from reviews.models import submit_review

UserModel = get_user_model()


@dataclass(frozen=True)
class ReviewSeed:
    member_username: str
    target_type: str
    target_id: str
    rating: int
    headline: str
    body: str


DEMO_REVIEW_SEEDS: tuple[ReviewSeed, ...] = (
    ReviewSeed(
        member_username="mei",
        target_type="trip",
        target_id="101",
        rating=5,
        headline="Excellent host pacing",
        body="Logistics were clear and the route pacing stayed realistic for mixed experience levels.",
    ),
    ReviewSeed(
        member_username="arun",
        target_type="trip",
        target_id="101",
        rating=4,
        headline="Strong route design",
        body="Good checkpoint sequencing and clear fallback plans for weather shifts.",
    ),
    ReviewSeed(
        member_username="sahar",
        target_type="trip",
        target_id="102",
        rating=5,
        headline="Great alpine workflow",
        body="The host communication cadence made long-day handoffs easy to follow.",
    ),
    ReviewSeed(
        member_username="mei",
        target_type="blog",
        target_id="packing-for-swing-weather",
        rating=5,
        headline="Practical and concise",
        body="The layering framework is immediately usable and avoids overpacking.",
    ),
)


class Command(BaseCommand):
    help = "Create or refresh demo review rows for trip/blog targets."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--create-missing-members",
            action="store_true",
            help="Create missing demo members before applying review seeds.",
        )
        parser.add_argument(
            "--demo-password",
            default="TapneDemoPass!123",
            help="Password used when --create-missing-members creates user rows.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print detailed progress for each review seed operation.",
        )

    def _vprint(self, verbose_enabled: bool, message: str) -> None:
        if verbose_enabled:
            self.stdout.write(f"[reviews][verbose] {message}")

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

        self.stdout.write("Bootstrapping reviews for trips and blogs...")
        self._vprint(verbose_enabled, f"create_missing_members={create_missing_members}")

        created_members_count = 0
        created_reviews_count = 0
        updated_reviews_count = 0
        skipped_reviews_count = 0

        member_cache: dict[str, Any | None] = {}

        def get_member(username: str) -> Any | None:
            nonlocal created_members_count
            cache_key = username.lower()
            if cache_key in member_cache:
                return member_cache[cache_key]

            member, created = self._resolve_member(
                username=username,
                create_missing_members=create_missing_members,
                demo_password=demo_password,
                verbose_enabled=verbose_enabled,
            )
            if created:
                created_members_count += 1
            member_cache[cache_key] = member
            return member

        for seed in DEMO_REVIEW_SEEDS:
            member = get_member(seed.member_username)
            if member is None:
                skipped_reviews_count += 1
                continue

            review_row, outcome, target = submit_review(
                member=member,
                target_type=seed.target_type,
                target_id=seed.target_id,
                rating=seed.rating,
                headline=seed.headline,
                body=seed.body,
            )

            if outcome == "created":
                created_reviews_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Created review member=@{member}; target={target}; review_id={review_id}; rating={rating}"
                        .format(
                            member=seed.member_username,
                            target=(f"{target.target_type}:{target.target_key}" if target is not None else "n/a"),
                            review_id=(review_row.pk if review_row is not None else "n/a"),
                            rating=seed.rating,
                        )
                    ),
                )
            elif outcome == "updated":
                updated_reviews_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Updated review member=@{member}; target={target}; review_id={review_id}; rating={rating}"
                        .format(
                            member=seed.member_username,
                            target=(f"{target.target_type}:{target.target_key}" if target is not None else "n/a"),
                            review_id=(review_row.pk if review_row is not None else "n/a"),
                            rating=seed.rating,
                        )
                    ),
                )
            else:
                skipped_reviews_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Skipped review member=@{member}; target_type={target_type}; target_id={target_id}; outcome={outcome}"
                        .format(
                            member=seed.member_username,
                            target_type=seed.target_type,
                            target_id=seed.target_id,
                            outcome=outcome,
                        )
                    ),
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Reviews bootstrap complete. "
                f"created_members={created_members_count}, "
                f"created_reviews={created_reviews_count}, "
                f"updated_reviews={updated_reviews_count}, "
                f"skipped_reviews={skipped_reviews_count}"
            )
        )
