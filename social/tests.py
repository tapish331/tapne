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
from feed.models import MemberFeedPreference
from trips.models import Trip

from .models import Bookmark, FollowRelation

UserModel = get_user_model()


class SocialViewsTests(TestCase):
    def setUp(self) -> None:
        self.password = "SocialPass!123456"
        self.member = UserModel.objects.create_user(
            username="member-social",
            email="member-social@example.com",
            password=self.password,
        )
        self.target = UserModel.objects.create_user(
            username="target-social",
            email="target-social@example.com",
            password=self.password,
        )
        self.other = UserModel.objects.create_user(
            username="other-social",
            email="other-social@example.com",
            password=self.password,
        )

        starts_at = timezone.now() + timedelta(days=9)
        self.trip = Trip.objects.create(
            host=self.target,
            title="Bookmarked trip",
            summary="Trip summary",
            description="Trip description",
            destination="Lisbon",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=2),
            traffic_score=25,
            is_published=True,
        )
        self.blog = Blog.objects.create(
            author=self.target,
            slug="bookmarked-blog",
            title="Bookmarked blog",
            excerpt="Blog excerpt",
            body="Blog body",
            reads=120,
            reviews_count=4,
            is_published=True,
        )

    def test_follow_requires_login(self) -> None:
        response = self.client.post(
            reverse("social:follow", kwargs={"username": self.target.username})
        )
        expected_redirect = (
            f"{reverse('accounts:login')}?next={reverse('social:follow', kwargs={'username': self.target.username})}"
        )
        self.assertRedirects(response, expected_redirect, fetch_redirect_response=False)

    def test_follow_post_creates_relation_and_syncs_feed_preference(self) -> None:
        self.client.login(username=self.member.username, password=self.password)

        response = self.client.post(
            reverse("social:follow", kwargs={"username": self.target.username}),
            {"next": reverse("public-profile", kwargs={"username": self.target.username})},
        )

        self.assertRedirects(
            response,
            reverse("public-profile", kwargs={"username": self.target.username}),
        )
        self.assertTrue(
            FollowRelation.objects.filter(
                follower=self.member,
                following=self.target,
            ).exists()
        )

        preference = MemberFeedPreference.objects.get(user=self.member)
        self.assertEqual(preference.followed_usernames, [self.target.username.lower()])

    def test_follow_self_is_blocked(self) -> None:
        self.client.login(username=self.member.username, password=self.password)

        response = self.client.post(
            reverse("social:follow", kwargs={"username": self.member.username}),
            {"next": reverse("accounts:me")},
        )

        self.assertRedirects(response, reverse("accounts:me"))
        self.assertFalse(FollowRelation.objects.filter(follower=self.member).exists())

    def test_unfollow_post_deletes_relation_and_syncs_feed_preference(self) -> None:
        FollowRelation.objects.create(follower=self.member, following=self.target)
        MemberFeedPreference.objects.create(
            user=self.member,
            followed_usernames=[self.target.username.lower()],
            interest_keywords=["route"],
        )

        self.client.login(username=self.member.username, password=self.password)
        response = self.client.post(
            reverse("social:unfollow", kwargs={"username": self.target.username}),
            {"next": reverse("accounts:me")},
        )

        self.assertRedirects(response, reverse("accounts:me"))
        self.assertFalse(
            FollowRelation.objects.filter(
                follower=self.member,
                following=self.target,
            ).exists()
        )

        preference = MemberFeedPreference.objects.get(user=self.member)
        self.assertEqual(preference.followed_usernames, [])
        self.assertEqual(preference.interest_keywords, ["route"])

    def test_bookmark_requires_login(self) -> None:
        response = self.client.post(
            reverse("social:bookmark"),
            {"type": "trip", "id": str(self.trip.pk)},
        )
        expected_redirect = f"{reverse('accounts:login')}?next={reverse('social:bookmark')}"
        self.assertRedirects(response, expected_redirect, fetch_redirect_response=False)

    def test_bookmark_trip_blog_user_deduplicates_rows(self) -> None:
        self.client.login(username=self.member.username, password=self.password)

        trip_response = self.client.post(
            reverse("social:bookmark"),
            {"type": "trip", "id": str(self.trip.pk), "next": reverse("social:bookmarks")},
        )
        self.assertRedirects(trip_response, reverse("social:bookmarks"))

        duplicate_trip_response = self.client.post(
            reverse("social:bookmark"),
            {"type": "trip", "id": str(self.trip.pk), "next": reverse("social:bookmarks")},
        )
        self.assertRedirects(duplicate_trip_response, reverse("social:bookmarks"))

        user_response = self.client.post(
            reverse("social:bookmark"),
            {"type": "user", "id": self.target.username, "next": reverse("social:bookmarks")},
        )
        self.assertRedirects(user_response, reverse("social:bookmarks"))

        blog_response = self.client.post(
            reverse("social:bookmark"),
            {"type": "blog", "id": self.blog.slug, "next": reverse("social:bookmarks")},
        )
        self.assertRedirects(blog_response, reverse("social:bookmarks"))

        self.assertEqual(
            Bookmark.objects.filter(member=self.member, target_type="trip").count(),
            1,
        )
        self.assertEqual(
            Bookmark.objects.filter(member=self.member, target_type="user").count(),
            1,
        )
        self.assertEqual(
            Bookmark.objects.filter(member=self.member, target_type="blog").count(),
            1,
        )

    def test_unbookmark_removes_row(self) -> None:
        Bookmark.objects.create(
            member=self.member,
            target_type="trip",
            target_key=str(self.trip.pk),
            target_label=self.trip.title,
            target_url=self.trip.get_absolute_url(),
        )

        self.client.login(username=self.member.username, password=self.password)
        response = self.client.post(
            reverse("social:unbookmark"),
            {"type": "trip", "id": str(self.trip.pk), "next": reverse("social:bookmarks")},
        )

        self.assertRedirects(response, reverse("social:bookmarks"))
        self.assertFalse(Bookmark.objects.filter(member=self.member, target_type="trip").exists())

    def test_bookmarks_view_requires_login(self) -> None:
        response = self.client.get(reverse("social:bookmarks"))
        expected_redirect = f"{reverse('accounts:login')}?next={reverse('social:bookmarks')}"
        self.assertRedirects(response, expected_redirect, fetch_redirect_response=False)

    def test_bookmarks_view_renders_payload_for_member(self) -> None:
        Bookmark.objects.create(
            member=self.member,
            target_type="trip",
            target_key=str(self.trip.pk),
            target_label=self.trip.title,
            target_url=self.trip.get_absolute_url(),
        )
        Bookmark.objects.create(
            member=self.member,
            target_type="user",
            target_key=self.target.username.lower(),
            target_label=f"@{self.target.username}",
            target_url=f"/u/{self.target.username}/",
        )
        Bookmark.objects.create(
            member=self.member,
            target_type="blog",
            target_key=self.blog.slug.lower(),
            target_label=self.blog.title,
            target_url=self.blog.get_absolute_url(),
        )

        self.client.login(username=self.member.username, password=self.password)
        response = self.client.get(reverse("social:bookmarks"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["bookmark_mode"], "member-bookmarks")
        self.assertEqual(response.context["bookmark_counts"]["trip"], 1)
        self.assertEqual(response.context["bookmark_counts"]["user"], 1)
        self.assertEqual(response.context["bookmark_counts"]["blog"], 1)
        self.assertEqual(response.context["bookmarked_trips"][0]["id"], self.trip.pk)
        self.assertEqual(response.context["bookmarked_profiles"][0]["username"], self.target.username)
        self.assertEqual(response.context["bookmarked_blogs"][0]["slug"], self.blog.slug)

    def test_bookmarks_verbose_query_prints_debug_lines(self) -> None:
        self.client.login(username=self.member.username, password=self.password)

        with patch("builtins.print") as mock_print:
            response = self.client.get(f"{reverse('social:bookmarks')}?verbose=1")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(mock_print.call_count, 1)
        printed_lines = "\n".join(str(args[0]) for args, _kwargs in mock_print.call_args_list)
        self.assertIn("[social][verbose]", printed_lines)

    def test_follow_post_without_verbose_does_not_print_debug_lines(self) -> None:
        self.client.login(username=self.member.username, password=self.password)

        with patch("builtins.print") as mock_print:
            response = self.client.post(
                reverse("social:follow", kwargs={"username": self.other.username}),
                {"next": reverse("social:bookmarks")},
            )

        self.assertRedirects(response, reverse("social:bookmarks"))
        mock_print.assert_not_called()


class SocialBootstrapCommandTests(TestCase):
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
        Trip.objects.create(
            pk=103,
            host=self.sahar,
            title="Morocco souk to desert circuit",
            summary="s",
            description="d",
            destination="Morocco",
            starts_at=now + timedelta(days=28),
            ends_at=now + timedelta(days=32),
            traffic_score=80,
            is_published=True,
        )

        Blog.objects.create(
            pk=301,
            author=self.mei,
            slug="packing-for-swing-weather",
            title="Packing for swing-weather trips without overloading",
            excerpt="e",
            body="b",
            is_published=True,
        )
        Blog.objects.create(
            pk=302,
            author=self.arun,
            slug="first-group-trip-ops-checklist",
            title="First group-trip operations checklist",
            excerpt="e",
            body="b",
            is_published=True,
        )
        Blog.objects.create(
            pk=303,
            author=self.sahar,
            slug="how-to-run-a-desert-route",
            title="How to run a desert route without chaos",
            excerpt="e",
            body="b",
            is_published=True,
        )

    def test_bootstrap_social_creates_follows_and_bookmarks_with_verbose_output(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_social", "--verbose", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(FollowRelation.objects.count(), 3)
        self.assertEqual(Bookmark.objects.count(), 9)
        self.assertEqual(MemberFeedPreference.objects.count(), 3)
        self.assertIn("[social][verbose]", output)
        self.assertIn("Social bootstrap complete", output)

    def test_bootstrap_social_can_create_missing_members(self) -> None:
        UserModel.objects.all().delete()
        stdout = StringIO()
        call_command(
            "bootstrap_social",
            "--create-missing-members",
            "--verbose",
            stdout=stdout,
        )
        output = stdout.getvalue()

        self.assertTrue(UserModel.objects.filter(username="mei").exists())
        self.assertTrue(UserModel.objects.filter(username="arun").exists())
        self.assertTrue(UserModel.objects.filter(username="sahar").exists())
        self.assertEqual(FollowRelation.objects.count(), 3)
        self.assertIn("created_members=", output)
