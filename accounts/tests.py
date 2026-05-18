from __future__ import annotations

from datetime import timedelta
from io import StringIO
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.views import (
    host_metrics_for_user,
    profile_completeness_for_user,
    review_distribution_for_host,
    reviews_received_for_host,
    reviews_written_by_user,
)

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


class HostMetricsTests(TestCase):
    def _make_user(self, username: str) -> AbstractUser:
        return UserModel.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="DemoPass!12345",
        )

    def _make_trip(self, host: AbstractUser, title: str = "Demo trip"):
        from trips.models import Trip

        return Trip.objects.create(
            host=host,
            title=title,
            summary=f"{title} summary",
            destination="Tokyo, Japan",
            trip_type="city",
            is_published=True,
            status=Trip.STATUS_PUBLISHED,
        )

    def test_zero_trip_user_returns_zeroed_metrics(self) -> None:
        user = self._make_user("zero-trip-user")
        metrics = host_metrics_for_user(user)
        self.assertEqual(metrics["trips_hosted"], 0)
        self.assertEqual(metrics["reviews_count"], 0)
        self.assertEqual(metrics["average_rating"], 0.0)
        self.assertEqual(metrics["travelers_hosted"], 0)
        self.assertEqual(metrics["repeat_travelers_count"], 0)
        self.assertIsNone(metrics["median_response_hours"])

    def test_host_with_reviews_aggregates_rating_and_count(self) -> None:
        from reviews.models import Review

        host = self._make_user("metric-host")
        traveler = self._make_user("metric-traveler")
        trip = self._make_trip(host, title="Metric trip")
        Review.objects.create(
            author=traveler,
            target_type=Review.TARGET_TRIP,
            target_key=str(trip.pk),
            rating=5,
            headline="Loved it",
            body="Wonderful host.",
        )
        Review.objects.create(
            author=self._make_user("metric-traveler-2"),
            target_type=Review.TARGET_TRIP,
            target_key=str(trip.pk),
            rating=3,
            headline="Mixed",
            body="Some logistics issues.",
        )

        metrics = host_metrics_for_user(host)
        self.assertEqual(metrics["trips_hosted"], 1)
        self.assertEqual(metrics["reviews_count"], 2)
        self.assertEqual(metrics["average_rating"], 4.0)

    def test_repeat_travelers_counted_when_user_joins_two_trips(self) -> None:
        from enrollment.models import EnrollmentRequest

        host = self._make_user("repeat-host")
        loyal = self._make_user("loyal-traveler")
        once = self._make_user("once-traveler")
        trip_a = self._make_trip(host, title="Trip A")
        trip_b = self._make_trip(host, title="Trip B")

        EnrollmentRequest.objects.create(
            trip=trip_a, requester=loyal, status=EnrollmentRequest.STATUS_APPROVED
        )
        EnrollmentRequest.objects.create(
            trip=trip_b, requester=loyal, status=EnrollmentRequest.STATUS_APPROVED
        )
        EnrollmentRequest.objects.create(
            trip=trip_a, requester=once, status=EnrollmentRequest.STATUS_APPROVED
        )

        metrics = host_metrics_for_user(host)
        self.assertEqual(metrics["travelers_hosted"], 3)
        self.assertEqual(metrics["repeat_travelers_count"], 1)

    def test_median_response_hours_uses_reviewed_at_minus_created_at(self) -> None:
        from enrollment.models import EnrollmentRequest

        host = self._make_user("response-host")
        trip = self._make_trip(host, title="Response trip")

        # Two host responses: 2h and 6h. Median = 4.0
        for username, hours in (("resp-fast", 2), ("resp-slow", 6)):
            requester = self._make_user(username)
            row = EnrollmentRequest.objects.create(
                trip=trip, requester=requester, status=EnrollmentRequest.STATUS_APPROVED
            )
            row.reviewed_by = host
            row.reviewed_at = row.created_at + timedelta(hours=hours)
            row.save(update_fields=["reviewed_by", "reviewed_at", "updated_at"])

        # An auto-deny (no reviewed_by) must NOT enter the median.
        auto_requester = self._make_user("auto-denied-traveler")
        auto_row = EnrollmentRequest.objects.create(
            trip=trip, requester=auto_requester, status=EnrollmentRequest.STATUS_DENIED
        )
        auto_row.reviewed_at = auto_row.created_at + timedelta(hours=999)
        auto_row.save(update_fields=["reviewed_at", "updated_at"])

        metrics = host_metrics_for_user(host)
        self.assertEqual(metrics["median_response_hours"], 4.0)

    def test_review_distribution_percentages_sum_to_100_for_host(self) -> None:
        from reviews.models import Review

        host = self._make_user("distrib-host")
        trip = self._make_trip(host, title="Distrib trip")
        for index, rating in enumerate([5, 5, 4, 1]):
            Review.objects.create(
                author=self._make_user(f"reviewer-{index}"),
                target_type=Review.TARGET_TRIP,
                target_key=str(trip.pk),
                rating=rating,
                body="ok",
            )

        distribution = review_distribution_for_host(host)
        self.assertEqual(distribution["5"], 50.0)
        self.assertEqual(distribution["4"], 25.0)
        self.assertEqual(distribution["1"], 25.0)
        self.assertEqual(distribution["3"], 0.0)
        self.assertEqual(distribution["2"], 0.0)

    def test_review_distribution_empty_returns_zero_buckets(self) -> None:
        host = self._make_user("empty-distrib-host")
        distribution = review_distribution_for_host(host)
        self.assertEqual(set(distribution.keys()), {"5", "4", "3", "2", "1"})
        self.assertEqual(sum(distribution.values()), 0.0)

    def test_reviews_received_returns_only_host_target_reviews(self) -> None:
        from reviews.models import Review

        host_a = self._make_user("host-a")
        host_b = self._make_user("host-b")
        trip_a = self._make_trip(host_a, title="A trip")
        trip_b = self._make_trip(host_b, title="B trip")

        author = self._make_user("author")
        Review.objects.create(
            author=author,
            target_type=Review.TARGET_TRIP,
            target_key=str(trip_a.pk),
            rating=5,
            headline="A loved it",
            body="Great host A",
        )
        Review.objects.create(
            author=author,
            target_type=Review.TARGET_TRIP,
            target_key=str(trip_b.pk),
            rating=2,
            headline="B was meh",
            body="Mixed time with B",
        )

        rows_a = reviews_received_for_host(host_a)
        self.assertEqual(len(rows_a), 1)
        self.assertEqual(rows_a[0]["headline"], "A loved it")
        self.assertEqual(rows_a[0]["trip_id"], trip_a.pk)
        self.assertEqual(rows_a[0]["author_username"], "author")

    def test_reviews_written_returns_authored_reviews(self) -> None:
        from reviews.models import Review

        author = self._make_user("review-writer")
        host = self._make_user("review-target-host")
        trip = self._make_trip(host, title="Reviewed trip")
        Review.objects.create(
            author=author,
            target_type=Review.TARGET_TRIP,
            target_key=str(trip.pk),
            rating=4,
            headline="Solid",
            body="Good time overall",
        )
        rows = reviews_written_by_user(author)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["rating"], 4)
        self.assertEqual(rows[0]["target_key"], str(trip.pk))


