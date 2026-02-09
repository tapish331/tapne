from __future__ import annotations

from datetime import datetime
from typing import Any, Final, Literal, TypedDict, cast

from django.conf import settings
from django.db import models
from django.utils import timezone

from trips.models import Trip

EnrollmentStatus = Literal["pending", "approved", "denied"]
SubmitJoinRequestOutcome = Literal[
    "member-required",
    "invalid-member",
    "host-self-request-blocked",
    "created-pending",
    "already-pending",
    "already-approved",
    "reopened-pending",
]
EnrollmentDecisionOutcome = Literal[
    "not-host",
    "already-approved",
    "already-denied",
    "approved",
    "denied",
]

VALID_HOSTING_INBOX_FILTERS: Final[set[str]] = {"all", "pending", "approved", "denied"}


class EnrollmentRequestData(TypedDict):
    id: int
    trip_id: int
    trip_title: str
    trip_destination: str
    trip_url: str
    requester_username: str
    message: str
    status: str
    created_at: datetime
    reviewed_at: datetime | None
    reviewed_by_username: str


class HostingInboxPayload(TypedDict):
    requests: list[EnrollmentRequestData]
    counts: dict[str, int]
    mode: str
    reason: str
    active_status: str


class EnrollmentRequest(models.Model):
    """
    Member request to join a hosted trip.

    Status lifecycle is intentionally small and explicit for operational clarity:
    pending -> approved | denied
    """

    STATUS_PENDING: Final = "pending"
    STATUS_APPROVED: Final = "approved"
    STATUS_DENIED: Final = "denied"
    STATUS_CHOICES: Final[tuple[tuple[str, str], ...]] = (
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_DENIED, "Denied"),
    )

    trip = models.ForeignKey(
        Trip,
        on_delete=models.CASCADE,
        related_name="enrollment_requests",
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trip_enrollment_requests",
    )
    message = models.CharField(
        max_length=500,
        blank=True,
        help_text="Optional member note shown to the host in hosting inbox.",
    )
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_enrollment_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("trip", "requester"),
                name="enrollment_unique_trip_requester",
            )
        ]
        indexes = [
            models.Index(fields=("trip", "status", "created_at"), name="enroll_trip_status_idx"),
            models.Index(fields=("requester", "status", "created_at"), name="enroll_req_status_idx"),
            models.Index(fields=("status", "created_at"), name="enroll_status_created_idx"),
        ]

    def __str__(self) -> str:
        trip_id = int(getattr(getattr(self, "trip", None), "pk", 0) or 0)
        requester_username = str(getattr(self.requester, "username", "") or "").strip()
        trip_title = str(getattr(self.trip, "title", "") or "").strip() or f"Trip #{trip_id}"
        return f"Join request @{requester_username} -> {trip_title} ({self.status})"

    def to_enrollment_request_data(self) -> EnrollmentRequestData:
        trip_id = int(getattr(getattr(self, "trip", None), "pk", 0) or 0)
        requester_username = str(getattr(self.requester, "username", "") or "").strip()
        reviewed_by_username = str(getattr(getattr(self, "reviewed_by", None), "username", "") or "").strip()
        trip_title = str(getattr(self.trip, "title", "") or "").strip() or f"Trip #{trip_id}"
        get_absolute_url = getattr(self.trip, "get_absolute_url", None)
        trip_url = f"/trips/{trip_id}/" if trip_id > 0 else "/trips/"
        if callable(get_absolute_url):
            maybe_url = get_absolute_url()
            if isinstance(maybe_url, str) and maybe_url.strip():
                trip_url = maybe_url

        return {
            "id": int(self.pk or 0),
            "trip_id": trip_id,
            "trip_title": trip_title,
            "trip_destination": str(getattr(self.trip, "destination", "") or "").strip(),
            "trip_url": trip_url,
            "requester_username": requester_username,
            "message": str(self.message or "").strip(),
            "status": str(self.status or "").strip().lower(),
            "created_at": self.created_at,
            "reviewed_at": self.reviewed_at,
            "reviewed_by_username": reviewed_by_username,
        }


def normalize_hosting_inbox_filter(raw_status: object) -> str:
    normalized = str(raw_status or "").strip().lower()
    if normalized in VALID_HOSTING_INBOX_FILTERS:
        return normalized
    return EnrollmentRequest.STATUS_PENDING


def _clean_message(raw_message: object) -> str:
    # Persist predictable single-space separated text for reliable equality checks.
    return " ".join(str(raw_message or "").strip().split())


