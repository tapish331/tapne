from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from trips.models import Trip

from .models import EnrollmentRequest

UserModel = get_user_model()


class EnrollmentViewsTests(TestCase):
    def setUp(self) -> None:
        self.password = "EnrollPass!123456"
        self.host = UserModel.objects.create_user(
            username="host-enroll",
            email="host-enroll@example.com",
            password=self.password,
        )
        self.host_two = UserModel.objects.create_user(
            username="host-enroll-two",
            email="host-enroll-two@example.com",
            password=self.password,
        )
        self.member = UserModel.objects.create_user(
            username="member-enroll",
            email="member-enroll@example.com",
            password=self.password,
        )
        self.member_two = UserModel.objects.create_user(
            username="member-enroll-two",
            email="member-enroll-two@example.com",
            password=self.password,
        )

        starts_at = timezone.now() + timedelta(days=10)
        self.trip = Trip.objects.create(
            host=self.host,
            title="Enrollment target trip",
            summary="Trip summary",
            description="Trip description",
            destination="Oslo",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=2),
            traffic_score=33,
            is_published=True,
        )
        self.unpublished_trip = Trip.objects.create(
            host=self.host,
            title="Draft trip",
            summary="Draft summary",
            description="Draft description",
            destination="Helsinki",
            starts_at=starts_at + timedelta(days=5),
            ends_at=starts_at + timedelta(days=7),
            traffic_score=11,
            is_published=False,
        )
        self.other_host_trip = Trip.objects.create(
            host=self.host_two,
            title="Other host trip",
            summary="Trip summary",
            description="Trip description",
            destination="Zurich",
            starts_at=starts_at + timedelta(days=1),
            ends_at=starts_at + timedelta(days=3),
            traffic_score=21,
            is_published=True,
        )

    def test_trip_request_requires_login(self) -> None:
        response = self.client.post(
            reverse("enrollment:trip-request", kwargs={"trip_id": self.trip.pk})
        )
        expected_redirect = (
            f"{reverse('accounts:login')}?next={reverse('enrollment:trip-request', kwargs={'trip_id': self.trip.pk})}"
        )
        self.assertRedirects(response, expected_redirect, fetch_redirect_response=False)

    def test_member_can_submit_join_request_for_published_trip(self) -> None:
        self.client.login(username=self.member.username, password=self.password)

        response = self.client.post(
            reverse("enrollment:trip-request", kwargs={"trip_id": self.trip.pk}),
            {
                "message": "  I can help with logistics   checkpoints. ",
                "next": reverse("trips:detail", kwargs={"trip_id": self.trip.pk}),
            },
        )

        self.assertRedirects(response, reverse("trips:detail", kwargs={"trip_id": self.trip.pk}))
        row = EnrollmentRequest.objects.get(trip=self.trip, requester=self.member)
        self.assertEqual(row.status, EnrollmentRequest.STATUS_PENDING)
        self.assertEqual(row.message, "I can help with logistics checkpoints.")

    def test_trip_request_ajax_returns_json_payload(self) -> None:
        self.client.login(username=self.member.username, password=self.password)

        response = self.client.post(
            reverse("enrollment:trip-request", kwargs={"trip_id": self.trip.pk}),
            {
                "message": "Can share transport checkpoints.",
                "next": reverse("trips:detail", kwargs={"trip_id": self.trip.pk}),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["action"], "trip-request")
        self.assertEqual(payload["trip_id"], self.trip.pk)
        self.assertEqual(payload["outcome"], "created-pending")
        self.assertTrue(payload["is_pending"])
        self.assertFalse(payload["is_approved"])
        row = EnrollmentRequest.objects.get(trip=self.trip, requester=self.member)
        self.assertEqual(payload["request_id"], row.pk)

    def test_duplicate_pending_request_is_idempotent(self) -> None:
        EnrollmentRequest.objects.create(
            trip=self.trip,
            requester=self.member,
            message="Original message",
            status=EnrollmentRequest.STATUS_PENDING,
        )
        self.client.login(username=self.member.username, password=self.password)

        response = self.client.post(
            reverse("enrollment:trip-request", kwargs={"trip_id": self.trip.pk}),
            {"message": "Original message", "next": reverse("trips:list")},
        )

        self.assertRedirects(response, reverse("trips:list"))
        self.assertEqual(
            EnrollmentRequest.objects.filter(trip=self.trip, requester=self.member).count(),
            1,
        )
        row = EnrollmentRequest.objects.get(trip=self.trip, requester=self.member)
        self.assertEqual(row.status, EnrollmentRequest.STATUS_PENDING)

    def test_host_cannot_request_own_trip(self) -> None:
        self.client.login(username=self.host.username, password=self.password)
        response = self.client.post(
            reverse("enrollment:trip-request", kwargs={"trip_id": self.trip.pk}),
            {"next": reverse("trips:detail", kwargs={"trip_id": self.trip.pk})},
        )

        self.assertRedirects(response, reverse("trips:detail", kwargs={"trip_id": self.trip.pk}))
        self.assertFalse(EnrollmentRequest.objects.filter(trip=self.trip, requester=self.host).exists())

    def test_denied_request_is_reopened_to_pending_on_resubmit(self) -> None:
        row = EnrollmentRequest.objects.create(
            trip=self.trip,
            requester=self.member,
            message="Old message",
            status=EnrollmentRequest.STATUS_DENIED,
            reviewed_by=self.host,
            reviewed_at=timezone.now(),
        )
        self.client.login(username=self.member.username, password=self.password)

        response = self.client.post(
            reverse("enrollment:trip-request", kwargs={"trip_id": self.trip.pk}),
            {
                "message": "I can adjust dates and follow trip constraints.",
                "next": reverse("trips:detail", kwargs={"trip_id": self.trip.pk}),
            },
        )

        self.assertRedirects(response, reverse("trips:detail", kwargs={"trip_id": self.trip.pk}))
        row.refresh_from_db()
        self.assertEqual(row.status, EnrollmentRequest.STATUS_PENDING)
        self.assertEqual(row.reviewed_by, None)
        self.assertEqual(row.reviewed_at, None)
        self.assertIn("adjust dates", row.message)

    def test_unpublished_trip_cannot_be_requested(self) -> None:
        self.client.login(username=self.member.username, password=self.password)
        response = self.client.post(
            reverse("enrollment:trip-request", kwargs={"trip_id": self.unpublished_trip.pk}),
            {"next": reverse("trips:list")},
        )

        self.assertRedirects(response, reverse("trips:list"))
        self.assertFalse(
            EnrollmentRequest.objects.filter(
                trip=self.unpublished_trip,
                requester=self.member,
            ).exists()
        )

    def test_trip_request_ajax_unpublished_trip_returns_json_error(self) -> None:
        self.client.login(username=self.member.username, password=self.password)
        response = self.client.post(
            reverse("enrollment:trip-request", kwargs={"trip_id": self.unpublished_trip.pk}),
            {"next": reverse("trips:list")},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["action"], "trip-request")
        self.assertEqual(payload["trip_id"], self.unpublished_trip.pk)
        self.assertEqual(payload["outcome"], "trip-unpublished")

    def test_hosting_inbox_requires_login(self) -> None:
        response = self.client.get(reverse("enrollment:hosting-inbox"))
        expected_redirect = f"{reverse('accounts:login')}?next={reverse('enrollment:hosting-inbox')}"
        self.assertRedirects(response, expected_redirect, fetch_redirect_response=False)

    def test_hosting_inbox_lists_only_requests_for_current_host(self) -> None:
        EnrollmentRequest.objects.create(
            trip=self.trip,
            requester=self.member,
            message="For host one",
            status=EnrollmentRequest.STATUS_PENDING,
        )
        EnrollmentRequest.objects.create(
            trip=self.other_host_trip,
            requester=self.member_two,
            message="For host two",
            status=EnrollmentRequest.STATUS_PENDING,
        )

        self.client.login(username=self.host.username, password=self.password)
        response = self.client.get(reverse("enrollment:hosting-inbox"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["hosting_counts"]["all"], 1)
        self.assertEqual(response.context["hosting_counts"]["pending"], 1)
        self.assertEqual(len(response.context["hosting_requests"]), 1)
        self.assertEqual(response.context["hosting_requests"][0]["requester_username"], self.member.username)

    def test_hosting_inbox_status_filter_works(self) -> None:
        EnrollmentRequest.objects.create(
            trip=self.trip,
            requester=self.member,
            message="Pending row",
            status=EnrollmentRequest.STATUS_PENDING,
        )
        EnrollmentRequest.objects.create(
            trip=self.trip,
            requester=self.member_two,
            message="Approved row",
            status=EnrollmentRequest.STATUS_APPROVED,
            reviewed_by=self.host,
            reviewed_at=timezone.now(),
        )
        another_member = UserModel.objects.create_user(
            username="member-enroll-three",
            email="member-enroll-three@example.com",
            password=self.password,
        )
        EnrollmentRequest.objects.create(
            trip=self.trip,
            requester=another_member,
            message="Denied row",
            status=EnrollmentRequest.STATUS_DENIED,
            reviewed_by=self.host,
            reviewed_at=timezone.now(),
        )

        self.client.login(username=self.host.username, password=self.password)
        response = self.client.get(f"{reverse('enrollment:hosting-inbox')}?status=approved")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_status"], "approved")
        self.assertEqual(len(response.context["hosting_requests"]), 1)
        self.assertEqual(response.context["hosting_requests"][0]["status"], EnrollmentRequest.STATUS_APPROVED)

    def test_host_can_approve_and_deny_join_requests(self) -> None:
        row = EnrollmentRequest.objects.create(
            trip=self.trip,
            requester=self.member,
            message="Pending request",
            status=EnrollmentRequest.STATUS_PENDING,
        )
        self.client.login(username=self.host.username, password=self.password)

        approve_response = self.client.post(
            reverse("enrollment:approve", kwargs={"request_id": row.pk}),
            {"next": reverse("enrollment:hosting-inbox")},
        )
        self.assertRedirects(approve_response, reverse("enrollment:hosting-inbox"))

        row.refresh_from_db()
        self.assertEqual(row.status, EnrollmentRequest.STATUS_APPROVED)
        self.assertEqual(row.reviewed_by, self.host)
        self.assertIsNotNone(row.reviewed_at)

        deny_response = self.client.post(
            reverse("enrollment:deny", kwargs={"request_id": row.pk}),
            {"next": reverse("enrollment:hosting-inbox")},
        )
        self.assertRedirects(deny_response, reverse("enrollment:hosting-inbox"))

        row.refresh_from_db()
        self.assertEqual(row.status, EnrollmentRequest.STATUS_DENIED)
        self.assertEqual(row.reviewed_by, self.host)
        self.assertIsNotNone(row.reviewed_at)

    def test_review_request_is_owner_only(self) -> None:
        row = EnrollmentRequest.objects.create(
            trip=self.trip,
            requester=self.member,
            message="Pending request",
            status=EnrollmentRequest.STATUS_PENDING,
        )
        self.client.login(username=self.host_two.username, password=self.password)

        response = self.client.post(reverse("enrollment:approve", kwargs={"request_id": row.pk}))
        self.assertEqual(response.status_code, 404)

        row.refresh_from_db()
        self.assertEqual(row.status, EnrollmentRequest.STATUS_PENDING)

    def test_hosting_inbox_verbose_query_prints_debug_lines(self) -> None:
        self.client.login(username=self.host.username, password=self.password)

        with patch("builtins.print") as mock_print:
            response = self.client.get(f"{reverse('enrollment:hosting-inbox')}?verbose=1")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(mock_print.call_count, 1)
        printed_lines = "\n".join(str(args[0]) for args, _kwargs in mock_print.call_args_list)
        self.assertIn("[enrollment][verbose]", printed_lines)

    def test_trip_request_without_verbose_does_not_print_debug_lines(self) -> None:
        self.client.login(username=self.member.username, password=self.password)

        with patch("builtins.print") as mock_print:
            response = self.client.post(
                reverse("enrollment:trip-request", kwargs={"trip_id": self.trip.pk}),
                {"next": reverse("trips:list")},
            )

        self.assertRedirects(response, reverse("trips:list"))
        mock_print.assert_not_called()


class EnrollmentBootstrapCommandTests(TestCase):
    def setUp(self) -> None:
        self.demo_password = "DemoPass!12345"
        self.mei = UserModel.objects.create_user(
            username="mei",
            email="mei@example.com",
            password=self.demo_password,
        )
        self.arun = UserModel.objects.create_user(
            username="arun",
            email="arun@example.com",
            password=self.demo_password,
        )
        self.sahar = UserModel.objects.create_user(
            username="sahar",
            email="sahar@example.com",
            password=self.demo_password,
        )
        self.nora = UserModel.objects.create_user(
            username="nora",
            email="nora@example.com",
            password=self.demo_password,
        )
        self.kai = UserModel.objects.create_user(
            username="kai",
            email="kai@example.com",
            password=self.demo_password,
        )
        self.lina = UserModel.objects.create_user(
            username="lina",
            email="lina@example.com",
            password=self.demo_password,
        )

        now = timezone.now()
        Trip.objects.create(
            pk=101,
            host=self.mei,
            title="Kyoto food lanes weekend",
            summary="s",
            description="d",
            destination="Kyoto",
            starts_at=now + timedelta(days=14),
            ends_at=now + timedelta(days=16),
            traffic_score=90,
            is_published=True,
        )
        Trip.objects.create(
            pk=102,
            host=self.arun,
            title="Patagonia first-light trekking camp",
            summary="s",
            description="d",
            destination="Patagonia",
            starts_at=now + timedelta(days=20),
            ends_at=now + timedelta(days=24),
            traffic_score=85,
            is_published=True,
        )
        Trip.objects.create(
            pk=103,
            host=self.sahar,
            title="Morocco souk to desert circuit",
            summary="s",
            description="d",
            destination="Morocco",
            starts_at=now + timedelta(days=28),
            ends_at=now + timedelta(days=32),
            traffic_score=80,
            is_published=True,
        )

    def test_bootstrap_enrollment_seeds_rows_with_verbose_output(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_enrollment", "--verbose", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(EnrollmentRequest.objects.count(), 4)
        self.assertEqual(
            EnrollmentRequest.objects.filter(status=EnrollmentRequest.STATUS_PENDING).count(),
            2,
        )
        self.assertEqual(
            EnrollmentRequest.objects.filter(status=EnrollmentRequest.STATUS_APPROVED).count(),
            1,
        )
        self.assertEqual(
            EnrollmentRequest.objects.filter(status=EnrollmentRequest.STATUS_DENIED).count(),
            1,
        )
        self.assertIn("[enrollment][verbose]", output)
        self.assertIn("Enrollment bootstrap complete", output)

    def test_bootstrap_enrollment_can_create_missing_members(self) -> None:
        EnrollmentRequest.objects.all().delete()
        UserModel.objects.filter(username__in=["nora", "kai", "lina"]).delete()

        stdout = StringIO()
        call_command(
            "bootstrap_enrollment",
            "--create-missing-members",
            "--verbose",
            stdout=stdout,
        )
        output = stdout.getvalue()

        self.assertTrue(UserModel.objects.filter(username="nora").exists())
        self.assertTrue(UserModel.objects.filter(username="kai").exists())
        self.assertTrue(UserModel.objects.filter(username="lina").exists())
        self.assertEqual(EnrollmentRequest.objects.count(), 4)
        self.assertIn("created_members=3", output)

    def test_bootstrap_enrollment_skips_when_members_are_missing(self) -> None:
        EnrollmentRequest.objects.all().delete()
        UserModel.objects.filter(username__in=["nora", "kai", "lina"]).delete()

        stdout = StringIO()
        call_command("bootstrap_enrollment", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(EnrollmentRequest.objects.count(), 0)
        self.assertIn("skipped=4", output)
