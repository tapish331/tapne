from __future__ import annotations

from io import StringIO
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import AccountProfile, ensure_profile

UserModel = get_user_model()


class AccountsViewsTests(TestCase):
    def setUp(self) -> None:
        self.password = "TestPassword!123"
        self.user = UserModel.objects.create_user(
            username="owner",
            email="owner@example.com",
            password=self.password,
        )
        ensure_profile(self.user)

    def test_signup_get_renders_form(self) -> None:
        response = self.client.get(reverse("accounts:signup"))
        self.assertRedirects(response, "/?auth=signup")

    def test_login_get_redirects_to_modal_state(self) -> None:
        response = self.client.get(reverse("accounts:login"))
        self.assertRedirects(response, "/?auth=login")

    def test_login_get_for_member_page_redirects_to_safe_origin_with_auth_next(self) -> None:
        response = self.client.get(f"{reverse('accounts:login')}?next={reverse('accounts:me')}")
        self.assertEqual(response.status_code, 302)
        location = str(response.headers["Location"])
        self.assertTrue(location.startswith("/?auth=login"))
        self.assertIn("auth_next=%2Faccounts%2Fme%2F", location)

    def test_signup_post_creates_user_and_profile(self) -> None:
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "newmember",
                "email": "newmember@example.com",
                "password1": "AnotherStrongPass!123",
                "password2": "AnotherStrongPass!123",
            },
        )
        self.assertRedirects(response, reverse("home"))
        self.assertTrue(UserModel.objects.filter(username="newmember").exists())
        created_user = UserModel.objects.get(username="newmember")
        self.assertTrue(AccountProfile.objects.filter(user=created_user).exists())

    def test_signup_rejects_case_insensitive_duplicate_username(self) -> None:
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "OWNER",
                "email": "owner-alt@example.com",
                "password1": "AnotherStrongPass!123",
                "password2": "AnotherStrongPass!123",
            },
        )
        self.assertEqual(response.status_code, 302)
        location = str(response.headers["Location"])
        parsed = urlsplit(location)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.path, "/")
        self.assertEqual(query.get("auth"), ["signup"])
        self.assertEqual(query.get("auth_error"), ["1"])
        self.assertEqual(UserModel.objects.filter(username__iexact="owner").count(), 1)

        detail_response = self.client.get(location)
        self.assertContains(detail_response, "An account with this username already exists.")

    def test_signup_rejects_weak_password(self) -> None:
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "weakcandidate",
                "email": "weakcandidate@example.com",
                "password1": "weakpassword12",
                "password2": "weakpassword12",
            },
        )
        self.assertEqual(response.status_code, 302)
        location = str(response.headers["Location"])
        parsed = urlsplit(location)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.path, "/")
        self.assertEqual(query.get("auth"), ["signup"])
        self.assertEqual(query.get("auth_error"), ["1"])
        self.assertFalse(UserModel.objects.filter(username="weakcandidate").exists())

        detail_response = self.client.get(location)
        self.assertContains(detail_response, "Password must contain at least one uppercase letter.")
        self.assertContains(detail_response, "Password must contain at least one symbol.")

    def test_login_invalid_credentials_show_modal_error(self) -> None:
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "owner", "password": "WrongPass!123"},
        )
        self.assertEqual(response.status_code, 302)
        location = str(response.headers["Location"])
        parsed = urlsplit(location)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.path, "/")
        self.assertEqual(query.get("auth"), ["login"])
        self.assertEqual(query.get("auth_error"), ["1"])

        detail_response = self.client.get(location)
        self.assertContains(detail_response, "Please enter a correct username and password.")

    def test_login_post_redirects_to_next_url(self) -> None:
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": self.user.username,
                "password": self.password,
                "next": reverse("accounts:me"),
            },
        )
        self.assertRedirects(response, reverse("accounts:me"))

    def test_logout_requires_post(self) -> None:
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 405)

    def test_logout_post_logs_member_out(self) -> None:
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("home"))
        me_response = self.client.get(reverse("accounts:me"))
        self.assertEqual(me_response.status_code, 302)

    def test_my_profile_requires_login(self) -> None:
        response = self.client.get(reverse("accounts:me"))
        expected_redirect = f"{reverse('accounts:login')}?next={reverse('accounts:me')}"
        self.assertRedirects(response, expected_redirect, fetch_redirect_response=False)

    def test_my_profile_view_works_for_logged_in_member(self) -> None:
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(reverse("accounts:me"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "@owner")

    def test_my_profile_edit_updates_profile_and_user_fields(self) -> None:
        self.client.login(username=self.user.username, password=self.password)
        response = self.client.post(
            reverse("accounts:me-edit"),
            {
                "display_name": "Owner Display",
                "bio": "I host practical city routes.",
                "location": "Lisbon",
                "website": "https://example.com",
                "email": "updated-owner@example.com",
                "first_name": "Owner",
                "last_name": "Person",
            },
        )
        self.assertRedirects(response, reverse("accounts:me"))
        self.user.refresh_from_db()
        profile = AccountProfile.objects.get(user=self.user)
        self.assertEqual(self.user.email, "updated-owner@example.com")
        self.assertEqual(profile.display_name, "Owner Display")
        self.assertEqual(profile.location, "Lisbon")

    def test_public_profile_for_real_user(self) -> None:
        response = self.client.get(reverse("public-profile", kwargs={"username": "owner"}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "@owner")

    def test_public_profile_for_demo_user_fallback(self) -> None:
        response = self.client.get(reverse("public-profile", kwargs={"username": "mei"}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mei Tanaka")
        self.assertContains(response, "demo profile")


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
