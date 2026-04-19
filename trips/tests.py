import os
from io import StringIO
from unittest.mock import PropertyMock, patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
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
