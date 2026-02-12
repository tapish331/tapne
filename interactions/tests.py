from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db.models import Q
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from blogs.models import Blog
from trips.models import Trip

from .models import Comment, DirectMessage, DirectMessageThread, resolve_comment_target

UserModel = get_user_model()


class InteractionViewsTests(TestCase):
    def setUp(self) -> None:
        self.password = "InteractionsPass!123456"
        self.host = UserModel.objects.create_user(
            username="host-interactions",
            email="host-interactions@example.com",
            password=self.password,
        )
        self.member = UserModel.objects.create_user(
            username="member-interactions",
            email="member-interactions@example.com",
            password=self.password,
        )
        self.target = UserModel.objects.create_user(
            username="target-interactions",
            email="target-interactions@example.com",
            password=self.password,
        )
        self.other = UserModel.objects.create_user(
            username="other-interactions",
            email="other-interactions@example.com",
            password=self.password,
        )

        starts_at = timezone.now() + timedelta(days=7)
        self.trip = Trip.objects.create(
            host=self.host,
            title="Interactions trip",
            summary="Trip summary",
            description="Trip description",
            destination="Naples",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=2),
            traffic_score=44,
            is_published=True,
        )
        self.blog = Blog.objects.create(
            author=self.host,
            slug="interactions-blog",
            title="Interactions blog",
            excerpt="Blog excerpt",
            body="Blog body",
            reads=100,
            reviews_count=2,
            is_published=True,
        )

    def _thread_between(self, user_a: object, user_b: object) -> DirectMessageThread:
        user_a_id = int(getattr(user_a, "pk", 0) or 0)
        user_b_id = int(getattr(user_b, "pk", 0) or 0)
        return DirectMessageThread.objects.get(
            Q(member_one_id=user_a_id, member_two_id=user_b_id)
            | Q(member_one_id=user_b_id, member_two_id=user_a_id)
        )

    def test_comment_requires_login(self) -> None:
        response = self.client.post(
            reverse("interactions:comment"),
            {
                "target_type": "trip",
                "target_id": str(self.trip.pk),
                "text": "Looks great.",
            },
        )
        expected_redirect = f"{reverse('accounts:login')}?next={reverse('interactions:comment')}"
        self.assertRedirects(response, expected_redirect, fetch_redirect_response=False)

    def test_member_can_post_trip_comment(self) -> None:
        self.client.login(username=self.member.username, password=self.password)
        response = self.client.post(
            reverse("interactions:comment"),
            {
                "target_type": "trip",
                "target_id": str(self.trip.pk),
                "text": "  Great route.   Is luggage transfer included? ",
                "next": reverse("trips:detail", kwargs={"trip_id": self.trip.pk}),
            },
        )

        self.assertRedirects(response, reverse("trips:detail", kwargs={"trip_id": self.trip.pk}))
        comment = Comment.objects.get(author=self.member, parent__isnull=True)
        self.assertEqual(comment.target_type, "trip")
        self.assertEqual(comment.target_key, str(self.trip.pk))
        self.assertEqual(comment.text, "Great route. Is luggage transfer included?")

    def test_member_can_reply_to_blog_comment(self) -> None:
        target = resolve_comment_target("blog", self.blog.slug)
        assert target is not None
        parent = Comment.objects.create(
            author=self.target,
            target_type=target.target_type,
            target_key=target.target_key,
            target_label=target.target_label,
            target_url=target.target_url,
            text="What did you use for your packing split?",
        )

        self.client.login(username=self.member.username, password=self.password)
        response = self.client.post(
            reverse("interactions:reply"),
            {
                "comment_id": str(parent.pk),
                "text": "  Two cubes for clothes and one for weather layers. ",
                "next": reverse("blogs:detail", kwargs={"slug": self.blog.slug}),
            },
        )

        self.assertRedirects(response, reverse("blogs:detail", kwargs={"slug": self.blog.slug}))
        reply = Comment.objects.get(parent=parent, author=self.member)
        self.assertEqual(reply.text, "Two cubes for clothes and one for weather layers.")
        self.assertEqual(reply.target_type, parent.target_type)
        self.assertEqual(reply.target_key, parent.target_key)

    def test_invalid_comment_target_type_is_rejected(self) -> None:
        self.client.login(username=self.member.username, password=self.password)
        response = self.client.post(
            reverse("interactions:comment"),
            {
                "target_type": "user",
                "target_id": "someone",
                "text": "This should fail.",
                "next": reverse("home"),
            },
        )

        self.assertRedirects(response, reverse("home"))
        self.assertEqual(Comment.objects.count(), 0)

    def test_dm_inbox_requires_login(self) -> None:
        response = self.client.get(reverse("interactions:dm-inbox"))
        expected_redirect = f"{reverse('accounts:login')}?next={reverse('interactions:dm-inbox')}"
        self.assertRedirects(response, expected_redirect, fetch_redirect_response=False)

    def test_dm_open_requires_login(self) -> None:
        response = self.client.post(
            reverse("interactions:dm-open"),
            {
                "with": self.target.username,
            },
        )
        expected_redirect = f"{reverse('accounts:login')}?next={reverse('interactions:dm-open')}"
        self.assertRedirects(response, expected_redirect, fetch_redirect_response=False)

    def test_dm_inbox_get_with_query_does_not_create_thread(self) -> None:
        self.client.login(username=self.member.username, password=self.password)
        response = self.client.get(f"{reverse('interactions:dm-inbox')}?with={self.target.username}")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            DirectMessageThread.objects.filter(
                Q(member_one=self.member, member_two=self.target)
                | Q(member_one=self.target, member_two=self.member)
            ).exists()
        )

    def test_dm_open_post_creates_thread_and_redirects(self) -> None:
        self.client.login(username=self.member.username, password=self.password)
        response = self.client.post(
            reverse("interactions:dm-open"),
            {
                "with": self.target.username,
                "next": reverse("interactions:dm-inbox"),
            },
        )

        thread = self._thread_between(self.member, self.target)
        self.assertRedirects(
            response,
            reverse("interactions:dm-thread", kwargs={"thread_id": thread.pk}),
        )

    def test_dm_thread_is_participant_only(self) -> None:
        DirectMessageThread.objects.create(
            member_one=self.member if int(self.member.pk) < int(self.target.pk) else self.target,
            member_two=self.target if int(self.member.pk) < int(self.target.pk) else self.member,
        )
        thread = self._thread_between(self.member, self.target)

        self.client.login(username=self.other.username, password=self.password)
        response = self.client.get(reverse("interactions:dm-thread", kwargs={"thread_id": thread.pk}))
        self.assertEqual(response.status_code, 404)

    def test_dm_send_creates_message_for_participant(self) -> None:
        DirectMessageThread.objects.create(
            member_one=self.member if int(self.member.pk) < int(self.target.pk) else self.target,
            member_two=self.target if int(self.member.pk) < int(self.target.pk) else self.member,
        )
        thread = self._thread_between(self.member, self.target)

        self.client.login(username=self.member.username, password=self.password)
        response = self.client.post(
            reverse("interactions:dm-send", kwargs={"thread_id": thread.pk}),
            {
                "text": "  See you at the airport gate at 07:30. ",
                "next": reverse("interactions:dm-thread", kwargs={"thread_id": thread.pk}),
            },
        )

        self.assertRedirects(
            response,
            reverse("interactions:dm-thread", kwargs={"thread_id": thread.pk}),
        )
        message = DirectMessage.objects.get(thread=thread, sender=self.member)
        self.assertEqual(message.body, "See you at the airport gate at 07:30.")

    def test_dm_inbox_verbose_query_prints_debug_lines(self) -> None:
        self.client.login(username=self.member.username, password=self.password)

        with patch("builtins.print") as mock_print:
            response = self.client.get(f"{reverse('interactions:dm-inbox')}?verbose=1")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(mock_print.call_count, 1)
        printed_lines = "\n".join(str(args[0]) for args, _kwargs in mock_print.call_args_list)
        self.assertIn("[interactions][verbose]", printed_lines)

    def test_comment_post_without_verbose_does_not_print_debug_lines(self) -> None:
        self.client.login(username=self.member.username, password=self.password)

        with patch("builtins.print") as mock_print:
            response = self.client.post(
                reverse("interactions:comment"),
                {
                    "target_type": "trip",
                    "target_id": str(self.trip.pk),
                    "text": "Looks solid.",
                    "next": reverse("trips:detail", kwargs={"trip_id": self.trip.pk}),
                },
            )

        self.assertRedirects(response, reverse("trips:detail", kwargs={"trip_id": self.trip.pk}))
        mock_print.assert_not_called()


