from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from blogs.models import Blog
from feed.models import MemberFeedPreference

UserModel = get_user_model()


class SearchBootstrapCommandTests(TestCase):
    def test_bootstrap_search_outputs_verbose_lines(self) -> None:
        UserModel.objects.create_user(
            username="mei",
            email="mei@example.com",
            password="DemoPass!12345",
        )

        stdout = StringIO()
        call_command("bootstrap_search", "--verbose", stdout=stdout)
        output = stdout.getvalue()

        self.assertIn("[search][verbose]", output)
        self.assertIn("Search bootstrap complete", output)

    def test_bootstrap_search_can_create_missing_member(self) -> None:
        call_command(
            "bootstrap_search",
            "--member-username",
            "missing-member",
            "--create-missing-member",
        )
        self.assertTrue(UserModel.objects.filter(username="missing-member").exists())
