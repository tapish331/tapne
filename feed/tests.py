from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from trips.models import Trip

from .models import MemberFeedPreference

UserModel = get_user_model()


class FeedHomeViewTests(TestCase):
    def setUp(self) -> None:
        self.password = "FeedPass!123456"
        self.member = UserModel.objects.create_user(
            username="member1",
            email="member1@example.com",
            password=self.password,
        )

    def test_guest_home_uses_trending_payload(self) -> None:
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["feed_mode"], "guest-trending")
        self.assertContains(response, "Find your kind of people.")
        self.assertContains(response, "Then travel.")
        self.assertContains(
            response,
            "Join community-led trips with like-minded travelers. Discover adventures, make friends, and explore the world together.",
        )
        self.assertNotContains(response, "Guest home")

        top_trip = response.context["trips"][0]
        top_profile = response.context["profiles"][0]
        top_blog = response.context["blogs"][0]

        self.assertEqual(top_trip["host_username"], "mei")
        self.assertEqual(top_profile["username"], "mei")
        self.assertEqual(top_blog["author_username"], "mei")
        self.assertEqual(response.context["total_unique_destinations"], 0)
        self.assertEqual(response.context["total_authenticated_users"], 1)
        self.assertEqual(response.context["total_trips_created"], 0)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_guest_home_uses_live_catalog_when_demo_catalog_disabled(self) -> None:
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["feed_mode"], "guest-trending-live")
        self.assertEqual(response.context["trips"], [])
        self.assertEqual(response.context["blogs"], [])
        self.assertEqual(response.context["profiles"][0]["username"], "member1")

    def test_member_home_uses_personalized_payload_from_preferences(self) -> None:
        MemberFeedPreference.objects.create(
            user=self.member,
            followed_usernames=["sahar"],
            interest_keywords=["desert", "route"],
        )

        self.client.login(username=self.member.username, password=self.password)
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["feed_mode"], "member-personalized")
        self.assertNotContains(response, "Member home")
        self.assertContains(response, "Find your kind of people.")
        self.assertContains(response, "Then travel.")

        top_trip = response.context["trips"][0]
        top_blog = response.context["blogs"][0]
        self.assertEqual(top_trip["host_username"], "sahar")
        self.assertEqual(top_blog["author_username"], "sahar")

    def test_member_home_without_preference_uses_fallback_reason(self) -> None:
        self.client.login(username=self.member.username, password=self.password)
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["feed_mode"], "member-personalized")
        self.assertIn("Fallback member personalization", response.context["feed_reason"])

    def test_home_verbose_query_prints_debug_lines(self) -> None:
        with patch("builtins.print") as mock_print:
            response = self.client.get(f"{reverse('home')}?verbose=1")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(mock_print.call_count, 1)

        printed_lines = "\n".join(str(args[0]) for args, _kwargs in mock_print.call_args_list)
        self.assertIn("[feed][verbose]", printed_lines)

    def test_home_without_verbose_query_does_not_print_debug_lines(self) -> None:
        with patch("builtins.print") as mock_print:
            response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        mock_print.assert_not_called()

    def test_home_totals_include_case_insensitive_unique_destination_count(self) -> None:
        Trip.objects.create(host=self.member, title="City Escape", destination="Lisbon")
        Trip.objects.create(host=self.member, title="Weekend Route", destination="lisbon")
        Trip.objects.create(host=self.member, title="Food Trail", destination="Sevilla")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_unique_destinations"], 2)
        self.assertEqual(response.context["total_authenticated_users"], 1)
        self.assertEqual(response.context["total_trips_created"], 3)


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
