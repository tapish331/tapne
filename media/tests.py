from __future__ import annotations

import shutil
import tempfile
from datetime import timedelta
from io import BytesIO
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from blogs.models import Blog
from reviews.models import Review
from trips.models import Trip

from .models import MediaAsset, MediaAttachment

UserModel = get_user_model()


def _build_sample_png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (1, 1), color=(32, 160, 141)).save(buffer, format="PNG")
    return buffer.getvalue()


SAMPLE_PNG_BYTES = _build_sample_png_bytes()


class MediaViewsTests(TestCase):
    def setUp(self) -> None:
        self.media_root = Path(tempfile.mkdtemp(prefix="tapne-media-tests-"))
        self.override = override_settings(
            MEDIA_ROOT=self.media_root,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            },
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(lambda: shutil.rmtree(self.media_root, ignore_errors=True))

        self.password = "MediaPass!123456"
        self.host = UserModel.objects.create_user(
            username="host-media",
            email="host-media@example.com",
            password=self.password,
        )
        self.member = UserModel.objects.create_user(
            username="member-media",
            email="member-media@example.com",
            password=self.password,
        )

        starts_at = timezone.now() + timedelta(days=10)
        self.trip = Trip.objects.create(
            host=self.host,
            title="Media target trip",
            summary="Trip summary",
            description="Trip description",
            destination="Tokyo",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=2),
            traffic_score=40,
            is_published=True,
        )
        self.blog = Blog.objects.create(
            author=self.host,
            slug="media-target-blog",
            title="Media target blog",
            excerpt="Blog excerpt",
            body="Blog body",
            reads=100,
            reviews_count=0,
            is_published=True,
        )
        self.review = Review.objects.create(
            author=self.member,
            target_type=Review.TARGET_TRIP,
            target_key=str(self.trip.pk),
            target_label=self.trip.title,
            target_url=self.trip.get_absolute_url(),
            rating=5,
            headline="Strong host prep",
            body="Clear logistics and pacing.",
        )

    def _image_file(self, name: str = "upload.png") -> SimpleUploadedFile:
        return SimpleUploadedFile(name=name, content=SAMPLE_PNG_BYTES, content_type="image/png")

    def _invalid_file(self) -> SimpleUploadedFile:
        return SimpleUploadedFile(name="notes.txt", content=b"not media", content_type="text/plain")

    def test_media_upload_requires_login(self) -> None:
        response = self.client.post(
            reverse("media:upload"),
            {
                "target_type": "trip",
                "target_id": str(self.trip.pk),
                "file": self._image_file(),
            },
        )

        expected_redirect = f"{reverse('accounts:login')}?next={reverse('media:upload')}"
        self.assertRedirects(response, expected_redirect, fetch_redirect_response=False)

    def test_host_can_upload_trip_media_and_trip_detail_includes_it(self) -> None:
        self.client.login(username=self.host.username, password=self.password)

        response = self.client.post(
            reverse("media:upload"),
            {
                "target_type": "trip",
                "target_id": str(self.trip.pk),
                "caption": "  Route board from day zero  ",
                "next": reverse("trips:detail", kwargs={"trip_id": self.trip.pk}),
                "file": self._image_file(),
            },
        )

        self.assertRedirects(response, reverse("trips:detail", kwargs={"trip_id": self.trip.pk}))
        self.assertEqual(MediaAsset.objects.count(), 1)
        self.assertEqual(MediaAttachment.objects.count(), 1)

        detail_response = self.client.get(reverse("trips:detail", kwargs={"trip_id": self.trip.pk}))
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(len(detail_response.context["trip_media_items"]), 1)
        self.assertTrue(detail_response.context["trip_media_can_upload"])
        self.assertEqual(detail_response.context["trip_media_items"][0]["caption"], "Route board from day zero")

    def test_non_owner_cannot_upload_media_for_trip(self) -> None:
        self.client.login(username=self.member.username, password=self.password)

        response = self.client.post(
            reverse("media:upload"),
            {
                "target_type": "trip",
                "target_id": str(self.trip.pk),
                "next": reverse("trips:detail", kwargs={"trip_id": self.trip.pk}),
                "file": self._image_file(),
            },
        )

        self.assertRedirects(response, reverse("trips:detail", kwargs={"trip_id": self.trip.pk}))
        self.assertEqual(MediaAsset.objects.count(), 0)
        self.assertEqual(MediaAttachment.objects.count(), 0)

    def test_invalid_content_type_upload_is_rejected(self) -> None:
        self.client.login(username=self.host.username, password=self.password)

        response = self.client.post(
            reverse("media:upload"),
            {
                "target_type": "blog",
                "target_id": self.blog.slug,
                "next": reverse("blogs:detail", kwargs={"slug": self.blog.slug}),
                "file": self._invalid_file(),
            },
        )

        self.assertRedirects(response, reverse("blogs:detail", kwargs={"slug": self.blog.slug}))
        self.assertEqual(MediaAsset.objects.count(), 0)

    def test_member_can_upload_media_for_own_review(self) -> None:
        self.client.login(username=self.member.username, password=self.password)

        response = self.client.post(
            reverse("media:upload"),
            {
                "target_type": "review",
                "target_id": str(self.review.pk),
                "next": reverse("reviews:target-list", kwargs={"target_type": "trip", "target_id": str(self.trip.pk)}),
                "file": self._image_file(name="review-media.png"),
            },
        )

        self.assertRedirects(
            response,
            reverse("reviews:target-list", kwargs={"target_type": "trip", "target_id": str(self.trip.pk)}),
        )
        self.assertTrue(
            MediaAttachment.objects.filter(
                target_type="review",
                target_key=str(self.review.pk),
            ).exists()
        )

    def test_review_list_context_includes_review_media_attachments(self) -> None:
        self.client.login(username=self.member.username, password=self.password)
        self.client.post(
            reverse("media:upload"),
            {
                "target_type": "review",
                "target_id": str(self.review.pk),
                "next": reverse("reviews:target-list", kwargs={"target_type": "trip", "target_id": str(self.trip.pk)}),
                "file": self._image_file(name="review-wire.png"),
            },
        )

        response = self.client.get(
            reverse("reviews:target-list", kwargs={"target_type": "trip", "target_id": str(self.trip.pk)})
        )

        self.assertEqual(response.status_code, 200)
        first_review = response.context["review_items"][0]
        self.assertIn("media_attachments", first_review)
        self.assertGreaterEqual(len(first_review["media_attachments"]), 1)

    def test_media_delete_is_owner_scoped(self) -> None:
        upload_owner = self.host
        self.client.login(username=upload_owner.username, password=self.password)
        self.client.post(
            reverse("media:upload"),
            {
                "target_type": "trip",
                "target_id": str(self.trip.pk),
                "next": reverse("trips:detail", kwargs={"trip_id": self.trip.pk}),
                "file": self._image_file(name="delete-me.png"),
            },
        )
        attachment = MediaAttachment.objects.first()
        self.assertIsNotNone(attachment)
        assert attachment is not None

        self.client.logout()
        self.client.login(username=self.member.username, password=self.password)
        forbidden_response = self.client.post(
            reverse("media:delete", kwargs={"attachment_id": int(attachment.pk)}),
            {"next": reverse("trips:detail", kwargs={"trip_id": self.trip.pk})},
        )
        self.assertRedirects(forbidden_response, reverse("trips:detail", kwargs={"trip_id": self.trip.pk}))
        self.assertTrue(MediaAttachment.objects.filter(pk=int(attachment.pk)).exists())

        self.client.logout()
        self.client.login(username=upload_owner.username, password=self.password)
        allowed_response = self.client.post(
            reverse("media:delete", kwargs={"attachment_id": int(attachment.pk)}),
            {"next": reverse("trips:detail", kwargs={"trip_id": self.trip.pk})},
        )
        self.assertRedirects(allowed_response, reverse("trips:detail", kwargs={"trip_id": self.trip.pk}))
        self.assertFalse(MediaAttachment.objects.filter(pk=int(attachment.pk)).exists())
        self.assertEqual(MediaAsset.objects.count(), 0)

    def test_media_upload_verbose_post_prints_debug_lines(self) -> None:
        self.client.login(username=self.host.username, password=self.password)

        with patch("builtins.print") as mock_print:
            response = self.client.post(
                reverse("media:upload"),
                {
                    "target_type": "trip",
                    "target_id": str(self.trip.pk),
                    "verbose": "1",
                    "next": reverse("trips:detail", kwargs={"trip_id": self.trip.pk}),
                    "file": self._image_file(name="verbose.png"),
                },
            )

        self.assertRedirects(response, reverse("trips:detail", kwargs={"trip_id": self.trip.pk}))
        self.assertGreaterEqual(mock_print.call_count, 1)
        printed_lines = "\n".join(str(args[0]) for args, _kwargs in mock_print.call_args_list)
        self.assertIn("[media][verbose]", printed_lines)


