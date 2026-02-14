from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from feed.models import MemberFeedPreference

from .models import Blog

UserModel = get_user_model()


class BlogViewsTests(TestCase):
    def setUp(self) -> None:
        self.password = "BlogsPass!123456"
        self.author_user = UserModel.objects.create_user(
            username="author-user",
            email="author-user@example.com",
            password=self.password,
        )
        self.member_user = UserModel.objects.create_user(
            username="member-user",
            email="member-user@example.com",
            password=self.password,
        )

    def test_guest_blog_list_uses_demo_fallback_when_no_live_rows(self) -> None:
        response = self.client.get(reverse("blogs:list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["blog_source"], "demo-fallback")
        self.assertEqual(response.context["blog_mode"], "guest-most-read-demo")
        self.assertGreater(len(response.context["blogs"]), 0)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_guest_blog_list_is_live_only_when_demo_catalog_disabled(self) -> None:
        response = self.client.get(reverse("blogs:list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["blog_source"], "live-db")
        self.assertEqual(response.context["blog_mode"], "guest-most-read-live")
        self.assertEqual(response.context["blogs"], [])

    def test_member_blog_list_uses_live_rows_and_preference_boost(self) -> None:
        Blog.objects.create(
            author=self.author_user,
            slug="baseline-blog",
            title="Baseline blog",
            excerpt="Standard row",
            body="Default member row",
            reads=900,
            reviews_count=10,
            is_published=True,
        )

        boosted_author = UserModel.objects.create_user(
            username="boosted-author",
            email="boosted-author@example.com",
            password=self.password,
        )
        Blog.objects.create(
            author=boosted_author,
            slug="boosted-blog",
            title="Boosted preference blog",
            excerpt="Preferred author",
            body="Should rank first for member preference",
            reads=10,
            reviews_count=1,
            is_published=True,
        )

        MemberFeedPreference.objects.create(
            user=self.member_user,
            followed_usernames=["boosted-author"],
            interest_keywords=["route"],
        )

        self.client.login(username=self.member_user.username, password=self.password)
        response = self.client.get(reverse("blogs:list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["blog_source"], "live-db")
        self.assertEqual(response.context["blog_mode"], "member-like-minded-live")
        self.assertEqual(response.context["blogs"][0]["author_username"], "boosted-author")

    def test_blog_detail_shows_full_body_for_guest(self) -> None:
        blog = Blog.objects.create(
            author=self.author_user,
            slug="guest-visible-blog",
            title="Guest visible blog",
            excerpt="Guest excerpt",
            body="Guests should see full blog content in detail mode.",
            reads=50,
            reviews_count=2,
            is_published=True,
        )

        response = self.client.get(reverse("blogs:detail", kwargs={"slug": blog.slug}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["blog_detail_mode"], "guest-full")
        self.assertIn("Guests should see full blog content", response.context["blog"]["body"])
        self.assertFalse(response.context["can_manage_blog"])

    def test_unpublished_blog_is_visible_to_owner(self) -> None:
        blog = Blog.objects.create(
            author=self.author_user,
            slug="owner-draft-blog",
            title="Owner draft blog",
            excerpt="Draft excerpt",
            body="Draft body for owner visibility check.",
            reads=0,
            reviews_count=0,
            is_published=False,
        )

        self.client.login(username=self.author_user.username, password=self.password)
        response = self.client.get(reverse("blogs:detail", kwargs={"slug": blog.slug}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["blog_detail_source"], "live-db")
        self.assertEqual(response.context["blog_detail_mode"], "member-full")
        self.assertTrue(response.context["can_manage_blog"])
        self.assertIn("Draft body for owner visibility check", response.context["blog"]["body"])

    def test_unpublished_blog_is_hidden_from_guest(self) -> None:
        Blog.objects.create(
            author=self.author_user,
            slug="guest-hidden-draft-blog",
            title="Guest hidden draft blog",
            excerpt="Draft excerpt",
            body="This unpublished draft should not be visible to guests.",
            reads=0,
            reviews_count=0,
            is_published=False,
        )

        response = self.client.get(reverse("blogs:detail", kwargs={"slug": "guest-hidden-draft-blog"}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["blog_detail_source"], "synthetic-fallback")
        self.assertNotIn("This unpublished draft", response.context["blog"]["body"])

    def test_blog_create_requires_login(self) -> None:
        response = self.client.get(reverse("blogs:create"))
        expected_redirect = f"{reverse('accounts:login')}?next={reverse('blogs:create')}"
        self.assertRedirects(response, expected_redirect, fetch_redirect_response=False)

    def test_blog_create_post_creates_blog_for_logged_in_member(self) -> None:
        self.client.login(username=self.member_user.username, password=self.password)

        response = self.client.post(
            reverse("blogs:create"),
            {
                "title": "Created blog title",
                "slug": "",
                "excerpt": "Created excerpt",
                "body": "Created detail body",
                "is_published": "on",
            },
        )

        created_blog = Blog.objects.get(title="Created blog title")
        self.assertRedirects(response, reverse("blogs:detail", kwargs={"slug": created_blog.slug}))
        self.assertEqual(created_blog.author, self.member_user)
        self.assertEqual(created_blog.slug, "created-blog-title")

    def test_blog_edit_is_owner_only(self) -> None:
        blog = Blog.objects.create(
            author=self.author_user,
            slug="owner-only-blog",
            title="Owner only blog",
            excerpt="e",
            body="d",
            reads=0,
            reviews_count=0,
            is_published=True,
        )

        self.client.login(username=self.member_user.username, password=self.password)
        response = self.client.get(reverse("blogs:edit", kwargs={"slug": blog.slug}))
        self.assertEqual(response.status_code, 404)

    def test_blog_delete_requires_post(self) -> None:
        blog = Blog.objects.create(
            author=self.author_user,
            slug="delete-method-blog",
            title="Delete method blog",
            excerpt="e",
            body="d",
            reads=0,
            reviews_count=0,
            is_published=True,
        )

        self.client.login(username=self.author_user.username, password=self.password)
        response = self.client.get(reverse("blogs:delete", kwargs={"slug": blog.slug}))
        self.assertEqual(response.status_code, 405)

    def test_blog_list_verbose_query_prints_debug_lines(self) -> None:
        with patch("builtins.print") as mock_print:
            response = self.client.get(f"{reverse('blogs:list')}?verbose=1")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(mock_print.call_count, 1)
        printed_lines = "\n".join(str(args[0]) for args, _kwargs in mock_print.call_args_list)
        self.assertIn("[blogs][verbose]", printed_lines)

    def test_blog_list_without_verbose_query_does_not_print_debug_lines(self) -> None:
        with patch("builtins.print") as mock_print:
            response = self.client.get(reverse("blogs:list"))

        self.assertEqual(response.status_code, 200)
        mock_print.assert_not_called()


class BlogsBootstrapCommandTests(TestCase):
    def test_bootstrap_blogs_seeds_rows_with_verbose_output(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_blogs", "--create-missing-authors", "--verbose", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(Blog.objects.count(), 3)
        self.assertIn("[blogs][verbose]", output)
        self.assertIn("Blogs bootstrap complete", output)

    def test_bootstrap_blogs_skips_when_authors_are_missing(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_blogs", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(Blog.objects.count(), 0)
        self.assertIn("skipped=3", output)
