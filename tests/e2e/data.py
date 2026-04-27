from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import django

from tests.e2e.auth import DEFAULT_DEMO_PASSWORD
from tests.e2e.server import build_server_env

_DJANGO_READY = False


def _setup_django() -> None:
    global _DJANGO_READY
    if _DJANGO_READY:
        return

    env = build_server_env()
    for key, value in env.items():
        os.environ.setdefault(key, value)
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tapne.settings")
    django.setup()
    _DJANGO_READY = True


def _slug(prefix: str) -> str:
    parts = [
        "".join(char.lower() if char.isalnum() else "-" for char in prefix).strip("-")
    ]
    normalized = "-".join(part for part in parts if part)
    return normalized or "guardrail"


def unique_username(prefix: str) -> str:
    return f"{_slug(prefix)[:18]}-{uuid4().hex[:8]}"


def ensure_member(
    *,
    username: str,
    display_name: str | None = None,
    password: str = DEFAULT_DEMO_PASSWORD,
) -> str:
    _setup_django()

    from django.contrib.auth import get_user_model

    from accounts.models import ensure_profile

    UserModel = get_user_model()
    email = f"{username}@example.com"
    user, _created = UserModel.objects.get_or_create(  # type: ignore[call-arg]
        username=username,
        defaults={
            "email": email,
            "first_name": (display_name or username).split()[0],
            "is_active": True,
        },
    )

    dirty_fields: list[str] = []
    if str(getattr(user, "email", "") or "").strip().lower() != email:
        user.email = email  # type: ignore[assignment]
        dirty_fields.append("email")
    if not bool(getattr(user, "is_active", False)):
        user.is_active = True  # type: ignore[assignment]
        dirty_fields.append("is_active")
    if display_name:
        expected_first_name = display_name.split()[0]
        if str(getattr(user, "first_name", "") or "").strip() != expected_first_name:
            user.first_name = expected_first_name  # type: ignore[assignment]
            dirty_fields.append("first_name")
    if dirty_fields:
        user.save(update_fields=dirty_fields)

    user.set_password(password)
    user.save(update_fields=["password"])

    profile = ensure_profile(user)
    if display_name and str(getattr(profile, "display_name", "") or "").strip() != display_name:
        profile.display_name = display_name  # type: ignore[assignment]
        profile.save(update_fields=["display_name"])

    return username


def ensure_follow_state(
    *,
    follower_username: str,
    following_username: str,
    is_following: bool,
) -> None:
    _setup_django()

    from django.contrib.auth import get_user_model

    from social.models import FollowRelation

    UserModel = get_user_model()
    follower = UserModel.objects.get(username=follower_username)
    following = UserModel.objects.get(username=following_username)

    if is_following:
        FollowRelation.objects.get_or_create(follower=follower, following=following)
        return

    FollowRelation.objects.filter(follower=follower, following=following).delete()


def ensure_bookmark_state(
    *,
    username: str,
    trip_id: int,
    bookmarked: bool,
) -> None:
    _setup_django()

    from django.contrib.auth import get_user_model

    from social.models import Bookmark, resolve_bookmark_target

    UserModel = get_user_model()
    member = UserModel.objects.get(username=username)

    if bookmarked:
        resolution = resolve_bookmark_target("trip", trip_id)
        if resolution is None:
            raise ValueError(f"Trip {trip_id} is not bookmarkable.")
        Bookmark.objects.get_or_create(
            member=member,
            target_type=Bookmark.TARGET_TRIP,
            target_key=resolution.target_key,
            defaults={
                "target_label": resolution.target_label,
                "target_url": resolution.target_url,
            },
        )
        return

    Bookmark.objects.filter(
        member=member,
        target_type=Bookmark.TARGET_TRIP,
        target_key=str(trip_id),
    ).delete()


