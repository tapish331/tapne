from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from blogs.models import Blog
from trips.models import Trip

from .models import Review

UserModel = get_user_model()


class ReviewsViewsTests(TestCase):
    def setUp(self) -> None:
        self.password = "ReviewsPass!123456"
        self.host = UserModel.objects.create_user(
            username="host-reviews",
            email="host-reviews@example.com",
            password=self.password,
        )
        self.member = UserModel.objects.create_user(
            username="member-reviews",
            email="member-reviews@example.com",
            password=self.password,
        )
        self.other = UserModel.objects.create_user(
            username="other-reviews",
            email="other-reviews@example.com",
            password=self.password,
        )

        starts_at = timezone.now() + timedelta(days=12)
        self.trip = Trip.objects.create(
            host=self.host,
            title="Reviews target trip",
            summary="Trip summary",
            description="Trip description",
            destination="Seoul",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=2),
            traffic_score=52,
            is_published=True,
        )
        self.blog = Blog.objects.create(
            author=self.host,
            slug="reviews-target-blog",
            title="Reviews target blog",
            excerpt="Blog excerpt",
            body="Blog body",
            reads=200,
            reviews_count=0,
            is_published=True,
        )

    def test_review_create_requires_login(self) -> None:
        response = self.client.post(
            reverse("reviews:create"),
            {
                "target_type": "trip",
                "target_id": str(self.trip.pk),
                "rating": "5",
                "headline": "Great host",
                "body": "Highly recommended.",
            },
        )
        expected_redirect = f"{reverse('accounts:login')}?next={reverse('reviews:create')}"
        self.assertRedirects(response, expected_redirect, fetch_redirect_response=False)

    def test_member_can_create_trip_review(self) -> None:
        self.client.login(username=self.member.username, password=self.password)

        response = self.client.post(
            reverse("reviews:create"),
            {
                "target_type": "trip",
                "target_id": str(self.trip.pk),
                "rating": "5",
                "headline": "  Excellent route planning  ",
                "body": "  Great pacing and clear host communication.  ",
                "next": reverse("trips:detail", kwargs={"trip_id": self.trip.pk}),
            },
        )

        self.assertRedirects(response, reverse("trips:detail", kwargs={"trip_id": self.trip.pk}))
        review = Review.objects.get(
            author=self.member,
            target_type=Review.TARGET_TRIP,
            target_key=str(self.trip.pk),
        )
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.headline, "Excellent route planning")
        self.assertEqual(review.body, "Great pacing and clear host communication.")

    def test_member_review_submission_updates_existing_row(self) -> None:
        Review.objects.create(
            author=self.member,
            target_type=Review.TARGET_TRIP,
            target_key=str(self.trip.pk),
            target_label=self.trip.title,
            target_url=self.trip.get_absolute_url(),
            rating=3,
            headline="Initial",
            body="Initial body",
        )

        self.client.login(username=self.member.username, password=self.password)
        response = self.client.post(
            reverse("reviews:create"),
            {
                "target_type": "trip",
                "target_id": str(self.trip.pk),
                "rating": "4",
                "headline": "Updated",
                "body": "Updated review copy.",
                "next": reverse("trips:detail", kwargs={"trip_id": self.trip.pk}),
            },
        )

        self.assertRedirects(response, reverse("trips:detail", kwargs={"trip_id": self.trip.pk}))
        self.assertEqual(
            Review.objects.filter(
                author=self.member,
                target_type=Review.TARGET_TRIP,
                target_key=str(self.trip.pk),
            ).count(),
            1,
        )
        review = Review.objects.get(
            author=self.member,
            target_type=Review.TARGET_TRIP,
            target_key=str(self.trip.pk),
        )
        self.assertEqual(review.rating, 4)
        self.assertEqual(review.headline, "Updated")
        self.assertEqual(review.body, "Updated review copy.")

    def test_create_blog_review_syncs_blog_reviews_count(self) -> None:
        self.client.login(username=self.member.username, password=self.password)
        first_response = self.client.post(
            reverse("reviews:create"),
            {
                "target_type": "blog",
                "target_id": self.blog.slug,
                "rating": "5",
                "body": "Strong operational checklist with practical tips.",
                "next": reverse("blogs:detail", kwargs={"slug": self.blog.slug}),
            },
        )
        self.assertRedirects(first_response, reverse("blogs:detail", kwargs={"slug": self.blog.slug}))

        self.blog.refresh_from_db()
        self.assertEqual(self.blog.reviews_count, 1)

        self.client.logout()
        self.client.login(username=self.other.username, password=self.password)
        second_response = self.client.post(
            reverse("reviews:create"),
            {
                "target_type": "blog",
                "target_id": self.blog.slug,
                "rating": "4",
                "body": "Good read with clear sequencing.",
                "next": reverse("blogs:detail", kwargs={"slug": self.blog.slug}),
            },
        )
        self.assertRedirects(second_response, reverse("blogs:detail", kwargs={"slug": self.blog.slug}))

        self.blog.refresh_from_db()
        self.assertEqual(self.blog.reviews_count, 2)

    def test_invalid_rating_is_rejected(self) -> None:
        self.client.login(username=self.member.username, password=self.password)
        response = self.client.post(
            reverse("reviews:create"),
            {
                "target_type": "trip",
                "target_id": str(self.trip.pk),
                "rating": "9",
                "body": "Should fail due to invalid rating.",
                "next": reverse("home"),
            },
        )

        self.assertRedirects(response, reverse("home"))
        self.assertEqual(Review.objects.count(), 0)

    def test_review_target_list_is_readable_for_guest(self) -> None:
        Review.objects.create(
            author=self.member,
            target_type=Review.TARGET_TRIP,
            target_key=str(self.trip.pk),
            target_label=self.trip.title,
            target_url=self.trip.get_absolute_url(),
            rating=5,
            headline="Great",
            body="Excellent pacing.",
        )
        Review.objects.create(
            author=self.other,
            target_type=Review.TARGET_TRIP,
            target_key=str(self.trip.pk),
            target_label=self.trip.title,
            target_url=self.trip.get_absolute_url(),
            rating=3,
            headline="Solid",
            body="Could use more free time.",
        )

        response = self.client.get(
            reverse(
                "reviews:target-list",
                kwargs={"target_type": "trip", "target_id": str(self.trip.pk)},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["review_mode"], "guest-target-reviews")
        self.assertEqual(response.context["review_count"], 2)
        self.assertEqual(float(response.context["review_average_rating"]), 4.0)

    def test_review_target_list_verbose_query_prints_debug_lines(self) -> None:
        with patch("builtins.print") as mock_print:
            response = self.client.get(
                f"{reverse('reviews:target-list', kwargs={'target_type': 'trip', 'target_id': str(self.trip.pk)})}?verbose=1"
            )

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(mock_print.call_count, 1)
        printed_lines = "\n".join(str(args[0]) for args, _kwargs in mock_print.call_args_list)
        self.assertIn("[reviews][verbose]", printed_lines)

    def test_review_create_without_verbose_does_not_print_debug_lines(self) -> None:
        self.client.login(username=self.member.username, password=self.password)

        with patch("builtins.print") as mock_print:
            response = self.client.post(
                reverse("reviews:create"),
                {
                    "target_type": "trip",
                    "target_id": str(self.trip.pk),
                    "rating": "4",
                    "body": "No verbose print expected.",
                    "next": reverse("trips:detail", kwargs={"trip_id": self.trip.pk}),
                },
            )

        self.assertRedirects(response, reverse("trips:detail", kwargs={"trip_id": self.trip.pk}))
        mock_print.assert_not_called()

    def test_invalid_target_type_list_returns_invalid_mode(self) -> None:
        response = self.client.get(
            reverse(
                "reviews:target-list",
                kwargs={"target_type": "user", "target_id": "member-reviews"},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["review_mode"], "invalid-target")


class ReviewsBootstrapCommandTests(TestCase):
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

        now = timezone.now()
        Trip.objects.create(
            pk=101,
            host=self.mei,
            title="Kyoto food lanes weekend",
            summary="s",
            description="d",
            destination="Kyoto",
            starts_at=now + timedelta(days=14),
            ends_at=now + timedelta(days=16),
            traffic_score=90,
            is_published=True,
        )
        Trip.objects.create(
            pk=102,
            host=self.arun,
            title="Patagonia first-light trekking camp",
            summary="s",
            description="d",
            destination="Patagonia",
            starts_at=now + timedelta(days=20),
            ends_at=now + timedelta(days=24),
            traffic_score=85,
            is_published=True,
        )
        Blog.objects.create(
            author=self.mei,
            slug="packing-for-swing-weather",
            title="Packing for swing-weather trips without overloading",
            excerpt="e",
            body="b",
            is_published=True,
        )
        Blog.objects.create(
            author=self.sahar,
            slug="how-to-run-a-desert-route",
            title="How to run a desert route without chaos",
            excerpt="e",
            body="b",
            is_published=True,
        )

    def test_bootstrap_reviews_seeds_rows_with_verbose_output(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_reviews", "--verbose", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(Review.objects.count(), 4)
        self.assertIn("[reviews][verbose]", output)
        self.assertIn("Reviews bootstrap complete", output)

    def test_bootstrap_reviews_can_create_missing_members(self) -> None:
        Review.objects.all().delete()
        UserModel.objects.filter(username__in=["mei", "arun", "sahar"]).delete()

        stdout = StringIO()
        call_command(
            "bootstrap_reviews",
            "--create-missing-members",
            "--verbose",
            stdout=stdout,
        )
        output = stdout.getvalue()

        self.assertTrue(UserModel.objects.filter(username="mei").exists())
        self.assertTrue(UserModel.objects.filter(username="arun").exists())
        self.assertTrue(UserModel.objects.filter(username="sahar").exists())
        self.assertEqual(Review.objects.count(), 4)
        self.assertIn("created_members=3", output)

    def test_bootstrap_reviews_skips_when_members_are_missing(self) -> None:
        Review.objects.all().delete()
        UserModel.objects.filter(username__in=["mei", "arun", "sahar"]).delete()

        stdout = StringIO()
        call_command("bootstrap_reviews", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(Review.objects.count(), 0)
        self.assertIn("skipped_reviews=4", output)
