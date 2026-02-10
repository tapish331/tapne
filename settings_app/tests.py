from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import MemberSettings

UserModel = get_user_model()


class SettingsViewTests(TestCase):
    def setUp(self) -> None:
        self.password = "SettingsPass!123456"
        self.member = UserModel.objects.create_user(
            username="settings-member",
            email="settings-member@example.com",
            password=self.password,
        )

    def test_settings_page_requires_login(self) -> None:
        response = self.client.get(reverse("settings_app:index"))
        expected_redirect = f"{reverse('accounts:login')}?next={reverse('settings_app:index')}"
        self.assertRedirects(response, expected_redirect, fetch_redirect_response=False)

    def test_settings_page_renders_member_payload_and_initializes_row(self) -> None:
        self.client.login(username=self.member.username, password=self.password)
        response = self.client.get(reverse("settings_app:index"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["settings_mode"], "member-settings")
        self.assertIn("settings", response.context["settings_reason"].lower())
        self.assertTrue(MemberSettings.objects.filter(member=self.member).exists())
        self.assertEqual(response.context["settings_record"]["member_username"], self.member.username)

    def test_settings_post_updates_preferences(self) -> None:
        self.client.login(username=self.member.username, password=self.password)

        response = self.client.post(
            reverse("settings_app:index"),
            {
                "email_updates": MemberSettings.EMAIL_UPDATES_NONE,
                "profile_visibility": MemberSettings.PROFILE_VISIBILITY_MEMBERS,
                "dm_privacy": MemberSettings.DM_PRIVACY_NONE,
                "search_visibility": "",
                "digest_enabled": "on",
                "next": reverse("settings_app:index"),
            },
        )

        self.assertRedirects(response, reverse("settings_app:index"))
        row = MemberSettings.objects.get(member=self.member)
        self.assertEqual(row.email_updates, MemberSettings.EMAIL_UPDATES_NONE)
        self.assertEqual(row.profile_visibility, MemberSettings.PROFILE_VISIBILITY_MEMBERS)
        self.assertEqual(row.dm_privacy, MemberSettings.DM_PRIVACY_NONE)
        self.assertFalse(row.search_visibility)
        self.assertTrue(row.digest_enabled)

    def test_settings_verbose_query_prints_debug_lines(self) -> None:
        self.client.login(username=self.member.username, password=self.password)

        with patch("builtins.print") as mock_print:
            response = self.client.get(f"{reverse('settings_app:index')}?verbose=1")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(mock_print.call_count, 1)
        printed_lines = "\n".join(str(args[0]) for args, _kwargs in mock_print.call_args_list)
        self.assertIn("[settings][verbose]", printed_lines)

    def test_settings_without_verbose_does_not_print_debug_lines(self) -> None:
        self.client.login(username=self.member.username, password=self.password)

        with patch("builtins.print") as mock_print:
            response = self.client.get(reverse("settings_app:index"))

        self.assertEqual(response.status_code, 200)
        mock_print.assert_not_called()


class SettingsBootstrapCommandTests(TestCase):
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

    def test_bootstrap_settings_seeds_rows_with_verbose_output(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_settings", "--verbose", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(MemberSettings.objects.count(), 4)
        self.assertIn("[settings][verbose]", output)
        self.assertIn("Settings bootstrap complete", output)
        self.assertTrue(MemberSettings.objects.filter(member__username="mei").exists())

    def test_bootstrap_settings_can_create_missing_members(self) -> None:
        UserModel.objects.all().delete()
        stdout = StringIO()
        call_command(
            "bootstrap_settings",
            "--create-missing-members",
            "--verbose",
            stdout=stdout,
        )
        output = stdout.getvalue()

        self.assertTrue(UserModel.objects.filter(username="mei").exists())
        self.assertTrue(UserModel.objects.filter(username="arun").exists())
        self.assertTrue(UserModel.objects.filter(username="sahar").exists())
        self.assertTrue(UserModel.objects.filter(username="nora").exists())
        self.assertEqual(MemberSettings.objects.count(), 4)
        self.assertIn("created_members=", output)
