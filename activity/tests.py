from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from blogs.models import Blog
from enrollment.models import EnrollmentRequest
from interactions.models import Comment
from reviews.models import Review
from social.models import Bookmark, FollowRelation
from trips.models import Trip

UserModel = get_user_model()


class ActivityBootstrapCommandTests(TestCase):
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

        now = timezone.now()
        Trip.objects.create(
            pk=101,
            host=self.mei,
            title="Kyoto food lanes weekend",
            summary="s",
            description="d",
            destination="Kyoto",
            starts_at=now + timedelta(days=10),
            ends_at=now + timedelta(days=12),
            traffic_score=80,
            is_published=True,
        )
        Trip.objects.create(
            pk=102,
            host=self.arun,
            title="Patagonia first-light trekking camp",
            summary="s",
            description="d",
            destination="Patagonia",
            starts_at=now + timedelta(days=15),
            ends_at=now + timedelta(days=18),
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
            starts_at=now + timedelta(days=20),
            ends_at=now + timedelta(days=23),
            traffic_score=83,
            is_published=True,
        )
        Blog.objects.create(
            author=self.mei,
            slug="packing-for-swing-weather",
            title="Packing for swing-weather trips without overloading",
            excerpt="e",
            body="b",
            is_published=True,
        )

    def test_bootstrap_activity_seeds_rows_with_verbose_output(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_activity", "--verbose", stdout=stdout)
        output = stdout.getvalue()

        self.assertIn("[activity][verbose]", output)
        self.assertIn("Activity bootstrap complete", output)
        self.assertEqual(FollowRelation.objects.filter(following=self.mei).count(), 3)
        self.assertEqual(
            EnrollmentRequest.objects.filter(
                requester=self.mei,
                status__in=[EnrollmentRequest.STATUS_APPROVED, EnrollmentRequest.STATUS_DENIED],
            ).count(),
            2,
        )
        self.assertEqual(Bookmark.objects.count(), 3)
        self.assertEqual(Review.objects.count(), 2)
        self.assertEqual(Comment.objects.filter(parent__isnull=True).count(), 2)
        self.assertEqual(Comment.objects.filter(parent__isnull=False).count(), 1)

    def test_bootstrap_activity_can_create_missing_members(self) -> None:
        UserModel.objects.all().delete()
        stdout = StringIO()
        call_command(
            "bootstrap_activity",
            "--create-missing-members",
            "--verbose",
            stdout=stdout,
        )
        output = stdout.getvalue()

        self.assertTrue(UserModel.objects.filter(username="mei").exists())
        self.assertTrue(UserModel.objects.filter(username="arun").exists())
        self.assertTrue(UserModel.objects.filter(username="sahar").exists())
        self.assertTrue(UserModel.objects.filter(username="nora").exists())
        self.assertIn("created_members=", output)
        self.assertIn("Activity bootstrap complete", output)