class MediaBootstrapCommandTests(TestCase):
    def setUp(self) -> None:
        self.media_root = Path(tempfile.mkdtemp(prefix="tapne-media-bootstrap-tests-"))
        self.override = override_settings(
            MEDIA_ROOT=self.media_root,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            },
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(lambda: shutil.rmtree(self.media_root, ignore_errors=True))

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

        now = timezone.now()
        self.trip_101 = Trip.objects.create(
            pk=101,
            host=self.mei,
            title="Kyoto food lanes weekend",
            summary="summary",
            description="description",
            destination="Kyoto",
            starts_at=now + timedelta(days=12),
            ends_at=now + timedelta(days=14),
            traffic_score=92,
            is_published=True,
        )
        self.trip_102 = Trip.objects.create(
            pk=102,
            host=self.arun,
            title="Patagonia first-light trekking camp",
            summary="summary",
            description="description",
            destination="Patagonia",
            starts_at=now + timedelta(days=20),
            ends_at=now + timedelta(days=24),
            traffic_score=87,
            is_published=True,
        )
        self.blog = Blog.objects.create(
            author=self.mei,
            slug="packing-for-swing-weather",
            title="Packing for swing-weather trips without overloading",
            excerpt="excerpt",
            body="body",
            reads=7200,
            reviews_count=0,
            is_published=True,
        )
        Review.objects.create(
            author=self.mei,
            target_type=Review.TARGET_TRIP,
            target_key="101",
            target_label=self.trip_101.title,
            target_url=self.trip_101.get_absolute_url(),
            rating=5,
            headline="Bootstrap review",
            body="Review row used by bootstrap_media review attachment seed.",
        )

    def test_bootstrap_media_seeds_uploads_with_verbose_output(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_media", "--verbose", stdout=stdout)
        output = stdout.getvalue()

        self.assertGreaterEqual(MediaAsset.objects.count(), 2)
        self.assertGreaterEqual(MediaAttachment.objects.count(), 3)
        self.assertIn("[media][verbose]", output)
        self.assertIn("Media bootstrap complete", output)

    def test_bootstrap_media_can_create_missing_members_and_targets(self) -> None:
        MediaAttachment.objects.all().delete()
        MediaAsset.objects.all().delete()
        Review.objects.all().delete()
        Blog.objects.all().delete()
        Trip.objects.all().delete()
        UserModel.objects.filter(username__in=["mei", "arun"]).delete()

        stdout = StringIO()
        call_command(
            "bootstrap_media",
            "--create-missing-members",
            "--create-missing-targets",
            "--verbose",
            stdout=stdout,
        )
        output = stdout.getvalue()

        self.assertTrue(UserModel.objects.filter(username="mei").exists())
        self.assertTrue(UserModel.objects.filter(username="arun").exists())
        self.assertTrue(Trip.objects.filter(pk=101).exists())
        self.assertTrue(Blog.objects.filter(slug="packing-for-swing-weather").exists())
        self.assertGreaterEqual(MediaAttachment.objects.count(), 3)
        self.assertIn("created_members=2", output)
