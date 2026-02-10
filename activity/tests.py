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
from enrollment.models import EnrollmentRequest
from interactions.models import Comment
from reviews.models import Review
from social.models import Bookmark, FollowRelation
from trips.models import Trip

UserModel = get_user_model()


class ActivityViewTests(TestCase):
    def setUp(self) -> None:
        self.password = "ActivityPass!123456"
        self.mei = UserModel.objects.create_user(
            username="mei",
            email="mei@example.com",
            password=self.password,
        )
        self.arun = UserModel.objects.create_user(
            username="arun",
            email="arun@example.com",
            password=self.password,
        )
        self.sahar = UserModel.objects.create_user(
            username="sahar",
            email="sahar@example.com",
            password=self.password,
        )
        self.nora = UserModel.objects.create_user(
            username="nora",
            email="nora@example.com",
            password=self.password,
        )

        starts_at = timezone.now() + timedelta(days=9)
        self.trip_mei = Trip.objects.create(
            pk=101,
            host=self.mei,
            title="Kyoto food lanes weekend",
            summary="Kyoto walkthrough",
            description="Detailed route planning",
            destination="Kyoto",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=2),
            traffic_score=90,
            is_published=True,
        )
        self.trip_arun = Trip.objects.create(
            pk=102,
            host=self.arun,
            title="Patagonia first-light trekking camp",
            summary="Patagonia route",
            description="Altitude planning and camp ops",
            destination="Patagonia",
            starts_at=starts_at + timedelta(days=4),
            ends_at=starts_at + timedelta(days=7),
            traffic_score=84,
            is_published=True,
        )
        self.trip_sahar = Trip.objects.create(
            pk=103,
            host=self.sahar,
            title="Morocco souk to desert circuit",
            summary="Desert route",
            description="Market and camp logistics",
            destination="Morocco",
            starts_at=starts_at + timedelta(days=10),
            ends_at=starts_at + timedelta(days=13),
            traffic_score=82,
            is_published=True,
        )
        self.blog_mei = Blog.objects.create(
            author=self.mei,
            slug="packing-for-swing-weather",
            title="Packing for swing-weather trips without overloading",
            excerpt="Layering checklist",
            body="Body text",
            reads=320,
            reviews_count=0,
            is_published=True,
        )

        now = timezone.now()
        FollowRelation.objects.create(follower=self.arun, following=self.mei)
        EnrollmentRequest.objects.create(
            trip=self.trip_arun,
            requester=self.mei,
            message="Can I join this cycle?",
            status=EnrollmentRequest.STATUS_APPROVED,
            reviewed_by=self.arun,
            reviewed_at=now - timedelta(hours=4),
        )
        EnrollmentRequest.objects.create(
            trip=self.trip_sahar,
            requester=self.mei,
            message="Keeping dates flexible if seats change.",
            status=EnrollmentRequest.STATUS_DENIED,
            reviewed_by=self.sahar,
            reviewed_at=now - timedelta(hours=3),
        )
        Comment.objects.create(
            author=self.arun,
            target_type="trip",
            target_key=str(self.trip_mei.pk),
            target_label=self.trip_mei.title,
            target_url=self.trip_mei.get_absolute_url(),
            text="Strong itinerary structure.",
            parent=None,
        )
        parent_comment = Comment.objects.create(
            author=self.mei,
            target_type="trip",
            target_key=str(self.trip_arun.pk),
            target_label=self.trip_arun.title,
            target_url=self.trip_arun.get_absolute_url(),
            text="Host note for cross-team handoff.",
            parent=None,
        )
        Comment.objects.create(
            author=self.sahar,
            target_type=parent_comment.target_type,
            target_key=parent_comment.target_key,
            target_label=parent_comment.target_label,
            target_url=parent_comment.target_url,
            text="Happy to share my checklist.",
            parent=parent_comment,
        )
        Bookmark.objects.create(
            member=self.arun,
            target_type=Bookmark.TARGET_USER,
            target_key=self.mei.username.lower(),
            target_label=f"@{self.mei.username}",
            target_url=f"/u/{self.mei.username}/",
        )
        Bookmark.objects.create(
            member=self.nora,
            target_type=Bookmark.TARGET_TRIP,
            target_key=str(self.trip_mei.pk),
            target_label=self.trip_mei.title,
            target_url=self.trip_mei.get_absolute_url(),
        )
        Review.objects.create(
            author=self.arun,
            target_type=Review.TARGET_TRIP,
            target_key=str(self.trip_mei.pk),
            target_label=self.trip_mei.title,
            target_url=self.trip_mei.get_absolute_url(),
            rating=5,
            headline="Reliable pacing",
            body="Great route structure and practical pacing.",
        )

    def test_activity_page_requires_login(self) -> None:
        response = self.client.get(reverse("activity:index"))
        expected_redirect = f"{reverse('accounts:login')}?next={reverse('activity:index')}"
        self.assertRedirects(response, expected_redirect, fetch_redirect_response=False)

    def test_activity_page_renders_unified_member_activity_payload(self) -> None:
        self.client.login(username=self.mei.username, password=self.password)
        response = self.client.get(reverse("activity:index"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["activity_mode"], "member-activity")
        self.assertEqual(response.context["activity_filter"], "all")
        self.assertGreaterEqual(response.context["activity_counts"]["all"], 6)
        self.assertEqual(response.context["activity_counts"]["follows"], 1)
        self.assertEqual(response.context["activity_counts"]["enrollment"], 2)
        self.assertEqual(response.context["activity_counts"]["comments"], 1)
        self.assertEqual(response.context["activity_counts"]["replies"], 1)
        self.assertEqual(response.context["activity_counts"]["bookmarks"], 2)
        self.assertEqual(response.context["activity_counts"]["reviews"], 1)

        groups = {item["group"] for item in response.context["activity_items"]}
        self.assertIn("follows", groups)
        self.assertIn("enrollment", groups)
        self.assertIn("comments", groups)
        self.assertIn("replies", groups)
        self.assertIn("bookmarks", groups)
        self.assertIn("reviews", groups)

    def test_activity_filter_bookmarks_returns_bookmark_events_only(self) -> None:
        self.client.login(username=self.mei.username, password=self.password)
        response = self.client.get(f"{reverse('activity:index')}?type=bookmarks")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["activity_filter"], "bookmarks")
        self.assertTrue(response.context["activity_items"])
        for item in response.context["activity_items"]:
            self.assertEqual(item["group"], "bookmarks")

    def test_activity_verbose_query_prints_debug_lines(self) -> None:
        self.client.login(username=self.mei.username, password=self.password)
        with patch("builtins.print") as mock_print:
            response = self.client.get(f"{reverse('activity:index')}?verbose=1")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(mock_print.call_count, 1)
        printed_lines = "\n".join(str(args[0]) for args, _kwargs in mock_print.call_args_list)
        self.assertIn("[activity][verbose]", printed_lines)

    def test_activity_without_verbose_does_not_print_debug_lines(self) -> None:
        self.client.login(username=self.mei.username, password=self.password)
        with patch("builtins.print") as mock_print:
            response = self.client.get(reverse("activity:index"))

        self.assertEqual(response.status_code, 200)
        mock_print.assert_not_called()


