from __future__ import annotations

from io import StringIO
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from .models import AccountProfile, ensure_profile

UserModel = get_user_model()


class BootstrapAccountsCommandTests(TestCase):
    def test_command_creates_demo_users_and_verbose_output(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_accounts", "--verbose", stdout=stdout)
        output = stdout.getvalue()

        self.assertTrue(UserModel.objects.filter(username="mei").exists())
        self.assertIn("[accounts][verbose]", output)

    def test_command_normalizes_existing_demo_username_case(self) -> None:
        user = UserModel.objects.create_user(
            username="MeI",
            email="legacy-mei@example.com",
            password="LegacyPass!123",
        )
        ensure_profile(user)

        call_command("bootstrap_accounts")

        self.assertEqual(UserModel.objects.filter(username__iexact="mei").count(), 1)
        normalized_user = UserModel.objects.get(username__iexact="mei")
        self.assertEqual(normalized_user.username, "mei")
