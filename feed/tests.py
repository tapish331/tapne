from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from social.models import Bookmark
from trips.models import Trip

from .models import MemberFeedPreference

UserModel = get_user_model()


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
