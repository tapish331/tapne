from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from social.models import Bookmark
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
        self.assertContains(response, "Upcoming trips")
        self.assertContains(response, "Destinations")
        self.assertNotContains(response, "<h2>People</h2>")
        self.assertNotContains(response, "Guest home")

        top_trip = response.context["trips"][0]
        top_blog = response.context["blogs"][0]
        top_destination = response.context["destinations"][0]

        self.assertEqual(top_trip["host_username"], "mei")
        self.assertEqual(top_blog["author_username"], "mei")
        self.assertEqual(top_destination["name"], top_trip["destination"])
        self.assertEqual(top_destination["trip_count"], 1)
        self.assertEqual(response.context["profiles"], [])
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
        self.assertEqual(response.context["destinations"], [])
        self.assertEqual(response.context["profiles"], [])

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

    def test_member_home_marks_bookmarked_trip_and_uses_unbookmark_action(self) -> None:
        self.client.login(username=self.member.username, password=self.password)
        first_response = self.client.get(reverse("home"))
        first_trip_id = int(first_response.context["trips"][0]["id"])

        Bookmark.objects.create(
            member=self.member,
            target_type=Bookmark.TARGET_TRIP,
            target_key=str(first_trip_id),
            target_label="Saved trip",
            target_url=f"/trips/{first_trip_id}/",
        )

        second_response = self.client.get(reverse("home"))
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(int(second_response.context["trips"][0]["id"]), first_trip_id)
        self.assertTrue(bool(second_response.context["trips"][0]["is_bookmarked"]))
        self.assertContains(second_response, reverse("social:unbookmark"))

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

    def test_home_destination_cards_link_to_destination_search(self) -> None:
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        first_destination = response.context["destinations"][0]
        escaped_search_url = str(first_destination["search_url"]).replace("&", "&amp;")
        self.assertContains(response, f'href="{escaped_search_url}"')

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_home_filters_out_past_trips_before_limiting_upcoming_section(self) -> None:
        now = timezone.now()
        for index in range(8):
            Trip.objects.create(
                host=self.member,
                title=f"Past trip {index + 1}",
                destination="Lisbon",
                starts_at=now - timedelta(days=index + 1),
                traffic_score=500 + index,
            )

        future_trip_ids: list[int] = []
        for index in range(3):
            future_trip = Trip.objects.create(
                host=self.member,
                title=f"Future trip {index + 1}",
                destination="Sevilla",
                starts_at=now + timedelta(days=index + 1),
                traffic_score=10 + index,
            )
            future_trip_ids.append(int(future_trip.pk))

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        rendered_trip_ids = [int(trip["id"]) for trip in response.context["trips"]]
        self.assertEqual(sorted(rendered_trip_ids), sorted(future_trip_ids))


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
