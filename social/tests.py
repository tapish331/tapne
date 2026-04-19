from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from blogs.models import Blog
from feed.models import MemberFeedPreference
from trips.models import Trip

from .models import Bookmark, FollowRelation

UserModel = get_user_model()


class SocialBootstrapCommandTests(TestCase):
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

        Blog.objects.create(
            pk=301,
            author=self.mei,
            slug="packing-for-swing-weather",
            title="Packing for swing-weather trips without overloading",
            excerpt="e",
            body="b",
            is_published=True,
        )
        Blog.objects.create(
            pk=302,
            author=self.arun,
            slug="first-group-trip-ops-checklist",
            title="First group-trip operations checklist",
            excerpt="e",
            body="b",
            is_published=True,
        )
        Blog.objects.create(
            pk=303,
            author=self.sahar,
            slug="how-to-run-a-desert-route",
            title="How to run a desert route without chaos",
            excerpt="e",
            body="b",
            is_published=True,
        )

    def test_bootstrap_social_creates_follows_and_bookmarks_with_verbose_output(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_social", "--verbose", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(FollowRelation.objects.count(), 3)
        self.assertEqual(Bookmark.objects.count(), 9)
        self.assertEqual(MemberFeedPreference.objects.count(), 3)
        self.assertIn("[social][verbose]", output)
        self.assertIn("Social bootstrap complete", output)

    def test_bootstrap_social_can_create_missing_members(self) -> None:
        UserModel.objects.all().delete()
        stdout = StringIO()
        call_command(
            "bootstrap_social",
            "--create-missing-members",
            "--verbose",
            stdout=stdout,
        )
        output = stdout.getvalue()

        self.assertTrue(UserModel.objects.filter(username="mei").exists())
        self.assertTrue(UserModel.objects.filter(username="arun").exists())
        self.assertTrue(UserModel.objects.filter(username="sahar").exists())
        self.assertEqual(FollowRelation.objects.count(), 3)
        self.assertIn("created_members=", output)