def submit_join_request(
    *,
    member: object,
    trip: Trip,
    message: object = "",
) -> tuple[EnrollmentRequest | None, SubmitJoinRequestOutcome]:
    if not bool(getattr(member, "is_authenticated", False)):
        return None, "member-required"

    member_id = int(getattr(member, "pk", 0) or 0)
    if member_id <= 0:
        return None, "invalid-member"

    trip_host_id = int(getattr(trip, "host_id", 0) or 0)
    if trip_host_id == member_id:
        return None, "host-self-request-blocked"

    cleaned_message = _clean_message(message)
    request_row, created = EnrollmentRequest.objects.get_or_create(
        trip=trip,
        requester=cast(Any, member),
        defaults={
            "message": cleaned_message,
            "status": EnrollmentRequest.STATUS_PENDING,
            "reviewed_by": None,
            "reviewed_at": None,
        },
    )

    if created:
        return request_row, "created-pending"

    if request_row.status == EnrollmentRequest.STATUS_PENDING:
        if cleaned_message and request_row.message != cleaned_message:
            request_row.message = cleaned_message
            request_row.save(update_fields=["message", "updated_at"])
        return request_row, "already-pending"

    if request_row.status == EnrollmentRequest.STATUS_APPROVED:
        if cleaned_message and request_row.message != cleaned_message:
            request_row.message = cleaned_message
            request_row.save(update_fields=["message", "updated_at"])
        return request_row, "already-approved"

    request_row.status = EnrollmentRequest.STATUS_PENDING
    request_row.reviewed_by = None
    request_row.reviewed_at = None
    request_row.message = cleaned_message
    request_row.save(update_fields=["status", "reviewed_by", "reviewed_at", "message", "updated_at"])
    return request_row, "reopened-pending"


def apply_enrollment_decision(
    *,
    request_row: EnrollmentRequest,
    host: object,
    decision: str,
) -> EnrollmentDecisionOutcome:
    host_id = int(getattr(host, "pk", 0) or 0)
    if host_id <= 0 or int(getattr(request_row.trip, "host_id", 0) or 0) != host_id:
        return "not-host"

    normalized_decision = decision.strip().lower()
    target_status: EnrollmentStatus = (
        cast(EnrollmentStatus, EnrollmentRequest.STATUS_APPROVED)
        if normalized_decision == "approve"
        else cast(EnrollmentStatus, EnrollmentRequest.STATUS_DENIED)
    )

    if request_row.status == target_status:
        return "already-approved" if target_status == EnrollmentRequest.STATUS_APPROVED else "already-denied"

    request_row.status = target_status
    request_row.reviewed_by = cast(Any, host)
    request_row.reviewed_at = timezone.now()
    request_row.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    return "approved" if target_status == EnrollmentRequest.STATUS_APPROVED else "denied"


def build_hosting_inbox_payload_for_member(
    member: object,
    *,
    status: object = EnrollmentRequest.STATUS_PENDING,
    limit: int = 100,
) -> HostingInboxPayload:
    active_status = normalize_hosting_inbox_filter(status)
    if not bool(getattr(member, "is_authenticated", False)):
        return {
            "requests": [],
            "counts": {"all": 0, "pending": 0, "approved": 0, "denied": 0},
            "mode": "guest-not-allowed",
            "reason": "Hosting inbox is available for members only.",
            "active_status": active_status,
        }

    member_id = int(getattr(member, "pk", 0) or 0)
    if member_id <= 0:
        return {
            "requests": [],
            "counts": {"all": 0, "pending": 0, "approved": 0, "denied": 0},
            "mode": "member-hosting-inbox",
            "reason": "No hosting request records are available for this account.",
            "active_status": active_status,
        }

    effective_limit = max(1, int(limit or 100))
    base_queryset = EnrollmentRequest.objects.select_related("trip", "requester", "reviewed_by").filter(
        trip__host_id=member_id
    )

    counts = {
        "all": base_queryset.count(),
        "pending": base_queryset.filter(status=EnrollmentRequest.STATUS_PENDING).count(),
        "approved": base_queryset.filter(status=EnrollmentRequest.STATUS_APPROVED).count(),
        "denied": base_queryset.filter(status=EnrollmentRequest.STATUS_DENIED).count(),
    }

    filtered_queryset = base_queryset.order_by("-created_at", "-pk")
    if active_status != "all":
        filtered_queryset = filtered_queryset.filter(status=active_status)

    rows = [item.to_enrollment_request_data() for item in filtered_queryset[:effective_limit]]
    reason = "Hosting inbox ordered by newest requests first."
    if counts["all"] == 0:
        reason = "No join requests yet for your hosted trips."
    elif active_status != "all":
        reason = f"Showing {active_status} requests for your hosted trips."

    return {
        "requests": rows,
        "counts": counts,
        "mode": "member-hosting-inbox",
        "reason": reason,
        "active_status": active_status,
    }
