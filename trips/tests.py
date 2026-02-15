from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import PropertyMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from feed.models import MemberFeedPreference
from social.models import Bookmark

from .models import Trip

UserModel = get_user_model()


def _datetime_local(value: datetime) -> str:
    return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")


def _tiny_gif_bytes() -> bytes:
    return (
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
        b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00"
        b"\x02\x02D\x01\x00;"
    )


def _media_file_path(media_root: str, relative_name: str) -> str:
    return os.path.join(media_root, relative_name.replace("/", os.sep))


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

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_guest_trip_list_is_live_only_when_demo_catalog_disabled(self) -> None:
        response = self.client.get(reverse("trips:list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["trip_source"], "live-db")
        self.assertEqual(response.context["trip_mode"], "guest-trending-live")
        self.assertEqual(response.context["trips"], [])

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
                "trip_type": "city",
                "budget_tier": "budget",
                "difficulty_level": "easy",
                "pace_level": "relaxed",
                "group_size_label": "4-6 travelers",
                "includes_label": "Host planning support and local coordination.",
                "starts_at": _datetime_local(starts_at),
                "ends_at": _datetime_local(ends_at),
                "traffic_score": "999999",
                "is_published": "on",
            },
        )

        created_trip = Trip.objects.get(title="Created trip")
        self.assertRedirects(response, reverse("trips:detail", kwargs={"trip_id": created_trip.pk}))
        self.assertEqual(created_trip.host, self.member_user)
        self.assertEqual(created_trip.trip_type, "city")
        self.assertEqual(created_trip.budget_tier, "budget")
        self.assertEqual(created_trip.difficulty_level, "easy")
        self.assertEqual(created_trip.pace_level, "relaxed")
        self.assertEqual(created_trip.group_size_label, "4-6 travelers")
        self.assertEqual(created_trip.traffic_score, 0)

    def test_trip_create_invalid_date_order_returns_form_error(self) -> None:
        self.client.login(username=self.member_user.username, password=self.password)
        starts_at = timezone.now() + timedelta(days=10)
        ends_at = starts_at - timedelta(days=1)

        response = self.client.post(
            reverse("trips:create"),
            {
                "title": "Date invalid trip",
                "summary": "Created summary",
                "description": "Created detail",
                "destination": "Athens",
                "trip_type": "city",
                "budget_tier": "budget",
                "difficulty_level": "easy",
                "pace_level": "relaxed",
                "group_size_label": "4-6 travelers",
                "includes_label": "Host planning support and local coordination.",
                "starts_at": _datetime_local(starts_at),
                "ends_at": _datetime_local(ends_at),
                "is_published": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "End time must be after the start time.")
        self.assertFalse(Trip.objects.filter(title="Date invalid trip").exists())

    def test_trip_create_rejects_description_above_limit(self) -> None:
        self.client.login(username=self.member_user.username, password=self.password)
        starts_at = timezone.now() + timedelta(days=10)
        ends_at = starts_at + timedelta(days=2)

        response = self.client.post(
            reverse("trips:create"),
            {
                "title": "Description too long",
                "summary": "Created summary",
                "description": "x" * 4001,
                "destination": "Athens",
                "trip_type": "city",
                "budget_tier": "budget",
                "difficulty_level": "easy",
                "pace_level": "relaxed",
                "group_size_label": "4-6 travelers",
                "includes_label": "Host planning support and local coordination.",
                "starts_at": _datetime_local(starts_at),
                "ends_at": _datetime_local(ends_at),
                "is_published": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Description must be 4000 characters or fewer.")
        self.assertFalse(Trip.objects.filter(title="Description too long").exists())

    def test_trip_create_get_includes_timezone_context_label(self) -> None:
        self.client.login(username=self.member_user.username, password=self.password)
        response = self.client.get(reverse("trips:create"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("form_timezone_label", response.context)
        self.assertTrue(str(response.context["form_timezone_label"]))
        self.assertContains(response, "Date/time fields use")

    def test_trip_create_without_upload_uses_default_banner_for_trip_type(self) -> None:
        self.client.login(username=self.member_user.username, password=self.password)
        starts_at = timezone.now() + timedelta(days=10)
        ends_at = starts_at + timedelta(days=2)

        response = self.client.post(
            reverse("trips:create"),
            {
                "title": "Default banner trip",
                "summary": "Created summary",
                "description": "Created detail",
                "destination": "Athens",
                "trip_type": "desert",
                "budget_tier": "budget",
                "difficulty_level": "easy",
                "pace_level": "relaxed",
                "group_size_label": "4-6 travelers",
                "includes_label": "Host planning support and local coordination.",
                "starts_at": _datetime_local(starts_at),
                "ends_at": _datetime_local(ends_at),
                "is_published": "on",
            },
        )

        created_trip = Trip.objects.get(title="Default banner trip")
        self.assertRedirects(response, reverse("trips:detail", kwargs={"trip_id": created_trip.pk}))
        self.assertFalse(bool(created_trip.banner_image))

        detail_response = self.client.get(reverse("trips:detail", kwargs={"trip_id": created_trip.pk}))
        self.assertEqual(detail_response.status_code, 200)
        banner_url = str(detail_response.context["trip"].get("banner_image_url", "") or "")
        self.assertIn("/static/img/trip-banners/desert.svg", banner_url)

    def test_trip_create_uploaded_banner_overrides_default_banner(self) -> None:
        self.client.login(username=self.member_user.username, password=self.password)
        starts_at = timezone.now() + timedelta(days=10)
        ends_at = starts_at + timedelta(days=2)

        with tempfile.TemporaryDirectory() as temp_media_root, override_settings(MEDIA_ROOT=temp_media_root):
            response = self.client.post(
                reverse("trips:create"),
                {
                    "title": "Uploaded banner trip",
                    "summary": "Created summary",
                    "description": "Created detail",
                    "destination": "Athens",
                    "trip_type": "desert",
                    "budget_tier": "budget",
                    "difficulty_level": "easy",
                    "pace_level": "relaxed",
                    "group_size_label": "4-6 travelers",
                    "includes_label": "Host planning support and local coordination.",
                    "starts_at": _datetime_local(starts_at),
                    "ends_at": _datetime_local(ends_at),
                    "is_published": "on",
                    "banner_image": SimpleUploadedFile(
                        "cute-banner.gif",
                        _tiny_gif_bytes(),
                        content_type="image/gif",
                    ),
                },
            )

            created_trip = Trip.objects.get(title="Uploaded banner trip")
            self.assertRedirects(response, reverse("trips:detail", kwargs={"trip_id": created_trip.pk}))
            self.assertTrue(str(created_trip.banner_image.name))

            detail_response = self.client.get(reverse("trips:detail", kwargs={"trip_id": created_trip.pk}))
            self.assertEqual(detail_response.status_code, 200)
            banner_url = str(detail_response.context["trip"].get("banner_image_url", "") or "")
            self.assertIn(created_trip.banner_image.name, banner_url)
            self.assertNotIn("/static/img/trip-banners/desert.svg", banner_url)

    def test_trip_edit_get_does_not_error_when_banner_url_resolution_fails(self) -> None:
        trip = Trip.objects.create(
            host=self.host_user,
            title="Banner URL resilient trip",
            summary="s",
            description="d",
            destination="Prague",
            starts_at=timezone.now() + timedelta(days=4),
            trip_type="city",
            budget_tier="mid",
            difficulty_level="moderate",
            pace_level="balanced",
            group_size_label="6-10 travelers",
            includes_label="Host planning support.",
            is_published=True,
        )
        Trip.objects.filter(pk=trip.pk).update(banner_image="trip_banners/fake.webp")
        trip.refresh_from_db(fields=["banner_image"])

        self.client.login(username=self.host_user.username, password=self.password)
        with patch(
            "django.db.models.fields.files.FieldFile.url",
            new_callable=PropertyMock,
            side_effect=RuntimeError("url lookup failed"),
        ):
            response = self.client.get(reverse("trips:edit", kwargs={"trip_id": trip.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Save changes")
        self.assertContains(response, "Current banner file: trip_banners/fake.webp")
        self.assertContains(response, reverse("trips:banner", kwargs={"trip_id": trip.pk}))

    def test_trip_detail_falls_back_to_banner_proxy_when_banner_url_resolution_fails(self) -> None:
        trip = Trip.objects.create(
            host=self.host_user,
            title="Banner fallback trip",
            summary="s",
            description="d",
            destination="Prague",
            starts_at=timezone.now() + timedelta(days=4),
            trip_type="city",
            budget_tier="mid",
            difficulty_level="moderate",
            pace_level="balanced",
            group_size_label="6-10 travelers",
            includes_label="Host planning support.",
            is_published=True,
        )
        Trip.objects.filter(pk=trip.pk).update(banner_image="trip_banners/fake.webp")
        trip.refresh_from_db(fields=["banner_image"])

        with patch(
            "django.db.models.fields.files.FieldFile.url",
            new_callable=PropertyMock,
            side_effect=RuntimeError("url lookup failed"),
        ):
            response = self.client.get(reverse("trips:detail", kwargs={"trip_id": trip.pk}))

        self.assertEqual(response.status_code, 200)
        banner_url = str(response.context["trip"].get("banner_image_url", "") or "")
        self.assertTrue(banner_url.startswith(reverse("trips:banner", kwargs={"trip_id": trip.pk})))
        self.assertIn("?v=", banner_url)

    def test_trip_banner_proxy_streams_uploaded_banner_when_direct_url_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_media_root, override_settings(MEDIA_ROOT=temp_media_root):
            trip = Trip.objects.create(
                host=self.host_user,
                title="Banner proxy trip",
                summary="s",
                description="d",
                destination="Prague",
                starts_at=timezone.now() + timedelta(days=4),
                trip_type="city",
                budget_tier="mid",
                difficulty_level="moderate",
                pace_level="balanced",
                group_size_label="6-10 travelers",
                includes_label="Host planning support.",
                is_published=True,
                banner_image=SimpleUploadedFile(
                    "cute-banner.gif",
                    _tiny_gif_bytes(),
                    content_type="image/gif",
                ),
            )

            with patch(
                "django.db.models.fields.files.FieldFile.url",
                new_callable=PropertyMock,
                side_effect=RuntimeError("url lookup failed"),
            ):
                detail_response = self.client.get(reverse("trips:detail", kwargs={"trip_id": trip.pk}))

            self.assertEqual(detail_response.status_code, 200)
            banner_url = str(detail_response.context["trip"].get("banner_image_url", "") or "")
            self.assertTrue(banner_url.startswith(reverse("trips:banner", kwargs={"trip_id": trip.pk})))
            self.assertIn("?v=", banner_url)

            banner_response = self.client.get(reverse("trips:banner", kwargs={"trip_id": trip.pk}))
            self.assertEqual(banner_response.status_code, 200)
            self.assertEqual(banner_response["Content-Type"], "image/gif")
            banner_response.close()

    def test_trip_banner_proxy_hides_unpublished_trip_from_non_host(self) -> None:
        with tempfile.TemporaryDirectory() as temp_media_root, override_settings(MEDIA_ROOT=temp_media_root):
            trip = Trip.objects.create(
                host=self.host_user,
                title="Private banner trip",
                summary="s",
                description="d",
                destination="Prague",
                starts_at=timezone.now() + timedelta(days=4),
                trip_type="city",
                budget_tier="mid",
                difficulty_level="moderate",
                pace_level="balanced",
                group_size_label="6-10 travelers",
                includes_label="Host planning support.",
                is_published=False,
                banner_image=SimpleUploadedFile(
                    "private-banner.gif",
                    _tiny_gif_bytes(),
                    content_type="image/gif",
                ),
            )

            guest_response = self.client.get(reverse("trips:banner", kwargs={"trip_id": trip.pk}))
            self.assertEqual(guest_response.status_code, 404)

            self.client.login(username=self.host_user.username, password=self.password)
            host_response = self.client.get(reverse("trips:banner", kwargs={"trip_id": trip.pk}))
            self.assertEqual(host_response.status_code, 200)
            host_response.close()

    def test_trip_detail_banner_url_cache_key_changes_after_banner_update(self) -> None:
        with tempfile.TemporaryDirectory() as temp_media_root, override_settings(MEDIA_ROOT=temp_media_root):
            trip = Trip.objects.create(
                host=self.host_user,
                title="Banner cache key trip",
                summary="s",
                description="d",
                destination="Prague",
                starts_at=timezone.now() + timedelta(days=4),
                trip_type="city",
                budget_tier="mid",
                difficulty_level="moderate",
                pace_level="balanced",
                group_size_label="6-10 travelers",
                includes_label="Host planning support.",
                is_published=True,
                banner_image=SimpleUploadedFile(
                    "first-banner.gif",
                    _tiny_gif_bytes(),
                    content_type="image/gif",
                ),
            )

            with patch(
                "django.db.models.fields.files.FieldFile.url",
                new_callable=PropertyMock,
                side_effect=RuntimeError("url lookup failed"),
            ):
                first_response = self.client.get(reverse("trips:detail", kwargs={"trip_id": trip.pk}))
            first_banner_url = str(first_response.context["trip"].get("banner_image_url", "") or "")

            trip.banner_image.save(
                "second-banner.gif",
                ContentFile(_tiny_gif_bytes()),
                save=True,
            )

            with patch(
                "django.db.models.fields.files.FieldFile.url",
                new_callable=PropertyMock,
                side_effect=RuntimeError("url lookup failed"),
            ):
                second_response = self.client.get(reverse("trips:detail", kwargs={"trip_id": trip.pk}))
            second_banner_url = str(second_response.context["trip"].get("banner_image_url", "") or "")

            self.assertTrue(first_banner_url.startswith(reverse("trips:banner", kwargs={"trip_id": trip.pk})))
            self.assertTrue(second_banner_url.startswith(reverse("trips:banner", kwargs={"trip_id": trip.pk})))
            self.assertNotEqual(first_banner_url, second_banner_url)

    def test_banner_replacement_deletes_old_banner_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_media_root, override_settings(MEDIA_ROOT=temp_media_root):
            trip = Trip.objects.create(
                host=self.host_user,
                title="Banner cleanup replace trip",
                summary="s",
                description="d",
                destination="Prague",
                starts_at=timezone.now() + timedelta(days=4),
                trip_type="city",
                budget_tier="mid",
                difficulty_level="moderate",
                pace_level="balanced",
                group_size_label="6-10 travelers",
                includes_label="Host planning support.",
                is_published=True,
                banner_image=SimpleUploadedFile(
                    "old-banner.gif",
                    _tiny_gif_bytes(),
                    content_type="image/gif",
                ),
            )

            old_name = str(trip.banner_image.name)
            old_path = _media_file_path(temp_media_root, old_name)
            self.assertTrue(os.path.exists(old_path))

            trip.banner_image.save(
                "new-banner.gif",
                ContentFile(_tiny_gif_bytes()),
                save=True,
            )
            trip.refresh_from_db(fields=["banner_image"])

            new_name = str(trip.banner_image.name)
            new_path = _media_file_path(temp_media_root, new_name)
            self.assertTrue(os.path.exists(new_path))
            self.assertFalse(os.path.exists(old_path))

    def test_trip_deletion_deletes_current_banner_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_media_root, override_settings(MEDIA_ROOT=temp_media_root):
            trip = Trip.objects.create(
                host=self.host_user,
                title="Banner cleanup delete trip",
                summary="s",
                description="d",
                destination="Prague",
                starts_at=timezone.now() + timedelta(days=4),
                trip_type="city",
                budget_tier="mid",
                difficulty_level="moderate",
                pace_level="balanced",
                group_size_label="6-10 travelers",
                includes_label="Host planning support.",
                is_published=True,
                banner_image=SimpleUploadedFile(
                    "delete-banner.gif",
                    _tiny_gif_bytes(),
                    content_type="image/gif",
                ),
            )

            banner_path = _media_file_path(temp_media_root, str(trip.banner_image.name))
            self.assertTrue(os.path.exists(banner_path))

            trip.delete()

            self.assertFalse(os.path.exists(banner_path))

    def test_banner_replacement_keeps_old_file_when_still_referenced(self) -> None:
        with tempfile.TemporaryDirectory() as temp_media_root, override_settings(MEDIA_ROOT=temp_media_root):
            original_trip = Trip.objects.create(
                host=self.host_user,
                title="Banner cleanup shared source",
                summary="s",
                description="d",
                destination="Prague",
                starts_at=timezone.now() + timedelta(days=4),
                trip_type="city",
                budget_tier="mid",
                difficulty_level="moderate",
                pace_level="balanced",
                group_size_label="6-10 travelers",
                includes_label="Host planning support.",
                is_published=True,
                banner_image=SimpleUploadedFile(
                    "shared-banner.gif",
                    _tiny_gif_bytes(),
                    content_type="image/gif",
                ),
            )
            shared_name = str(original_trip.banner_image.name)
            shared_path = _media_file_path(temp_media_root, shared_name)
            self.assertTrue(os.path.exists(shared_path))

            sibling_trip = Trip.objects.create(
                host=self.member_user,
                title="Banner cleanup shared sibling",
                summary="s",
                description="d",
                destination="Rome",
                starts_at=timezone.now() + timedelta(days=5),
                trip_type="city",
                budget_tier="mid",
                difficulty_level="moderate",
                pace_level="balanced",
                group_size_label="6-10 travelers",
                includes_label="Host planning support.",
                is_published=True,
            )
            Trip.objects.filter(pk=sibling_trip.pk).update(banner_image=shared_name)

            original_trip.banner_image.save(
                "replacement-banner.gif",
                ContentFile(_tiny_gif_bytes()),
                save=True,
            )

            self.assertTrue(os.path.exists(shared_path))

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_trip_create_unpublished_stays_hidden_from_list_and_search(self) -> None:
        self.client.login(username=self.member_user.username, password=self.password)
        starts_at = timezone.now() + timedelta(days=10)
        ends_at = starts_at + timedelta(days=2)

        response = self.client.post(
            reverse("trips:create"),
            {
                "title": "Draft only trip",
                "summary": "Created summary",
                "description": "Created detail",
                "destination": "Athens",
                "trip_type": "city",
                "budget_tier": "budget",
                "difficulty_level": "easy",
                "pace_level": "relaxed",
                "group_size_label": "4-6 travelers",
                "includes_label": "Host planning support and local coordination.",
                "starts_at": _datetime_local(starts_at),
                "ends_at": _datetime_local(ends_at),
            },
        )

        created_trip = Trip.objects.get(title="Draft only trip")
        self.assertRedirects(response, reverse("trips:detail", kwargs={"trip_id": created_trip.pk}))
        self.assertFalse(created_trip.is_published)

        list_response = self.client.get(reverse("trips:list"))
        list_ids = {trip["id"] for trip in list_response.context["trips"]}
        self.assertNotIn(created_trip.pk, list_ids)

        search_response = self.client.get(f"{reverse('search:search')}?q=Draft+only+trip&type=trips")
        search_ids = {trip["id"] for trip in search_response.context["trips"]}
        self.assertNotIn(created_trip.pk, search_ids)

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