class ActivityBootstrapCommandTests(TestCase):
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

        now = timezone.now()
        Trip.objects.create(
            pk=101,
            host=self.mei,
            title="Kyoto food lanes weekend",
            summary="s",
            description="d",
            destination="Kyoto",
            starts_at=now + timedelta(days=10),
            ends_at=now + timedelta(days=12),
            traffic_score=80,
            is_published=True,
        )
        Trip.objects.create(
            pk=102,
            host=self.arun,
            title="Patagonia first-light trekking camp",
            summary="s",
            description="d",
            destination="Patagonia",
            starts_at=now + timedelta(days=15),
            ends_at=now + timedelta(days=18),
            traffic_score=85,
            is_published=True,
        )
        Trip.objects.create(
            pk=103,
            host=self.sahar,
            title="Morocco souk to desert circuit",
            summary="s",
            description="d",
            destination="Morocco",
            starts_at=now + timedelta(days=20),
            ends_at=now + timedelta(days=23),
            traffic_score=83,
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

    def test_bootstrap_activity_seeds_rows_with_verbose_output(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_activity", "--verbose", stdout=stdout)
        output = stdout.getvalue()

        self.assertIn("[activity][verbose]", output)
        self.assertIn("Activity bootstrap complete", output)
        self.assertEqual(FollowRelation.objects.filter(following=self.mei).count(), 3)
        self.assertEqual(
            EnrollmentRequest.objects.filter(
                requester=self.mei,
                status__in=[EnrollmentRequest.STATUS_APPROVED, EnrollmentRequest.STATUS_DENIED],
            ).count(),
            2,
        )
        self.assertEqual(Bookmark.objects.count(), 3)
        self.assertEqual(Review.objects.count(), 2)
        self.assertEqual(Comment.objects.filter(parent__isnull=True).count(), 2)
        self.assertEqual(Comment.objects.filter(parent__isnull=False).count(), 1)

    def test_bootstrap_activity_can_create_missing_members(self) -> None:
        UserModel.objects.all().delete()
        stdout = StringIO()
        call_command(
            "bootstrap_activity",
            "--create-missing-members",
            "--verbose",
            stdout=stdout,
        )
        output = stdout.getvalue()

        self.assertTrue(UserModel.objects.filter(username="mei").exists())
        self.assertTrue(UserModel.objects.filter(username="arun").exists())
        self.assertTrue(UserModel.objects.filter(username="sahar").exists())
        self.assertTrue(UserModel.objects.filter(username="nora").exists())
        self.assertIn("created_members=", output)
        self.assertIn("Activity bootstrap complete", output)
