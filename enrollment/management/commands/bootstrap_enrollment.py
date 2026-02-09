from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from enrollment.models import EnrollmentRequest
from trips.models import Trip

UserModel = get_user_model()


@dataclass(frozen=True)
class EnrollmentSeed:
    member_username: str
    trip_id: int
    status: str
    message: str


DEMO_ENROLLMENT_SEEDS: tuple[EnrollmentSeed, ...] = (
    EnrollmentSeed(
        member_username="nora",
        trip_id=101,
        status=EnrollmentRequest.STATUS_PENDING,
        message="Can I join for the weekend food route?",
    ),
    EnrollmentSeed(
        member_username="kai",
        trip_id=101,
        status=EnrollmentRequest.STATUS_APPROVED,
        message="I have hosted small city walks and can follow your schedule exactly.",
    ),
    EnrollmentSeed(
        member_username="lina",
        trip_id=102,
        status=EnrollmentRequest.STATUS_DENIED,
        message="I need flexible start windows due to transit uncertainty.",
    ),
    EnrollmentSeed(
        member_username="nora",
        trip_id=103,
        status=EnrollmentRequest.STATUS_PENDING,
        message="Interested in the market-to-desert logistics flow and camp setup.",
    ),
)


class Command(BaseCommand):
    help = "Create or refresh demo enrollment request rows for host inbox flows."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--create-missing-members",
            action="store_true",
            help="Create missing seed members before applying enrollment seeds.",
        )
        parser.add_argument(
            "--demo-password",
            default="TapneDemoPass!123",
            help="Password used when --create-missing-members creates users.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print detailed progress lines for each enrollment seed.",
        )

    def _vprint(self, verbose_enabled: bool, message: str) -> None:
        if verbose_enabled:
            self.stdout.write(f"[enrollment][verbose] {message}")

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
                self._vprint(verbose_enabled, f"Normalized member username casing to @{username}")
            return member, False

        if not create_missing_members:
            self._vprint(
                verbose_enabled,
                (
                    f"Skipping @{username}; user does not exist and "
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

        self.stdout.write("Bootstrapping enrollment request records...")
        self._vprint(verbose_enabled, f"create_missing_members={create_missing_members}")

        created_members_count = 0
        created_requests_count = 0
        updated_requests_count = 0
        skipped_requests_count = 0
        now = timezone.now()

        for seed in DEMO_ENROLLMENT_SEEDS:
            member, member_created = self._resolve_member(
                username=seed.member_username,
                create_missing_members=create_missing_members,
                demo_password=demo_password,
                verbose_enabled=verbose_enabled,
            )
            if member_created:
                created_members_count += 1

            if member is None:
                skipped_requests_count += 1
                continue

            trip = Trip.objects.select_related("host").filter(pk=seed.trip_id).first()
            if trip is None:
                skipped_requests_count += 1
                self._vprint(
                    verbose_enabled,
                    f"Skipping seed for @{seed.member_username}; trip id={seed.trip_id} does not exist.",
                )
                continue

            if int(getattr(trip, "host_id", 0) or 0) == int(getattr(member, "pk", 0) or 0):
                skipped_requests_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Skipping seed because member=@{member} is host for trip id={trip_id}".format(
                            member=seed.member_username,
                            trip_id=seed.trip_id,
                        )
                    ),
                )
                continue

            reviewed_by = trip.host if seed.status in {
                EnrollmentRequest.STATUS_APPROVED,
                EnrollmentRequest.STATUS_DENIED,
            } else None
            reviewed_at = now if reviewed_by is not None else None

            request_row, created = EnrollmentRequest.objects.update_or_create(
                trip=trip,
                requester=member,
                defaults={
                    "message": seed.message,
                    "status": seed.status,
                    "reviewed_by": reviewed_by,
                    "reviewed_at": reviewed_at,
                },
            )

            if created:
                created_requests_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Created enrollment request id={request_id}; member=@{member}; trip_id={trip_id}; status={status}"
                        .format(
                            request_id=request_row.pk,
                            member=seed.member_username,
                            trip_id=seed.trip_id,
                            status=seed.status,
                        )
                    ),
                )
            else:
                updated_requests_count += 1
                self._vprint(
                    verbose_enabled,
                    (
                        "Updated enrollment request id={request_id}; member=@{member}; trip_id={trip_id}; status={status}"
                        .format(
                            request_id=request_row.pk,
                            member=seed.member_username,
                            trip_id=seed.trip_id,
                            status=seed.status,
                        )
                    ),
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Enrollment bootstrap complete. "
                f"created_members={created_members_count}, "
                f"created_requests={created_requests_count}, "
                f"updated_requests={updated_requests_count}, "
                f"skipped={skipped_requests_count}"
            )
        )
