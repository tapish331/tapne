from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from blogs.models import Blog
from trips.models import Trip

from .models import Review

UserModel = get_user_model()


class ReviewsBootstrapCommandTests(TestCase):
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
        Blog.objects.create(
            author=self.mei,
            slug="packing-for-swing-weather",
            title="Packing for swing-weather trips without overloading",
            excerpt="e",
            body="b",
            is_published=True,
        )
        Blog.objects.create(
            author=self.sahar,
            slug="how-to-run-a-desert-route",
            title="How to run a desert route without chaos",
            excerpt="e",
            body="b",
            is_published=True,
        )

    def test_bootstrap_reviews_seeds_rows_with_verbose_output(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_reviews", "--verbose", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(Review.objects.count(), 4)
        self.assertIn("[reviews][verbose]", output)
        self.assertIn("Reviews bootstrap complete", output)

    def test_bootstrap_reviews_can_create_missing_members(self) -> None:
        Review.objects.all().delete()
        UserModel.objects.filter(username__in=["mei", "arun", "sahar"]).delete()

        stdout = StringIO()
        call_command(
            "bootstrap_reviews",
            "--create-missing-members",
            "--verbose",
            stdout=stdout,
        )
        output = stdout.getvalue()

        self.assertTrue(UserModel.objects.filter(username="mei").exists())
        self.assertTrue(UserModel.objects.filter(username="arun").exists())
        self.assertTrue(UserModel.objects.filter(username="sahar").exists())
        self.assertEqual(Review.objects.count(), 4)
        self.assertIn("created_members=3", output)

    def test_bootstrap_reviews_skips_when_members_are_missing(self) -> None:
        Review.objects.all().delete()
        UserModel.objects.filter(username__in=["mei", "arun", "sahar"]).delete()

        stdout = StringIO()
        call_command("bootstrap_reviews", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(Review.objects.count(), 0)
        self.assertIn("skipped_reviews=4", output)
