from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from blogs.models import Blog
from social.models import Bookmark
from trips.models import Trip

from .models import MemberFeedPreference, build_home_payload_for_user

UserModel = get_user_model()


class HomePayloadCatalogTests(TestCase):
    @override_settings(TAPNE_ENABLE_DEMO_DATA=True, TAPNE_DEMO_CATALOG_VISIBLE=True)
    def test_home_prefers_live_catalog_rows_when_demo_fallback_is_enabled(self) -> None:
        user = UserModel.objects.create_user(
            username="live-host",
            email="live-host@example.com",
            password="DemoPass!12345",
        )
        Trip.objects.create(
            host=user,
            title="Live seeded coastal trip",
            summary="A persisted row from the local demo catalog.",
            destination="Goa",
            starts_at=timezone.now() + timedelta(days=10),
            status=Trip.STATUS_PUBLISHED,
            is_published=True,
        )
        Blog.objects.create(
            author=user,
            slug="live-seeded-story",
            title="Live seeded story",
            excerpt="A persisted story from the local demo catalog.",
            body="Live story body.",
            is_published=True,
        )

        payload = build_home_payload_for_user(AnonymousUser(), limit_per_section=None)

        self.assertEqual(payload["mode"], "guest-trending-live")
        self.assertEqual([trip["title"] for trip in payload["trips"]], ["Live seeded coastal trip"])
        self.assertEqual([blog["title"] for blog in payload["blogs"]], ["Live seeded story"])

    @override_settings(TAPNE_ENABLE_DEMO_DATA=True, TAPNE_DEMO_CATALOG_VISIBLE=True)
    def test_home_uses_demo_fallback_when_no_live_trips_or_blogs_exist(self) -> None:
        UserModel.objects.create_user(
            username="profile-only",
            email="profile-only@example.com",
            password="DemoPass!12345",
        )

        payload = build_home_payload_for_user(AnonymousUser(), limit_per_section=None)

        self.assertEqual(payload["mode"], "guest-trending")
        self.assertGreaterEqual(len(payload["trips"]), 3)
        self.assertGreaterEqual(len(payload["blogs"]), 3)


class FeedBootstrapCommandTests(TestCase):
    def test_bootstrap_feed_seeds_preferences_with_verbose_output(self) -> None:
        for username in ("mei", "arun", "sahar"):
            UserModel.objects.create_user(
                username=username,
                email=f"{username}@example.com",
                password="DemoPass!12345",
            )

        stdout = StringIO()
        call_command("bootstrap_feed", "--verbose", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(MemberFeedPreference.objects.count(), 3)
        self.assertIn("[feed][verbose]", output)

    def test_bootstrap_feed_can_create_missing_members(self) -> None:
        call_command("bootstrap_feed", "--create-missing-members")

        self.assertTrue(UserModel.objects.filter(username="mei").exists())
        self.assertTrue(UserModel.objects.filter(username="arun").exists())
        self.assertTrue(UserModel.objects.filter(username="sahar").exists())
        self.assertEqual(MemberFeedPreference.objects.count(), 3)
