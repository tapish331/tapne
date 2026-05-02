import tempfile
from io import BytesIO, StringIO
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from PIL import Image

from blogs.models import Blog, build_demo_blog_cover_storage_name, build_demo_blog_cover_url
from trips.demo_covers import (
    DEMO_TRIP_COVER_IMAGES,
    REQUIRED_DEMO_COVER_SLOTS,
    demo_trip_cover_for_trip,
    sync_demo_trip_cover_images,
    validate_demo_trip_cover_manifest,
)
from trips.management.commands.populate_demo_catalog import Command as PopulateDemoCatalogCommand
from .models import Trip
from .places_proxy import autocomplete_places, place_details
UserModel = get_user_model()



class TripPlacesProxyTests(TestCase):
    @override_settings(GOOGLE_MAPS_API_KEY="test-google-maps-key")
    def test_autocomplete_places_treats_cache_backend_failure_as_cache_miss(self) -> None:
        with patch(
            "trips.places_proxy.cache.get",
            side_effect=ConnectionError("redis unavailable"),
        ), patch(
            "trips.places_proxy.cache.set",
            side_effect=ConnectionError("redis unavailable"),
        ), patch(
            "trips.places_proxy._request_json",
            return_value={
                "suggestions": [
                    {
                        "placePrediction": {
                            "placeId": "abc123",
                            "structuredFormat": {
                                "mainText": {"text": "Shillong"},
                                "secondaryText": {"text": "India"},
                            },
                        }
                    }
                ]
            },
        ) as mock_request:
            predictions = autocomplete_places("Shill", session_token="session-1")

        self.assertEqual(len(predictions), 1)
        self.assertEqual(predictions[0]["place_id"], "abc123")
        self.assertEqual(predictions[0]["label"], "Shillong, India")
        mock_request.assert_called_once()

    @override_settings(GOOGLE_MAPS_API_KEY="test-google-maps-key")
    def test_place_details_treats_cache_backend_failure_as_cache_miss(self) -> None:
        with patch(
            "trips.places_proxy.cache.get",
            side_effect=ConnectionError("redis unavailable"),
        ), patch(
            "trips.places_proxy.cache.set",
            side_effect=ConnectionError("redis unavailable"),
        ), patch(
            "trips.places_proxy._request_json",
            return_value={
                "formattedAddress": "Shillong, Meghalaya, India",
                "location": {
                    "latitude": 25.5788,
                    "longitude": 91.8933,
                },
                "addressComponents": [
                    {"longText": "Shillong", "types": ["locality"]},
                    {"longText": "India", "types": ["country"]},
                ],
                "viewport": {
                    "low": {"latitude": 25.4, "longitude": 91.7},
                    "high": {"latitude": 25.7, "longitude": 92.0},
                },
            },
        ) as mock_request:
            details = place_details("abc123", session_token="session-1")

        self.assertEqual(details["place_id"], "abc123")
        self.assertEqual(details["label"], "Shillong, India")
        self.assertEqual(details["latitude"], 25.5788)
        self.assertEqual(details["longitude"], 91.8933)
        mock_request.assert_called_once()