class ProfileCompletenessTests(TestCase):
    def _user_with_profile(
        self,
        username: str,
        *,
        avatar: str = "",
        bio: str = "",
        location: str = "",
        tags: list[str] | None = None,
        gallery: list[str] | None = None,
    ) -> AbstractUser:
        user = UserModel.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="DemoPass!12345",
        )
        profile = ensure_profile(user)
        profile.avatar_url = avatar
        profile.bio = bio
        profile.location = location
        profile.travel_tags = list(tags or [])
        profile.gallery_photos = list(gallery or [])
        profile.save()
        return user

    def test_traveler_complete_when_avatar_bio_location_present(self) -> None:
        user = self._user_with_profile(
            "complete-traveler",
            avatar="https://x/a.jpg",
            bio="Hi",
            location="Anywhere",
        )
        result = profile_completeness_for_user(user, is_host=False)
        self.assertTrue(result["is_complete"])
        self.assertEqual(result["missing_fields"], [])

    def test_traveler_missing_fields_listed(self) -> None:
        user = self._user_with_profile("partial-traveler", avatar="", bio="hi", location="")
        result = profile_completeness_for_user(user, is_host=False)
        self.assertFalse(result["is_complete"])
        self.assertEqual(set(result["missing_fields"]), {"avatar_url", "location"})

    def test_host_requires_three_tags_and_three_gallery_photos(self) -> None:
        user = self._user_with_profile(
            "almost-host",
            avatar="https://x/a.jpg",
            bio="bio",
            location="here",
            tags=["beach", "food"],  # only 2
            gallery=["https://x/1.jpg", "https://x/2.jpg"],  # only 2
        )
        result = profile_completeness_for_user(user, is_host=True)
        self.assertFalse(result["is_complete"])
        self.assertEqual(set(result["missing_fields"]), {"travel_tags", "gallery_photos"})

    def test_host_complete_with_all_required_fields(self) -> None:
        user = self._user_with_profile(
            "complete-host",
            avatar="https://x/a.jpg",
            bio="bio",
            location="here",
            tags=["beach", "food", "hiking"],
            gallery=["https://x/1.jpg", "https://x/2.jpg", "https://x/3.jpg"],
        )
        result = profile_completeness_for_user(user, is_host=True)
        self.assertTrue(result["is_complete"])
        self.assertEqual(result["missing_fields"], [])

    def test_host_trip_banners_count_as_effective_gallery_photos(self) -> None:
        from trips.models import Trip

        user = self._user_with_profile(
            "host-with-trip-banners",
            avatar="https://x/a.jpg",
            bio="bio",
            location="here",
            tags=["beach", "food", "hiking"],
            gallery=[],
        )
        for index, trip_type in enumerate(["coastal", "trekking", "desert"]):
            Trip.objects.create(
                host=user,
                title=f"Visible trip {index + 1}",
                summary="Trip with visible profile card image.",
                destination="Goa",
                trip_type=trip_type,
                is_published=True,
                status=Trip.STATUS_PUBLISHED,
                starts_at=timezone.now() + timedelta(days=index + 1),
            )

        result = profile_completeness_for_user(user, is_host=True)

        self.assertTrue(result["is_complete"])
        self.assertNotIn("gallery_photos", result["missing_fields"])
