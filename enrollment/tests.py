from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from trips.models import Trip

from .models import EnrollmentRequest

UserModel = get_user_model()


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