class TripsBootstrapCommandTests(TestCase):
    def test_bootstrap_trips_seeds_rows_with_verbose_output(self) -> None:
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                stdout = StringIO()
                call_command("bootstrap_trips", "--create-missing-hosts", "--verbose", stdout=stdout)
                output = stdout.getvalue()

        self.assertEqual(Trip.objects.count(), 3)
        self.assertIn("[trips][verbose]", output)
        self.assertIn("Trips bootstrap complete", output)
        self.assertIn("generated_banners=3", output)
        self.assertTrue(
            all(
                str(trip.banner_image.name).startswith("trip_banners/demo/generated/")
                for trip in Trip.objects.all()
            )
        )
        self.assertTrue(
            all(
                trip.to_trip_data().get("banner_image_url")
                and trip.to_trip_data().get("banner_image_url") != "/placeholder.svg"
                for trip in Trip.objects.all()
            )
        )

    def test_bootstrap_trips_skips_when_hosts_are_missing(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_trips", stdout=stdout)
        output = stdout.getvalue()

        self.assertEqual(Trip.objects.count(), 0)
        self.assertIn("skipped=3", output)

    def test_bootstrap_trips_uses_synced_curated_cover_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                cover = demo_trip_cover_for_trip(
                    title="Kyoto food lanes weekend",
                    destination="Kyoto, Japan",
                    trip_type="food-culture",
                )
                default_storage.save(cover.storage_path, ContentFile(b"curated image", name="food.jpg"))

                stdout = StringIO()
                call_command("bootstrap_trips", "--create-missing-hosts", "--verbose", stdout=stdout)
                output = stdout.getvalue()

        kyoto = Trip.objects.get(pk=101)
        self.assertEqual(kyoto.banner_image.name, cover.storage_path)
        self.assertIn("curated_banners=1", output)
        self.assertNotEqual(kyoto.to_trip_data().get("banner_image_url"), "/placeholder.svg")


class DemoTripCoverTests(TestCase):
    def test_manifest_contains_required_curated_slots(self) -> None:
        validate_demo_trip_cover_manifest()

        self.assertEqual(len(DEMO_TRIP_COVER_IMAGES), 10)
        self.assertEqual(
            {entry.slot for entry in DEMO_TRIP_COVER_IMAGES},
            set(REQUIRED_DEMO_COVER_SLOTS),
        )
        for trip_type in REQUIRED_DEMO_COVER_SLOTS:
            cover = demo_trip_cover_for_trip(title="", destination="", trip_type=trip_type)
            self.assertIn(trip_type, cover.preferred_trip_types)

    def test_sync_demo_trip_covers_is_idempotent(self) -> None:
        image_bytes = _test_jpeg_bytes()

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                with patch("trips.demo_covers.download_demo_trip_cover_image", return_value=image_bytes) as mock_download:
                    first_results = sync_demo_trip_cover_images()
                    second_results = sync_demo_trip_cover_images()

        self.assertEqual([result.status for result in first_results], ["synced"] * 10)
        self.assertEqual([result.status for result in second_results], ["skipped"] * 10)
        self.assertEqual(mock_download.call_count, 10)


class PopulateDemoCatalogMediaTests(TestCase):
    def test_story_media_uses_synced_curated_cover_when_available(self) -> None:
        author = UserModel.objects.create_user(
            username="demo_story_host",
            email="demo-story-host@example.com",
            password="DemoPass!12345",
        )
        blog = Blog.objects.create(
            author=author,
            slug="asia-best-street-food-cities-ranked",
            title="Asia's Best Street Food Cities, Ranked",
            excerpt="Street food guide.",
            body="Street food body.",
            location="Asia",
            tags=["food", "street-food"],
            is_demo=True,
            is_published=True,
        )
        cover = demo_trip_cover_for_trip(
            title=blog.title,
            destination="Asia food street-food",
            trip_type="food-culture",
        )

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                default_storage.save(cover.storage_path, ContentFile(_test_jpeg_bytes(), name="food.jpg"))
                with patch(
                    "trips.management.commands.populate_demo_catalog._render_demo_cover",
                    side_effect=AssertionError("generated fallback should not be used"),
                ):
                    PopulateDemoCatalogCommand()._seed_blog_media(verbose=False)

                file_name = build_demo_blog_cover_storage_name(slug=blog.slug, blog_id=int(blog.pk))
                self.assertTrue(default_storage.exists(file_name))
                with default_storage.open(file_name, "rb") as saved_cover:
                    self.assertEqual(saved_cover.read(2), b"\xff\xd8")

        blog.refresh_from_db()
        self.assertEqual(blog.cover_image_url, build_demo_blog_cover_url(slug=blog.slug))

    def test_story_media_generates_cover_when_curated_cover_is_missing(self) -> None:
        author = UserModel.objects.create_user(
            username="demo_story_fallback_host",
            email="demo-story-fallback-host@example.com",
            password="DemoPass!12345",
        )
        blog = Blog.objects.create(
            author=author,
            slug="missing-curated-story",
            title="Missing Curated Story",
            excerpt="Fallback story.",
            body="Fallback story body.",
            location="Unknown",
            tags=["unknown"],
            is_demo=True,
            is_published=True,
        )

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                PopulateDemoCatalogCommand()._seed_blog_media(verbose=False)

                file_name = build_demo_blog_cover_storage_name(slug=blog.slug, blog_id=int(blog.pk))
                self.assertTrue(default_storage.exists(file_name))
                with default_storage.open(file_name, "rb") as saved_cover:
                    self.assertEqual(saved_cover.read(2), b"\xff\xd8")

        blog.refresh_from_db()
        self.assertEqual(blog.cover_image_url, build_demo_blog_cover_url(slug=blog.slug))


def _test_jpeg_bytes() -> bytes:
    image = Image.new("RGB", (32, 18), (30, 120, 180))
    output = BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()