def create_trip(
    *,
    host_username: str,
    title: str,
    access_type: str = "open",
    is_published: bool = True,
    booking_status: str = "open",
) -> int:
    _setup_django()

    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from trips.models import Trip

    UserModel = get_user_model()
    host = UserModel.objects.get(username=host_username)
    starts_at = timezone.now() + timedelta(days=30)
    ends_at = starts_at + timedelta(days=4)
    booking_closes_at = starts_at - timedelta(days=7)

    trip = Trip(
        host=host,
        title=title,
        summary="Guardrail scenario trip.",
        description="Guardrail scenario trip for end-to-end coverage.",
        destination="Guardrail Valley",
        trip_type="road-trip",
        starts_at=starts_at,
        ends_at=ends_at,
        booking_closes_at=booking_closes_at,
        total_seats=6,
        minimum_seats=2,
        currency="INR",
        price_per_person=Decimal("18000.00"),
        total_trip_price=Decimal("18000.00"),
        payment_terms="full",
        access_type=access_type,
        payment_method="direct_contact",
        is_published=is_published,
        draft_form_data={"booking_status": booking_status},
    )
    trip.full_clean()
    trip.save()
    return int(trip.pk or 0)


def set_enrollment_status(
    *,
    trip_id: int,
    requester_username: str,
    status: str,
    message: str,
) -> int:
    _setup_django()

    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from enrollment.models import EnrollmentRequest
    from trips.models import Trip

    if status not in {
        EnrollmentRequest.STATUS_PENDING,
        EnrollmentRequest.STATUS_APPROVED,
        EnrollmentRequest.STATUS_DENIED,
    }:
        raise ValueError(f"Unsupported enrollment status: {status}")

    UserModel = get_user_model()
    trip = Trip.objects.get(pk=trip_id)
    requester = UserModel.objects.get(username=requester_username)
    request_row, _created = EnrollmentRequest.objects.get_or_create(
        trip=trip,
        requester=requester,
        defaults={
            "message": message,
            "status": status,
            "reviewed_by": trip.host if status != EnrollmentRequest.STATUS_PENDING else None,
            "reviewed_at": timezone.now() if status != EnrollmentRequest.STATUS_PENDING else None,
        },
    )
    request_row.message = message
    request_row.status = status
    if status == EnrollmentRequest.STATUS_PENDING:
        request_row.reviewed_by = None
        request_row.reviewed_at = None
    else:
        request_row.reviewed_by = trip.host
        request_row.reviewed_at = timezone.now()
    request_row.save(update_fields=["message", "status", "reviewed_by", "reviewed_at", "updated_at"])
    return int(request_row.pk or 0)


@dataclass(frozen=True)
class BookingScenario:
    trip_id: int
    title: str
    traveler_username: str


@dataclass(frozen=True)
class ManageTripScenario:
    trip_id: int
    title: str
    host_username: str
    pending_username: str
    pending_display_name: str
    participant_username: str
    participant_display_name: str


def create_booking_scenario(*, name: str, host_username: str = "mei") -> BookingScenario:
    traveler_username = unique_username(f"{name}-traveler")
    ensure_member(username=traveler_username, display_name="Booking Traveler")
    title = f"Guardrail Booking {uuid4().hex[:6]}"
    trip_id = create_trip(host_username=host_username, title=title, access_type="open")
    return BookingScenario(trip_id=trip_id, title=title, traveler_username=traveler_username)


def create_manage_trip_scenario(*, name: str, host_username: str = "mei") -> ManageTripScenario:
    pending_display_name = "Pending Traveler"
    participant_display_name = "Confirmed Traveler"
    pending_username = unique_username(f"{name}-pending")
    participant_username = unique_username(f"{name}-participant")
    ensure_member(username=pending_username, display_name=pending_display_name)
    ensure_member(username=participant_username, display_name=participant_display_name)

    title = f"Guardrail Manage {uuid4().hex[:6]}"
    trip_id = create_trip(host_username=host_username, title=title, access_type="apply")
    set_enrollment_status(
        trip_id=trip_id,
        requester_username=pending_username,
        status="pending",
        message="I'd love to join this guardrail trip.",
    )
    set_enrollment_status(
        trip_id=trip_id,
        requester_username=participant_username,
        status="approved",
        message="Confirmed for the guardrail trip.",
    )

    return ManageTripScenario(
        trip_id=trip_id,
        title=title,
        host_username=host_username,
        pending_username=pending_username,
        pending_display_name=pending_display_name,
        participant_username=participant_username,
        participant_display_name=participant_display_name,
    )
