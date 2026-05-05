import tempfile
from io import BytesIO, StringIO
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from PIL import Image

from blogs.models import Blog
from trips.demo_covers import (
    DEMO_TRIP_COVER_IMAGES,
    REQUIRED_DEMO_COVER_SLOTS,
    demo_blog_cover_url_for_blog,
    demo_trip_cover_for_trip,
    demo_trip_cover_url_for_trip,
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
        self.assertIn("static_banners=3", output)
        self.assertTrue(
            all(
                str(trip.banner_image.name or "") == ""
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

    def test_bootstrap_trips_uses_static_curated_cover_url(self) -> None:
        stdout = StringIO()
        call_command("bootstrap_trips", "--create-missing-hosts", "--verbose", stdout=stdout)
        output = stdout.getvalue()

        kyoto = Trip.objects.get(pk=101)
        self.assertEqual(str(kyoto.banner_image.name or ""), "")
        self.assertIn("static_banners=3", output)
        self.assertEqual(
            kyoto.to_trip_data().get("banner_image_url"),
            demo_trip_cover_url_for_trip(
                title=kyoto.title,
                destination=kyoto.destination,
                trip_type=kyoto.trip_type,
            ),
        )


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
            self.assertTrue(cover.static_path.startswith("img/demo-covers/"))

    def test_trip_without_uploaded_banner_uses_static_curated_cover_url(self) -> None:
        host = UserModel.objects.create_user(
            username="stock-cover-host",
            email="stock-cover-host@example.com",
            password="DemoPass!12345",
        )
        trip = Trip.objects.create(
            host=host,
            title="Goa no-upload getaway",
            summary="A user-created trip with no uploaded cover.",
            destination="Goa, India",
            trip_type="coastal",
            is_published=True,
            status=Trip.STATUS_PUBLISHED,
        )
        trip_data = trip.to_trip_data()

        self.assertEqual(str(trip.banner_image.name or ""), "")
        self.assertEqual(
            trip_data.get("banner_image_url"),
            demo_trip_cover_url_for_trip(
                title=trip.title,
                destination=trip.destination,
                trip_type=trip.trip_type,
            ),
        )

    def test_trip_uploaded_banner_wins_over_curated_stock_cover(self) -> None:
        host = UserModel.objects.create_user(
            username="uploaded-cover-host",
            email="uploaded-cover-host@example.com",
            password="DemoPass!12345",
        )
        trip = Trip.objects.create(
            host=host,
            title="Goa uploaded cover getaway",
            summary="A user-created trip with an uploaded cover.",
            destination="Goa, India",
            trip_type="coastal",
            is_published=True,
            status=Trip.STATUS_PUBLISHED,
        )
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                trip.banner_image.save("uploads/user-cover.jpg", ContentFile(_test_jpeg_bytes(), name="user-cover.jpg"))

                trip_data = trip.to_trip_data()

        self.assertEqual(trip_data.get("banner_image_url"), "/media/trip_banners/uploads/user-cover.jpg")


class PopulateDemoCatalogMediaTests(TestCase):
    def test_trip_media_clears_existing_generated_banner_file(self) -> None:
        host = UserModel.objects.create_user(
            username="demo_trip_media_host",
            email="demo-trip-media-host@example.com",
            password="DemoPass!12345",
        )
        old_banner_name = "trip_banners/demo/generated/old-demo-cover.png"

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                default_storage.save(old_banner_name, ContentFile(b"old generated cover", name="old-demo-cover.png"))
                Trip.objects.create(
                    host=host,
                    title="Generated cover cleanup",
                    summary="Cleanup story.",
                    destination="Goa, India",
                    trip_type="coastal",
                    is_published=True,
                    is_demo=True,
                    status=Trip.STATUS_PUBLISHED,
                    banner_image=old_banner_name,
                )

                PopulateDemoCatalogCommand()._seed_trip_media(verbose=False)

                trip = Trip.objects.get(title="Generated cover cleanup")
                self.assertEqual(str(trip.banner_image.name or ""), "")
                self.assertFalse(default_storage.exists(old_banner_name))

    def test_story_media_uses_static_curated_cover(self) -> None:
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

        PopulateDemoCatalogCommand()._seed_blog_media(verbose=False)

        blog.refresh_from_db()
        self.assertEqual(
            blog.cover_image_url,
            demo_blog_cover_url_for_blog(
                title=blog.title,
                location=blog.location,
                tags=["food", "street-food"],
            ),
        )

    @override_settings(TAPNE_DEMO_CATALOG_VISIBLE=True)
    def test_old_story_cover_endpoint_redirects_to_static_cover(self) -> None:
        author = UserModel.objects.create_user(
            username="demo_story_redirect_host",
            email="demo-story-redirect-host@example.com",
            password="DemoPass!12345",
        )
        blog = Blog.objects.create(
            author=author,
            slug="static-cover-redirect-story",
            title="Static Cover Redirect Story",
            excerpt="Redirect story.",
            body="Redirect story body.",
            location="Asia",
            tags=["food"],
            is_demo=True,
            is_published=True,
        )

        response = self.client.get(f"/frontend-api/blogs/{blog.slug}/cover-image/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            demo_blog_cover_url_for_blog(
                title=blog.title,
                location=blog.location,
                tags=["food"],
            ),
        )


def _test_jpeg_bytes() -> bytes:
    image = Image.new("RGB", (32, 18), (30, 120, 180))
    output = BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()
