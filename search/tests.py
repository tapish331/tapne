from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from feed.models import MemberFeedPreference

UserModel = get_user_model()


class SearchViewTests(TestCase):
    def setUp(self) -> None:
        self.password = "SearchPass!123456"
        self.member = UserModel.objects.create_user(
            username="member-search",
            email="member-search@example.com",
            password=self.password,
        )

    def test_guest_search_defaults_use_global_most_searched_mode(self) -> None:
        response = self.client.get(reverse("search:search"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["search_mode"], "guest-most-searched")
        self.assertIn("Global most-searched defaults", response.context["search_reason"])

        self.assertEqual(response.context["trips"][0]["id"], 102)
        self.assertEqual(response.context["profiles"][0]["username"], "mei")
        self.assertEqual(response.context["blogs"][0]["slug"], "packing-for-swing-weather")

    def test_member_search_defaults_use_like_minded_signals(self) -> None:
        MemberFeedPreference.objects.create(
            user=self.member,
            followed_usernames=["sahar"],
            interest_keywords=["desert", "route"],
        )
        self.client.login(username=self.member.username, password=self.password)

        response = self.client.get(reverse("search:search"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["search_mode"], "member-like-minded")
        self.assertIn("like-minded", response.context["search_reason"])
        self.assertEqual(response.context["trips"][0]["host_username"], "sahar")
        self.assertEqual(response.context["profiles"][0]["username"], "sahar")
        self.assertEqual(response.context["blogs"][0]["author_username"], "sahar")

    def test_search_query_and_type_filter(self) -> None:
        response = self.client.get(f"{reverse('search:search')}?q=desert&type=trips")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_type"], "trips")
        self.assertTrue(response.context["has_query"])
        self.assertGreaterEqual(len(response.context["trips"]), 1)
        self.assertEqual(response.context["profiles"], [])
        self.assertEqual(response.context["blogs"], [])

    def test_invalid_search_type_falls_back_to_all(self) -> None:
        response = self.client.get(f"{reverse('search:search')}?type=unknown")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_type"], "all")
        self.assertGreater(len(response.context["trips"]), 0)
        self.assertGreater(len(response.context["profiles"]), 0)
        self.assertGreater(len(response.context["blogs"]), 0)

    def test_search_users_with_query_includes_live_accounts(self) -> None:
        for username in ("tapne", "tapne1", "tapne2"):
            UserModel.objects.create_user(
                username=username,
                email=f"{username}@example.com",
                password="LivePass!12345",
            )

        response = self.client.get(f"{reverse('search:search')}?q=tapne&type=users")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_type"], "users")
        usernames = {profile["username"] for profile in response.context["profiles"]}
        self.assertTrue({"tapne", "tapne1", "tapne2"}.issubset(usernames))
        self.assertEqual(response.context["trips"], [])
        self.assertEqual(response.context["blogs"], [])

    def test_search_all_with_query_includes_live_accounts_in_profile_results(self) -> None:
        UserModel.objects.create_user(
            username="tapne",
            email="tapne@example.com",
            password="LivePass!12345",
        )

        response = self.client.get(f"{reverse('search:search')}?q=tapne&type=all")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_type"], "all")
        usernames = {profile["username"] for profile in response.context["profiles"]}
        self.assertIn("tapne", usernames)

    def test_search_trips_with_query_includes_live_trips(self) -> None:
        with patch(
            "search.models._live_trips_for_query",
            return_value=[
                {
                    "id": 999,
                    "title": "Tapne mountain test trip",
                    "summary": "Live trip row",
                    "destination": "Test Valley",
                    "host_username": "tapne",
                    "traffic_score": 10,
                    "url": "/trips/999/",
                }
            ],
        ):
            response = self.client.get(f"{reverse('search:search')}?q=tapne&type=trips")

        self.assertEqual(response.status_code, 200)
        trip_ids = {trip["id"] for trip in response.context["trips"]}
        self.assertIn(999, trip_ids)

    def test_search_all_with_query_includes_live_trips_and_blogs(self) -> None:
        with patch(
            "search.models._live_trips_for_query",
            return_value=[
                {
                    "id": 998,
                    "title": "Tapne route live trip",
                    "summary": "Live trip row",
                    "destination": "Test Highlands",
                    "host_username": "tapne",
                    "traffic_score": 12,
                    "url": "/trips/998/",
                }
            ],
        ), patch(
            "search.models._live_blogs_for_query",
            return_value=[
                {
                    "id": 997,
                    "slug": "tapne-live-blog",
                    "title": "Tapne live blog post",
                    "excerpt": "Live blog row",
                    "author_username": "tapne",
                    "reads": 5,
                    "reviews_count": 0,
                    "url": "/blogs/tapne-live-blog/",
                    "body": "Live body",
                }
            ],
        ):
            response = self.client.get(f"{reverse('search:search')}?q=tapne&type=all")

        self.assertEqual(response.status_code, 200)
        trip_ids = {trip["id"] for trip in response.context["trips"]}
        blog_slugs = {blog["slug"] for blog in response.context["blogs"]}
        self.assertIn(998, trip_ids)
        self.assertIn("tapne-live-blog", blog_slugs)

    def test_search_trips_defaults_do_not_pull_live_rows_without_query(self) -> None:
        with patch("search.models._live_trips_for_query") as mock_live_trips:
            response = self.client.get(f"{reverse('search:search')}?type=trips")

        self.assertEqual(response.status_code, 200)
        mock_live_trips.assert_not_called()

    def test_search_blogs_defaults_do_not_pull_live_rows_without_query(self) -> None:
        with patch("search.models._live_blogs_for_query") as mock_live_blogs:
            response = self.client.get(f"{reverse('search:search')}?type=blogs")

        self.assertEqual(response.status_code, 200)
        mock_live_blogs.assert_not_called()

    def test_search_verbose_query_prints_debug_lines(self) -> None:
        with patch("builtins.print") as mock_print:
            response = self.client.get(f"{reverse('search:search')}?verbose=1")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(mock_print.call_count, 1)
        printed_lines = "\n".join(str(args[0]) for args, _kwargs in mock_print.call_args_list)
        self.assertIn("[search][verbose]", printed_lines)

    def test_search_without_verbose_query_does_not_print_debug_lines(self) -> None:
        with patch("builtins.print") as mock_print:
            response = self.client.get(reverse("search:search"))

        self.assertEqual(response.status_code, 200)
        mock_print.assert_not_called()


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
