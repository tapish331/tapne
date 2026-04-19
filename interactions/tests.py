from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db.models import Q
from django.test import TestCase
from django.utils import timezone

from blogs.models import Blog
from trips.models import Trip

from .models import Comment, DirectMessage, DirectMessageThread, resolve_comment_target

UserModel = get_user_model()


class InteractionsBootstrapCommandTests(TestCase):
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

    def test_bootstrap_interactions_seeds_rows_with_verbose_output(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_interactions", "--verbose", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(Comment.objects.filter(parent__isnull=True).count(), 4)
        self.assertEqual(Comment.objects.filter(parent__isnull=False).count(), 3)
        self.assertEqual(DirectMessageThread.objects.count(), 2)
        self.assertEqual(DirectMessage.objects.count(), 4)
        self.assertIn("[interactions][verbose]", output)
        self.assertIn("Interactions bootstrap complete", output)

    def test_bootstrap_interactions_can_create_missing_members(self) -> None:
        UserModel.objects.all().delete()
        stdout = StringIO()
        call_command(
            "bootstrap_interactions",
            "--create-missing-members",
            "--verbose",
            stdout=stdout,
        )
        output = stdout.getvalue()

        self.assertTrue(UserModel.objects.filter(username="mei").exists())
        self.assertTrue(UserModel.objects.filter(username="arun").exists())
        self.assertTrue(UserModel.objects.filter(username="sahar").exists())
        self.assertEqual(Comment.objects.count(), 7)
        self.assertEqual(DirectMessageThread.objects.count(), 2)
        self.assertIn("created_members=3", output)

    def test_bootstrap_interactions_skips_when_members_are_missing(self) -> None:
        UserModel.objects.all().delete()
        stdout = StringIO()
        call_command("bootstrap_interactions", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(Comment.objects.count(), 0)
        self.assertEqual(DirectMessage.objects.count(), 0)
        self.assertIn("skipped_comment_rows", output)
