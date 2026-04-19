from __future__ import annotations

import json
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import MemberSettings

UserModel = get_user_model()


class SettingsAppearanceEndpointTests(TestCase):
    """Tests for the live `/settings/appearance/` JSON endpoint.

    The Django-rendered settings page and its tests were retired in the
    SPA cutover; the SPA covers settings UI via `/frontend-api/settings/`.
    The appearance endpoint survives as a lightweight cookie-backed AJAX
    writer for live theme toggling.
    """

    def setUp(self) -> None:
        self.password = "SettingsPass!123456"
        self.member = UserModel.objects.create_user(
            username="settings-member",
            email="settings-member@example.com",
            password=self.password,
        )

    def test_settings_appearance_endpoint_requires_login(self) -> None:
        response = self.client.post(reverse("settings_app:appearance-update"))
        # login_url is now "/" (SPA root); anonymous POSTs redirect there so
        # the Lovable auth modal can open.
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/"))

    def test_settings_appearance_endpoint_updates_theme_preference(self) -> None:
        self.client.login(username=self.member.username, password=self.password)

        response = self.client.post(
            reverse("settings_app:appearance-update"),
            data=json.dumps({"theme_preference": MemberSettings.THEME_PREFERENCE_LIGHT}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ok"], True)
        row = MemberSettings.objects.get(member=self.member)
        self.assertEqual(row.theme_preference, MemberSettings.THEME_PREFERENCE_LIGHT)


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
