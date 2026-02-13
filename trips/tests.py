from __future__ import annotations

from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from feed.models import MemberFeedPreference
from social.models import Bookmark

from .models import Trip

UserModel = get_user_model()


def _datetime_local(value: datetime) -> str:
    return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")


class TripViewsTests(TestCase):
    def setUp(self) -> None:
        self.password = "TripsPass!123456"
        self.host_user = UserModel.objects.create_user(
            username="host-user",
            email="host-user@example.com",
            password=self.password,
        )
        self.member_user = UserModel.objects.create_user(
            username="member-user",
            email="member-user@example.com",
            password=self.password,
        )

    def test_guest_trip_list_uses_demo_fallback_when_no_live_rows(self) -> None:
        response = self.client.get(reverse("trips:list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["trip_source"], "demo-fallback")
        self.assertEqual(response.context["trip_mode"], "guest-trending-demo")
        self.assertGreater(len(response.context["trips"]), 0)

    def test_member_trip_list_uses_live_rows_and_preference_boost(self) -> None:
        Trip.objects.create(
            host=self.host_user,
            title="Baseline trip",
            summary="Standard row",
            description="Default member row",
            destination="Lisbon",
            starts_at=timezone.now() + timedelta(days=2),
            traffic_score=90,
        )

        boosted_host = UserModel.objects.create_user(
            username="boosted",
            email="boosted@example.com",
            password=self.password,
        )
        Trip.objects.create(
            host=boosted_host,
            title="Boosted preference trip",
            summary="Preferred host",
            description="Should rank first for member preference",
            destination="Sevilla",
            starts_at=timezone.now() + timedelta(days=5),
            traffic_score=10,
        )

        MemberFeedPreference.objects.create(
            user=self.member_user,
            followed_usernames=["boosted"],
            interest_keywords=["route"],
        )

        self.client.login(username=self.member_user.username, password=self.password)
        response = self.client.get(reverse("trips:list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["trip_source"], "live-db")
        self.assertEqual(response.context["trip_mode"], "member-like-minded-live")
        self.assertEqual(response.context["trips"][0]["host_username"], "boosted")

    def test_trip_detail_limits_description_for_guest(self) -> None:
        trip = Trip.objects.create(
            host=self.host_user,
            title="Guest detail trip",
            summary="Guest preview summary",
            description="x" * 400,
            destination="Osaka",
            starts_at=timezone.now() + timedelta(days=3),
            traffic_score=20,
        )

        response = self.client.get(reverse("trips:detail", kwargs={"trip_id": trip.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["trip_detail_mode"], "guest-limited")
        self.assertIn("Log in to view the full itinerary", response.context["trip"]["description"])

    def test_trip_detail_shows_full_description_for_member(self) -> None:
        trip = Trip.objects.create(
            host=self.host_user,
            title="Member detail trip",
            summary="Summary",
            description="Full itinerary text for authenticated member visibility.",
            destination="Reykjavik",
            starts_at=timezone.now() + timedelta(days=3),
            traffic_score=20,
        )

        self.client.login(username=self.member_user.username, password=self.password)
        response = self.client.get(reverse("trips:detail", kwargs={"trip_id": trip.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["trip_detail_mode"], "member-full")
        self.assertIn("Full itinerary text", response.context["trip"]["description"])

    def test_trip_create_requires_login(self) -> None:
        response = self.client.get(reverse("trips:create"))
        expected_redirect = f"{reverse('accounts:login')}?next={reverse('trips:create')}"
        self.assertRedirects(response, expected_redirect, fetch_redirect_response=False)

    def test_trip_create_post_creates_trip_for_logged_in_member(self) -> None:
        self.client.login(username=self.member_user.username, password=self.password)
        starts_at = timezone.now() + timedelta(days=10)
        ends_at = starts_at + timedelta(days=2)

        response = self.client.post(
            reverse("trips:create"),
            {
                "title": "Created trip",
                "summary": "Created summary",
                "description": "Created detail",
                "destination": "Athens",
                "starts_at": _datetime_local(starts_at),
                "ends_at": _datetime_local(ends_at),
                "traffic_score": "45",
                "is_published": "on",
            },
        )

        created_trip = Trip.objects.get(title="Created trip")
        self.assertRedirects(response, reverse("trips:detail", kwargs={"trip_id": created_trip.pk}))
        self.assertEqual(created_trip.host, self.member_user)

    def test_trip_edit_is_owner_only(self) -> None:
        trip = Trip.objects.create(
            host=self.host_user,
            title="Owner only trip",
            summary="s",
            description="d",
            destination="Berlin",
            starts_at=timezone.now() + timedelta(days=4),
            traffic_score=10,
        )

        self.client.login(username=self.member_user.username, password=self.password)
        response = self.client.get(reverse("trips:edit", kwargs={"trip_id": trip.pk}))
        self.assertEqual(response.status_code, 404)

    def test_trip_delete_requires_post(self) -> None:
        trip = Trip.objects.create(
            host=self.host_user,
            title="Delete method check",
            summary="s",
            description="d",
            destination="Prague",
            starts_at=timezone.now() + timedelta(days=4),
            traffic_score=10,
        )

        self.client.login(username=self.host_user.username, password=self.password)
        response = self.client.get(reverse("trips:delete", kwargs={"trip_id": trip.pk}))
        self.assertEqual(response.status_code, 405)

    def test_trip_mine_tabs_segment_upcoming_and_past(self) -> None:
        Trip.objects.create(
            host=self.host_user,
            title="Upcoming host trip",
            summary="s",
            description="d",
            destination="Rome",
            starts_at=timezone.now() + timedelta(days=5),
            traffic_score=10,
        )
        Trip.objects.create(
            host=self.host_user,
            title="Past host trip",
            summary="s",
            description="d",
            destination="Madrid",
            starts_at=timezone.now() - timedelta(days=5),
            traffic_score=10,
        )

        self.client.login(username=self.host_user.username, password=self.password)

        upcoming_response = self.client.get(reverse("trips:mine"))
        self.assertEqual(upcoming_response.status_code, 200)
        self.assertEqual(upcoming_response.context["active_tab"], "upcoming")
        upcoming_titles = {row["title"] for row in upcoming_response.context["mine_trips"]}
        self.assertIn("Upcoming host trip", upcoming_titles)
        self.assertNotIn("Past host trip", upcoming_titles)

        past_response = self.client.get(f"{reverse('trips:mine')}?tab=past")
        self.assertEqual(past_response.status_code, 200)
        self.assertEqual(past_response.context["active_tab"], "past")
        past_titles = {row["title"] for row in past_response.context["mine_trips"]}
        self.assertIn("Past host trip", past_titles)
        self.assertNotIn("Upcoming host trip", past_titles)

    def test_trip_mine_saved_tab_reads_social_trip_bookmarks(self) -> None:
        saved_trip = Trip.objects.create(
            host=self.host_user,
            title="Saved trip row",
            summary="s",
            description="d",
            destination="Copenhagen",
            starts_at=timezone.now() + timedelta(days=4),
            traffic_score=30,
        )
        Bookmark.objects.create(
            member=self.host_user,
            target_type="trip",
            target_key=str(saved_trip.pk),
            target_label=saved_trip.title,
            target_url=saved_trip.get_absolute_url(),
        )

        self.client.login(username=self.host_user.username, password=self.password)
        response = self.client.get(f"{reverse('trips:mine')}?tab=saved")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_tab"], "saved")
        saved_titles = {row["title"] for row in response.context["mine_trips"]}
        self.assertIn("Saved trip row", saved_titles)
        self.assertEqual(response.context["tab_counts"]["saved"], 1)

    def test_trip_list_filters_apply_duration_trip_type_and_destination(self) -> None:
        short_city_trip = Trip.objects.create(
            host=self.host_user,
            title="City weekend route",
            summary="Fast city highlights",
            description="Urban walk and food stops.",
            destination="Lisbon",
            starts_at=timezone.now() + timedelta(days=5),
            ends_at=timezone.now() + timedelta(days=7),
            traffic_score=30,
        )
        long_desert_trip = Trip.objects.create(
            host=self.host_user,
            title="Desert crossing route",
            summary="Multi-day desert camp sequence.",
            description="Sahara transfer and overnight camp plan.",
            destination="Merzouga",
            starts_at=timezone.now() + timedelta(days=10),
            ends_at=timezone.now() + timedelta(days=19),
            traffic_score=40,
        )

        response = self.client.get(
            f"{reverse('trips:list')}?duration=long&trip_type=desert&destination=merz"
        )
        self.assertEqual(response.status_code, 200)
        trip_ids = [trip["id"] for trip in response.context["trips"]]
        self.assertIn(long_desert_trip.pk, trip_ids)
        self.assertNotIn(short_city_trip.pk, trip_ids)
        self.assertEqual(response.context["trip_filters"]["duration"], "long")
        self.assertEqual(response.context["trip_filters"]["trip_type"], "desert")
        self.assertEqual(response.context["trip_filtered_count"], 1)

    def test_guest_trip_detail_exposes_richer_preview_fields(self) -> None:
        trip = Trip.objects.create(
            host=self.host_user,
            title="Budget city discovery",
            summary="Beginner-friendly route with relaxed pacing.",
            description="A practical first-timer city route.",
            destination="Porto",
            starts_at=timezone.now() + timedelta(days=6),
            ends_at=timezone.now() + timedelta(days=9),
            traffic_score=25,
        )

        response = self.client.get(reverse("trips:detail", kwargs={"trip_id": trip.pk}))
        self.assertEqual(response.status_code, 200)
        preview_trip = response.context["trip"]
        self.assertIn("duration_label", preview_trip)
        self.assertIn("trip_type_label", preview_trip)
        self.assertIn("budget_label", preview_trip)
        self.assertIn("difficulty_label", preview_trip)
        self.assertIn("pace_label", preview_trip)
        self.assertIn("group_size_label", preview_trip)
        self.assertIn("includes_label", preview_trip)

    def test_trip_list_verbose_query_prints_debug_lines(self) -> None:
        with patch("builtins.print") as mock_print:
            response = self.client.get(f"{reverse('trips:list')}?verbose=1")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(mock_print.call_count, 1)
        printed_lines = "\n".join(str(args[0]) for args, _kwargs in mock_print.call_args_list)
        self.assertIn("[trips][verbose]", printed_lines)

    def test_trip_list_without_verbose_query_does_not_print_debug_lines(self) -> None:
        with patch("builtins.print") as mock_print:
            response = self.client.get(reverse("trips:list"))

        self.assertEqual(response.status_code, 200)
        mock_print.assert_not_called()


class TripsBootstrapCommandTests(TestCase):
    def test_bootstrap_trips_seeds_rows_with_verbose_output(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_trips", "--create-missing-hosts", "--verbose", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(Trip.objects.count(), 3)
        self.assertIn("[trips][verbose]", output)
        self.assertIn("Trips bootstrap complete", output)

    def test_bootstrap_trips_skips_when_hosts_are_missing(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_trips", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(Trip.objects.count(), 0)
        self.assertIn("skipped=3", output)
