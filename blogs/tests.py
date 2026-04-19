from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from feed.models import MemberFeedPreference

from .models import Blog

UserModel = get_user_model()


class BlogsBootstrapCommandTests(TestCase):
    def test_bootstrap_blogs_seeds_rows_with_verbose_output(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_blogs", "--create-missing-authors", "--verbose", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(Blog.objects.count(), 3)
        self.assertIn("[blogs][verbose]", output)
        self.assertIn("Blogs bootstrap complete", output)

    def test_bootstrap_blogs_skips_when_authors_are_missing(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_blogs", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(Blog.objects.count(), 0)
        self.assertIn("skipped=3", output)