class InteractionsBootstrapCommandTests(TestCase):
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

    def test_bootstrap_interactions_seeds_rows_with_verbose_output(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_interactions", "--verbose", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(Comment.objects.filter(parent__isnull=True).count(), 4)
        self.assertEqual(Comment.objects.filter(parent__isnull=False).count(), 3)
        self.assertEqual(DirectMessageThread.objects.count(), 2)
        self.assertEqual(DirectMessage.objects.count(), 4)
        self.assertIn("[interactions][verbose]", output)
        self.assertIn("Interactions bootstrap complete", output)

    def test_bootstrap_interactions_can_create_missing_members(self) -> None:
        UserModel.objects.all().delete()
        stdout = StringIO()
        call_command(
            "bootstrap_interactions",
            "--create-missing-members",
            "--verbose",
            stdout=stdout,
        )
        output = stdout.getvalue()

        self.assertTrue(UserModel.objects.filter(username="mei").exists())
        self.assertTrue(UserModel.objects.filter(username="arun").exists())
        self.assertTrue(UserModel.objects.filter(username="sahar").exists())
        self.assertEqual(Comment.objects.count(), 7)
        self.assertEqual(DirectMessageThread.objects.count(), 2)
        self.assertIn("created_members=3", output)

    def test_bootstrap_interactions_skips_when_members_are_missing(self) -> None:
        UserModel.objects.all().delete()
        stdout = StringIO()
        call_command("bootstrap_interactions", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(Comment.objects.count(), 0)
        self.assertEqual(DirectMessage.objects.count(), 0)
        self.assertIn("skipped_comment_rows", output)
