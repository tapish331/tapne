from __future__ import annotations

import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from django.contrib.auth import get_user_model
from django.http import StreamingHttpResponse
from django.test import RequestFactory
from django.test import Client, TestCase, override_settings
from django.urls import clear_url_caches, set_urlconf
from django.utils import timezone

import frontend.urls as frontend_urls
import tapne.urls as tapne_urls
from blogs.models import Blog
from accounts.models import ensure_profile
from enrollment.models import EnrollmentRequest
from frontend.views import frontend_entrypoint_view
from interactions.models import DirectMessage, DirectMessageThread
from reviews.models import Review
from social.models import FollowRelation
from trips.models import Trip

UserModel = get_user_model()


def _set_profile_fields(profile: object, **values: object) -> None:
    for field_name, value in values.items():
        setattr(profile, field_name, value)


class FrontendApiTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.user = UserModel.objects.create_user(
            username="frontend-user",
            email="frontend@example.com",
            password="S3curePassw0rd!!",
        )
        Trip.objects.create(
            host=self.user,
            title="Kerala by Houseboat",
            summary="A real live trip row.",
            destination="Kerala",
            starts_at=timezone.now() + timezone.timedelta(days=10),
            is_published=True,
        )
        Blog.objects.create(
            author=self.user,
            slug="real-blog",
            title="Real blog post",
            excerpt="A real persisted blog row.",
            body="Real body content.",
            is_published=True,
        )

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_session_endpoint_includes_runtime_config(self) -> None:
        response = self.client.get("/frontend-api/session/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["authenticated"])
        self.assertIn("runtime", payload)
        self.assertEqual(payload["runtime"]["api"]["base"], "/frontend-api")
        self.assertEqual(payload["runtime"]["api"]["search"], "/frontend-api/search/")

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_json_login_endpoint_authenticates_member(self) -> None:
        response = self.client.post(
            "/frontend-api/auth/login/",
            data='{"username":"frontend-user","password":"S3curePassw0rd!!"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["authenticated"])
        self.assertEqual(payload["user"]["username"], "frontend-user")

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_trip_and_blog_endpoints_return_live_payloads(self) -> None:
        trip_response = self.client.get("/frontend-api/trips/")
        blog_response = self.client.get("/frontend-api/blogs/")

        self.assertEqual(trip_response.status_code, 200)
        self.assertEqual(blog_response.status_code, 200)
        self.assertEqual(trip_response.json()["source"], "live-db")
        self.assertEqual(blog_response.json()["source"], "live-db")

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_profile_patch_endpoint_updates_live_profile(self) -> None:
        self.client.login(username="frontend-user", password="S3curePassw0rd!!")
        response = self.client.patch(
            "/frontend-api/profile/me/",
            data='{"display_name":"Frontend Explorer","bio":"Real bio","location":"Bengaluru","website":"https://example.com"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["profile"]["display_name"], "Frontend Explorer")
        self.assertEqual(payload["profile"]["location"], "Bengaluru")

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_trip_draft_crud_and_publish_endpoints_use_live_storage(self) -> None:
        self.client.login(username="frontend-user", password="S3curePassw0rd!!")
        application_questions = [
            {
                "id": "fitness",
                "question": "What is your trekking experience?",
                "type": "long",
                "required": True,
            },
            {
                "id": "meal",
                "question": "Preferred meal?",
                "type": "single_select",
                "required": False,
                "options": ["Veg", "Non-veg"],
            },
        ]

        create_response = self.client.post(
            "/frontend-api/trips/drafts/",
            data=json.dumps(
                {
                    "title": "Live Draft",
                    "destination": "Goa",
                    "summary": "Draft summary",
                    "highlights": ["Beach walk", "Cafe stops"],
                    "trip_vibe": ["Social"],
                    "starts_at": "2030-01-10T10:00:00+05:30",
                    "ends_at": "2030-01-12T10:00:00+05:30",
                    "total_seats": "8",
                    "total_trip_price": "24000",
                    "access_type": "apply",
                    "application_questions": application_questions,
                    "auto_approve": True,
                    "payment_method": "show_payment_details",
                    "payment_details": "UPI: host@upi",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        created_trip = create_response.json()["trip"]
        created_trip_id = created_trip["id"]
        self.assertEqual(created_trip["access_type"], "apply")
        self.assertEqual(created_trip["application_questions"], application_questions)
        self.assertTrue(created_trip["auto_approve"])
        self.assertEqual(created_trip["payment_method"], "show_payment_details")
        self.assertEqual(created_trip["payment_details"], "UPI: host@upi")

        patch_response = self.client.patch(
            f"/frontend-api/trips/drafts/{created_trip_id}/",
            data='{"summary":"Updated live summary","included_items":["Stay","Coordination"]}',
            content_type="application/json",
        )
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.json()["trip"]["summary"], "Updated live summary")

        publish_response = self.client.post(
            f"/frontend-api/trips/drafts/{created_trip_id}/publish/",
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 200)
        self.assertTrue(publish_response.json()["ok"])

        published_trip = Trip.objects.get(pk=created_trip_id)
        self.assertTrue(published_trip.is_published)
        self.assertEqual(published_trip.draft_form_data["application_questions"], application_questions)
        self.assertTrue(published_trip.draft_form_data["auto_approve"])

        detail_response = self.client.get(f"/frontend-api/trips/{created_trip_id}/")
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = detail_response.json()
        self.assertEqual(detail_payload["source"], "live-db")
        self.assertEqual(detail_payload["trip"]["access_type"], "apply")
        self.assertEqual(detail_payload["trip"]["application_questions"], application_questions)
        self.assertTrue(detail_payload["trip"]["auto_approve"])
        self.assertEqual(detail_payload["trip"]["payment_method"], "show_payment_details")
        self.assertEqual(detail_payload["trip"]["payment_details"], "UPI: host@upi")
        self.assertEqual(detail_payload["host"]["username"], "frontend-user")
        self.assertGreaterEqual(len(detail_payload["participants"]), 1)

        traveler = UserModel.objects.create_user(
            username="frontend-traveler",
            email="traveler@example.com",
            password="S3curePassw0rd!!",
        )
        self.client.logout()
        self.client.login(username="frontend-traveler", password="S3curePassw0rd!!")
        long_message = "Application details " + ("x" * 700)
        join_response = self.client.post(
            f"/frontend-api/trips/{created_trip_id}/join-request/",
            data=json.dumps({"message": long_message}),
            content_type="application/json",
        )
        self.assertEqual(join_response.status_code, 200)
        self.assertEqual(join_response.json()["outcome"], "auto-approved")
        request_row = EnrollmentRequest.objects.get(trip_id=created_trip_id, requester=traveler)
        self.assertEqual(request_row.status, EnrollmentRequest.STATUS_APPROVED)
        self.assertEqual(request_row.message, long_message)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_late_draft_patch_does_not_demote_published_trip(self) -> None:
        self.client.login(username="frontend-user", password="S3curePassw0rd!!")

        create_response = self.client.post(
            "/frontend-api/trips/drafts/",
            data=(
                '{"title":"Race Draft","destination":"Goa","summary":"Draft summary",'
                '"starts_at":"2030-01-10T10:00:00+05:30","ends_at":"2030-01-12T10:00:00+05:30",'
                '"total_seats":"8","total_trip_price":"24000"}'
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        trip_id = create_response.json()["trip"]["id"]

        publish_response = self.client.post(
            f"/frontend-api/trips/drafts/{trip_id}/publish/",
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 200)

        late_patch_response = self.client.patch(
            f"/frontend-api/trips/drafts/{trip_id}/",
            data='{"summary":"Late autosave after publish"}',
            content_type="application/json",
        )
        self.assertEqual(late_patch_response.status_code, 200)

        trip = Trip.objects.get(pk=trip_id)
        self.assertEqual(trip.status, Trip.STATUS_PUBLISHED)
        self.assertTrue(trip.is_published)
        self.assertEqual(trip.summary, "Late autosave after publish")


class FrontendSessionBEndpointsTests(TestCase):
    """Coverage for the SPA-cutover endpoints added in Session B:
    - /frontend-api/profile/me/followers/ and /following/
    - /frontend-api/reviews/ (?author=me | ?recipient=me)
    - /frontend-api/trips/ (?q, ?sort)
    - /frontend-api/blogs/ (?q, ?author=me)"""

    def setUp(self) -> None:
        self.password = "SessionBPass!123456"
        self.alice = UserModel.objects.create_user(
            username="alice",
            email="alice@example.com",
            password=self.password,
        )
        self.bob = UserModel.objects.create_user(
            username="bob",
            email="bob@example.com",
            password=self.password,
        )
        self.carol = UserModel.objects.create_user(
            username="carol",
            email="carol@example.com",
            password=self.password,
        )

    # -- Followers / following ----------------------------------------------

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_followers_endpoint_lists_current_users_followers(self) -> None:
        FollowRelation.objects.create(follower=self.bob, following=self.alice)
        FollowRelation.objects.create(follower=self.carol, following=self.alice)

        self.client.login(username="alice", password=self.password)
        response = self.client.get("/frontend-api/profile/me/followers/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        usernames = {row["username"] for row in payload["users"]}
        self.assertEqual(usernames, {"bob", "carol"})

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_following_endpoint_lists_users_current_user_follows(self) -> None:
        FollowRelation.objects.create(follower=self.alice, following=self.bob)
        FollowRelation.objects.create(follower=self.alice, following=self.carol)

        self.client.login(username="alice", password=self.password)
        response = self.client.get("/frontend-api/profile/me/following/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        usernames = {row["username"] for row in payload["users"]}
        self.assertEqual(usernames, {"bob", "carol"})

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_followers_endpoint_requires_authentication(self) -> None:
        response = self.client.get("/frontend-api/profile/me/followers/")
        self.assertEqual(response.status_code, 401)

    # -- Reviews -------------------------------------------------------------

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_reviews_endpoint_author_filter_returns_authored_reviews(self) -> None:
        alice_trip = Trip.objects.create(
            host=self.alice,
            title="Alice's Trip",
            summary="Summary",
            destination="Goa",
            starts_at=timezone.now() + timezone.timedelta(days=30),
            is_published=True,
        )
        Review.objects.create(
            author=self.bob,
            target_type=Review.TARGET_TRIP,
            target_key=str(alice_trip.pk),
            target_label="Alice's Trip",
            rating=5,
            body="Loved it.",
        )

        self.client.login(username="bob", password=self.password)
        response = self.client.get("/frontend-api/reviews/?author=me")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["reviews"]), 1)
        row = payload["reviews"][0]
        self.assertEqual(row["rating"], 5)
        self.assertEqual(row["trip_title"], "Alice's Trip")
        self.assertEqual(row["text"], "Loved it.")
        self.assertTrue(row["is_mine"])

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_reviews_endpoint_recipient_filter_returns_received_reviews(self) -> None:
        alice_trip = Trip.objects.create(
            host=self.alice,
            title="Alice's Trip",
            summary="Summary",
            destination="Goa",
            starts_at=timezone.now() + timezone.timedelta(days=30),
            is_published=True,
        )
        Review.objects.create(
            author=self.bob,
            target_type=Review.TARGET_TRIP,
            target_key=str(alice_trip.pk),
            target_label="Alice's Trip",
            rating=4,
            body="Great host.",
        )

        self.client.login(username="alice", password=self.password)
        response = self.client.get("/frontend-api/reviews/?recipient=me")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["reviews"]), 1)
        row = payload["reviews"][0]
        self.assertEqual(row["rating"], 4)
        self.assertFalse(row["is_mine"])

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_reviews_endpoint_requires_explicit_filter(self) -> None:
        self.client.login(username="alice", password=self.password)
        response = self.client.get("/frontend-api/reviews/")
        self.assertEqual(response.status_code, 400)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_reviews_endpoint_requires_authentication(self) -> None:
        response = self.client.get("/frontend-api/reviews/?author=me")
        self.assertEqual(response.status_code, 401)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_dm_inbox_endpoint_returns_most_recent_messages_for_long_threads(self) -> None:
        thread = DirectMessageThread.objects.create(member_one=self.alice, member_two=self.bob)
        for index in range(54):
            sender = self.alice if index % 2 == 0 else self.bob
            DirectMessage.objects.create(
                thread=thread,
                sender=sender,
                body=f"msg {index:02d}",
            )

        self.client.login(username="alice", password=self.password)
        response = self.client.get("/frontend-api/dm/inbox/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["threads"]), 1)

        thread_row = payload["threads"][0]
        bodies = [row["body"] for row in thread_row["messages"]]
        self.assertEqual(len(bodies), 50)
        self.assertEqual(bodies[0], "msg 04")
        self.assertEqual(bodies[-1], "msg 53")
        self.assertEqual(thread_row["last_message"], "msg 53")
        self.assertNotIn("msg 00", bodies)

    # -- Trip list ?q / ?sort ------------------------------------------------

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_trip_list_q_filter_matches_title_and_destination(self) -> None:
        now = timezone.now()
        Trip.objects.create(
            host=self.alice,
            title="Kerala Houseboat",
            summary="Quiet backwaters",
            destination="Kerala",
            starts_at=now + timezone.timedelta(days=5),
            is_published=True,
        )
        Trip.objects.create(
            host=self.alice,
            title="Goa Beach Weekend",
            summary="Sun and sand",
            destination="Goa",
            starts_at=now + timezone.timedelta(days=10),
            is_published=True,
        )

        response = self.client.get("/frontend-api/trips/?q=kerala")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        titles = {trip["title"] for trip in payload["trips"]}
        self.assertIn("Kerala Houseboat", titles)
        self.assertNotIn("Goa Beach Weekend", titles)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_trip_list_review_filters_delegate_to_reviews_payload(self) -> None:
        alice_trip = Trip.objects.create(
            host=self.alice,
            title="Alice's Trip",
            summary="Summary",
            destination="Goa",
            starts_at=timezone.now() + timezone.timedelta(days=30),
            is_published=True,
        )
        Review.objects.create(
            author=self.bob,
            target_type=Review.TARGET_TRIP,
            target_key=str(alice_trip.pk),
            target_label="Alice's Trip",
            rating=5,
            body="Loved it.",
        )

        self.client.login(username="bob", password=self.password)
        response = self.client.get("/frontend-api/trips/?author=me")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["reviews"]), 1)
        self.assertEqual(payload["reviews"][0]["trip_title"], "Alice's Trip")

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_profile_endpoints_include_authors_published_stories(self) -> None:
        Blog.objects.create(
            author=self.alice,
            slug="alice-published-trek",
            title="Trekking the Himalayas",
            excerpt="What I learnt above 4,000 m.",
            body="Long form body.",
            is_published=True,
        )
        Blog.objects.create(
            author=self.alice,
            slug="alice-draft-coastline",
            title="Draft notes on the coastline",
            excerpt="Still writing.",
            body="Draft body.",
            is_published=False,
        )

        # Public profile endpoint — viewable by anyone, returns only published.
        public_response = self.client.get(f"/frontend-api/profile/{self.alice.username}/")
        self.assertEqual(public_response.status_code, 200)
        public_titles = {story["title"] for story in public_response.json()["stories"]}
        self.assertIn("Trekking the Himalayas", public_titles)
        self.assertNotIn("Draft notes on the coastline", public_titles)

        # Own profile endpoint also surfaces published stories.
        self.client.login(username="alice", password=self.password)
        me_response = self.client.get("/frontend-api/profile/me/")
        self.assertEqual(me_response.status_code, 200)
        me_titles = {story["title"] for story in me_response.json()["stories"]}
        self.assertIn("Trekking the Himalayas", me_titles)
        self.assertNotIn("Draft notes on the coastline", me_titles)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_profile_me_persists_travel_tags_and_avatar_url(self) -> None:
        self.client.login(username="alice", password=self.password)

        patch_response = self.client.patch(
            "/frontend-api/profile/me/",
            data={
                "display_name": "Alice A.",
                "bio": "Curious wanderer",
                "location": "Mumbai",
                "website": "",
                "avatar_url": "data:image/png;base64,iVBORw0KGgoAAAA",
                "travel_tags": ["Backpacking", "Food", "Solo"],
            },
            content_type="application/json",
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.content)
        member = patch_response.json()["member_profile"]
        self.assertEqual(member["avatar_url"], "data:image/png;base64,iVBORw0KGgoAAAA")
        self.assertEqual(member["travel_tags"], ["Backpacking", "Food", "Solo"])

        get_response = self.client.get("/frontend-api/profile/me/")
        self.assertEqual(get_response.status_code, 200)
        profile = get_response.json()["profile"]
        self.assertEqual(profile["avatar_url"], "data:image/png;base64,iVBORw0KGgoAAAA")
        self.assertEqual(profile["travel_tags"], ["Backpacking", "Food", "Solo"])

        clear_response = self.client.patch(
            "/frontend-api/profile/me/",
            data={"travel_tags": []},
            content_type="application/json",
        )
        self.assertEqual(clear_response.status_code, 200)
        self.assertEqual(clear_response.json()["member_profile"]["travel_tags"], [])

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_profile_me_persists_gallery_and_cover_photo(self) -> None:
        self.client.login(username="alice", password=self.password)

        patch_response = self.client.patch(
            "/frontend-api/profile/me/",
            data={
                "gallery_photos": [
                    "https://example.com/g1.jpg",
                    "https://example.com/g2.jpg",
                ],
                "cover_photo_url": "https://example.com/cover.jpg",
            },
            content_type="application/json",
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.content)
        member = patch_response.json()["member_profile"]
        self.assertEqual(member["cover_photo_url"], "https://example.com/cover.jpg")
        self.assertEqual(
            member["gallery_photos"],
            ["https://example.com/g1.jpg", "https://example.com/g2.jpg"],
        )

        get_response = self.client.get("/frontend-api/profile/me/")
        self.assertEqual(get_response.status_code, 200)
        profile = get_response.json()["profile"]
        self.assertEqual(profile["cover_photo_url"], "https://example.com/cover.jpg")
        self.assertEqual(len(profile["gallery_photos"]), 2)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_profile_me_persists_instagram_url(self) -> None:
        self.client.login(username="alice", password=self.password)

        patch_response = self.client.patch(
            "/frontend-api/profile/me/",
            data={"instagram_url": "https://instagram.com/alice.travels"},
            content_type="application/json",
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.content)
        member = patch_response.json()["member_profile"]
        self.assertEqual(member["instagram_url"], "https://instagram.com/alice.travels")

        get_response = self.client.get("/frontend-api/profile/me/")
        self.assertEqual(get_response.status_code, 200)
        profile = get_response.json()["profile"]
        self.assertEqual(profile["instagram_url"], "https://instagram.com/alice.travels")

        # Public profile endpoint must surface the same value.
        public_response = self.client.get(f"/frontend-api/profile/{self.alice.username}/")
        self.assertEqual(public_response.status_code, 200)
        public_profile = public_response.json()["profile"]
        self.assertEqual(
            public_profile["instagram_url"], "https://instagram.com/alice.travels"
        )

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_profile_detail_api_returns_host_metrics_and_new_fields(self) -> None:
        # Alice is the host with one published trip; a fresh reviewer leaves a 5-star review.
        reviewer = UserModel.objects.create_user(
            username="profile-detail-reviewer",
            email="profile-detail-reviewer@example.com",
            password=self.password,
        )
        ensure_profile(reviewer)

        trip = Trip.objects.create(
            host=self.alice,
            title="Alice's hosted trip",
            summary="Demo",
            destination="Tokyo, Japan",
            trip_type="city",
            is_published=True,
            status=Trip.STATUS_PUBLISHED,
        )
        Review.objects.create(
            author=reviewer,
            target_type=Review.TARGET_TRIP,
            target_key=str(trip.pk),
            rating=5,
            headline="Great",
            body="Loved it.",
        )

        response = self.client.get(f"/frontend-api/profile/{self.alice.username}/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        profile = body["profile"]

        # New fields must appear on the wire with snake_case names.
        for required_field in (
            "is_host",
            "member_since",
            "average_rating",
            "reviews_count",
            "trips_hosted",
            "travelers_hosted",
            "repeat_travelers_count",
            "median_response_hours",
            "cover_photo_url",
            "gallery_photos",
            "instagram_url",
        ):
            self.assertIn(required_field, profile, f"missing field: {required_field}")

        self.assertTrue(profile["is_host"])
        self.assertEqual(profile["trips_hosted"], 1)
        self.assertEqual(profile["reviews_count"], 1)
        self.assertEqual(profile["average_rating"], 5.0)

        # Host-only response contains review feed and distribution — nested inside profile
        # so Lovable's `data.profile.reviews_received` access path matches.
        self.assertIn("reviews_received", profile)
        self.assertIn("review_distribution", profile)
        self.assertEqual(profile["review_distribution"]["5"], 100.0)
        self.assertEqual(len(profile["reviews_received"]), 1)
        self.assertEqual(
            profile["reviews_received"][0]["author_username"], "profile-detail-reviewer"
        )
        self.assertEqual(profile["reviews_received"][0]["trip_id"], trip.pk)

        # reviews_written list also surfaced inside profile (empty for the host).
        self.assertIn("reviews_written", profile)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_profile_detail_api_traveler_omits_host_only_payload_sections(self) -> None:
        # A user with no hosted trips is_host=False; review_distribution + reviews_received empty.
        traveler = UserModel.objects.create_user(
            username="traveler-only",
            email="traveler-only@example.com",
            password=self.password,
        )
        ensure_profile(traveler)
        response = self.client.get(f"/frontend-api/profile/{traveler.username}/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["profile"]["is_host"])
        self.assertEqual(body["profile"]["reviews_received"], [])
        self.assertEqual(body["profile"]["review_distribution"], {})

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_trip_detail_includes_review_list_and_viewer_review(self) -> None:
        # Trip hosted by alice; bob writes a review; trip detail must surface
        # both the list and bob's own viewer_review entry on his next visit.
        from datetime import timedelta
        future_start = timezone.now() + timedelta(days=30)
        trip = Trip.objects.create(
            host=self.alice,
            title="Trip with reviews",
            summary="Demo",
            destination="Tokyo",
            trip_type="city",
            is_published=True,
            status=Trip.STATUS_PUBLISHED,
            starts_at=future_start,
            ends_at=future_start + timedelta(days=5),
        )
        Review.objects.create(
            author=self.bob,
            target_type=Review.TARGET_TRIP,
            target_key=str(trip.pk),
            rating=4,
            headline="Great",
            body="Solid time overall.",
        )

        # Anonymous viewer: list shows the review, viewer_review is null.
        anon_response = self.client.get(f"/frontend-api/trips/{trip.pk}/")
        self.assertEqual(anon_response.status_code, 200)
        anon_trip = anon_response.json()["trip"]
        self.assertIn("reviews", anon_trip)
        self.assertEqual(len(anon_trip["reviews"]), 1)
        self.assertEqual(anon_trip["reviews"][0]["rating"], 4)
        self.assertIsNone(anon_trip.get("viewer_review"))
        self.assertFalse(anon_trip.get("can_review"))
        # Aggregate values are surfaced so the Reviews card renders stars + count.
        self.assertEqual(anon_trip.get("reviews_count"), 1)
        self.assertEqual(anon_trip.get("average_rating"), 4.0)

        # Bob (the reviewer) sees his own review surfaced as viewer_review.
        self.client.login(username="bob", password=self.password)
        bob_response = self.client.get(f"/frontend-api/trips/{trip.pk}/")
        bob_trip = bob_response.json()["trip"]
        self.assertEqual(len(bob_trip["reviews"]), 1)
        self.assertIsNotNone(bob_trip["viewer_review"])
        self.assertEqual(bob_trip["viewer_review"]["rating"], 4)
        self.assertTrue(bob_trip["viewer_review"]["is_mine"])
        self.assertTrue(bob_trip.get("can_review"))

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_profile_detail_api_includes_completeness_only_for_self(self) -> None:
        # When viewer is the profile owner, profile_completeness is populated.
        self.client.login(username="alice", password=self.password)
        self_response = self.client.get(f"/frontend-api/profile/{self.alice.username}/")
        self.assertEqual(self_response.status_code, 200)
        completeness = self_response.json()["profile"]["profile_completeness"]
        self.assertIsNotNone(completeness)
        self.assertIn("is_complete", completeness)
        self.assertIn("missing_fields", completeness)

        # When viewed by someone else, completeness is null.
        self.client.logout()
        viewer = UserModel.objects.create_user(
            username="profile-detail-viewer",
            email="profile-detail-viewer@example.com",
            password=self.password,
        )
        ensure_profile(viewer)
        self.client.login(username="profile-detail-viewer", password=self.password)
        other_response = self.client.get(f"/frontend-api/profile/{self.alice.username}/")
        self.assertEqual(other_response.status_code, 200)
        self.assertIsNone(other_response.json()["profile"]["profile_completeness"])

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_trip_list_destination_filter_normalizes_slug_separators(self) -> None:
        now = timezone.now()
        Trip.objects.create(
            host=self.alice,
            title="Coastal escape",
            summary="Cliffs and lemons",
            destination="Amalfi Coast",
            starts_at=now + timezone.timedelta(days=5),
            is_published=True,
        )
        for separator_form in ("amalfi_coast", "amalfi-coast", "amalfi coast"):
            with self.subTest(form=separator_form):
                response = self.client.get(
                    f"/frontend-api/trips/?destination={separator_form}"
                )
                self.assertEqual(response.status_code, 200)
                titles = {trip["title"] for trip in response.json()["trips"]}
                self.assertIn("Coastal escape", titles)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_trip_list_sort_recent_orders_by_start_date_desc(self) -> None:
        now = timezone.now()
        Trip.objects.create(
            host=self.alice,
            title="Near Trip",
            summary="Soon",
            destination="A",
            starts_at=now + timezone.timedelta(days=3),
            is_published=True,
        )
        Trip.objects.create(
            host=self.alice,
            title="Far Trip",
            summary="Later",
            destination="B",
            starts_at=now + timezone.timedelta(days=60),
            is_published=True,
        )

        response = self.client.get("/frontend-api/trips/?sort=recent")
        self.assertEqual(response.status_code, 200)
        trips = response.json()["trips"]
        # sort=recent orders by starts_at desc, so Far Trip should come first.
        self.assertGreaterEqual(len(trips), 2)
        self.assertEqual(trips[0]["title"], "Far Trip")

    # -- Blog list ?q / ?author=me -------------------------------------------

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_blog_list_q_filter_matches_title_and_excerpt(self) -> None:
        Blog.objects.create(
            author=self.alice,
            slug="kyoto-streets",
            title="Walking Kyoto's Streets",
            excerpt="Old alleys and tea houses.",
            body="...",
            is_published=True,
        )
        Blog.objects.create(
            author=self.alice,
            slug="patagonia-trek",
            title="Patagonia Trek",
            excerpt="Windy ridges.",
            body="...",
            is_published=True,
        )

        response = self.client.get("/frontend-api/blogs/?q=kyoto")
        self.assertEqual(response.status_code, 200)
        slugs = {row["slug"] for row in response.json()["blogs"]}
        self.assertIn("kyoto-streets", slugs)
        self.assertNotIn("patagonia-trek", slugs)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_blog_list_author_me_returns_drafts_and_published_with_status(self) -> None:
        Blog.objects.create(
            author=self.alice,
            slug="alice-draft",
            title="Alice Draft",
            excerpt="Draft excerpt",
            body="...",
            is_published=False,
        )
        Blog.objects.create(
            author=self.alice,
            slug="alice-published",
            title="Alice Published",
            excerpt="Published excerpt",
            body="...",
            is_published=True,
        )
        # Blog by someone else must not appear.
        Blog.objects.create(
            author=self.bob,
            slug="bob-post",
            title="Bob's post",
            excerpt="...",
            body="...",
            is_published=True,
        )

        self.client.login(username="alice", password=self.password)
        response = self.client.get("/frontend-api/blogs/?author=me")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        slugs_by_status = {row["slug"]: row.get("status") for row in payload["blogs"]}
        self.assertEqual(
            slugs_by_status,
            {"alice-draft": "draft", "alice-published": "published"},
        )

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_blog_list_author_me_requires_authentication(self) -> None:
        response = self.client.get("/frontend-api/blogs/?author=me")
        self.assertEqual(response.status_code, 401)


class UnifiedSearchApiTests(TestCase):
    def setUp(self) -> None:
        self.password = "UnifiedSearchPass!123456"
        self.kyoto_host = UserModel.objects.create_user(
            username="kyoto_host",
            email="kyoto@example.com",
            password=self.password,
        )
        self.goa_host = UserModel.objects.create_user(
            username="goa_host",
            email="goa@example.com",
            password=self.password,
        )
        self.food_scout = UserModel.objects.create_user(
            username="food_scout",
            email="food@example.com",
            password=self.password,
        )
        self.quiet_reader = UserModel.objects.create_user(
            username="quiet_reader",
            email="reader@example.com",
            password=self.password,
        )

        kyoto_profile = ensure_profile(self.kyoto_host)
        _set_profile_fields(
            kyoto_profile,
            display_name="Kyoto Host",
            bio="Kyoto food guide and host.",
            location="Kyoto",
            travel_tags=["Food", "Culture"],
        )
        kyoto_profile.save(update_fields=["display_name", "bio", "location", "travel_tags", "updated_at"])

        goa_profile = ensure_profile(self.goa_host)
        _set_profile_fields(
            goa_profile,
            display_name="Goa Host",
            bio="Beach route builder.",
            location="Goa",
            travel_tags=["Beach", "Chill"],
        )
        goa_profile.save(update_fields=["display_name", "bio", "location", "travel_tags", "updated_at"])

        food_profile = ensure_profile(self.food_scout)
        _set_profile_fields(
            food_profile,
            display_name="Food Scout",
            bio="Finds food-first itineraries.",
            location="Kyoto",
            travel_tags=["Food"],
        )
        food_profile.save(update_fields=["display_name", "bio", "location", "travel_tags", "updated_at"])

        reader_profile = ensure_profile(self.quiet_reader)
        _set_profile_fields(
            reader_profile,
            display_name="Quiet Reader",
            bio="Reads travel stories.",
            location="Delhi",
            travel_tags=["Stories"],
        )
        reader_profile.save(update_fields=["display_name", "bio", "location", "travel_tags", "updated_at"])

        now = timezone.now()
        Trip.objects.create(
            host=self.kyoto_host,
            title="Kyoto Food Walk",
            summary="Markets and tea houses.",
            destination="Kyoto, Japan",
            starts_at=now + timezone.timedelta(days=5),
            is_published=True,
            trip_type="food-culture",
            budget_tier="mid",
            difficulty_level="easy",
            traffic_score=90,
        )
        Trip.objects.create(
            host=self.goa_host,
            title="Goa Beach Escape",
            summary="Sunrise swims.",
            destination="Goa, India",
            starts_at=now + timezone.timedelta(days=9),
            is_published=True,
            trip_type="coastal",
            budget_tier="budget",
            difficulty_level="easy",
            traffic_score=70,
        )

        Blog.objects.create(
            author=self.kyoto_host,
            slug="kyoto-streets",
            title="Kyoto Street Notes",
            excerpt="Tea counters and alley food spots.",
            body="Kyoto story body.",
            location="Kyoto",
            tags=["Food", "Culture"],
            is_published=True,
            reads=120,
        )
        Blog.objects.create(
            author=self.goa_host,
            slug="goa-sunrise",
            title="Goa Sunrise Notes",
            excerpt="Beach mornings.",
            body="Goa story body.",
            location="Goa",
            tags=["Beach"],
            is_published=True,
            reads=80,
        )

        FollowRelation.objects.create(follower=self.food_scout, following=self.kyoto_host)
        FollowRelation.objects.create(follower=self.quiet_reader, following=self.kyoto_host)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_search_api_all_returns_mixed_results_and_counts(self) -> None:
        response = self.client.get("/frontend-api/search/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["intent"], "all")
        self.assertEqual(payload["page_size"], 12)
        self.assertEqual(payload["available_sorts"], [{"value": "recommended", "label": "Recommended"}])
        self.assertEqual(
            payload["counts"]["all"],
            payload["counts"]["trips"] + payload["counts"]["destinations"] + payload["counts"]["stories"] + payload["counts"]["people"],
        )
        kinds = {row["result_kind"] for row in payload["results"]}
        self.assertTrue({"trip", "destination", "story", "person"}.issubset(kinds))

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_search_api_legacy_tab_maps_to_story_intent(self) -> None:
        response = self.client.get("/frontend-api/search/?q=kyoto&tab=stories")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["intent"], "stories")
        self.assertTrue(payload["meta"]["legacy_tab_mapped"])
        self.assertEqual({row["result_kind"] for row in payload["results"]}, {"story"})
        self.assertEqual(payload["results"][0]["slug"], "kyoto-streets")

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_search_api_trips_supports_filters_and_best_match(self) -> None:
        response = self.client.get(
            "/frontend-api/search/?intent=trips&q=kyoto&destination=kyoto&trip_type=food-culture&budget=mid&difficulty=easy&sort=best_match"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["intent"], "trips")
        self.assertEqual(payload["total_results"], 1)
        self.assertEqual(payload["applied_filters"]["destination"], "kyoto")
        self.assertEqual(payload["applied_filters"]["trip_type"], "food-culture")
        self.assertEqual(payload["results"][0]["title"], "Kyoto Food Walk")
        self.assertEqual(payload["results"][0]["result_kind"], "trip")

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_search_api_trips_pagination_reports_total_and_showing_range(self) -> None:
        for index in range(11):
            Trip.objects.create(
                host=self.kyoto_host,
                title=f"Kyoto Extra Trip {index + 1}",
                summary="More Kyoto inventory.",
                destination="Kyoto, Japan",
                starts_at=timezone.now() + timezone.timedelta(days=30 + index),
                trip_type="food-culture",
                budget_tier="mid",
                difficulty_level="easy",
                traffic_score=40 - index,
            )

        response = self.client.get("/frontend-api/search/?intent=trips&page=2")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["intent"], "trips")
        self.assertEqual(payload["total_results"], 13)
        self.assertEqual(payload["showing_from"], 13)
        self.assertEqual(payload["showing_to"], 13)
        self.assertEqual(len(payload["results"]), 1)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_search_api_destinations_include_canonical_trip_clickthrough(self) -> None:
        response = self.client.get("/frontend-api/search/?intent=destinations&q=kyoto")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["intent"], "destinations")
        self.assertGreaterEqual(payload["total_results"], 1)
        row = payload["results"][0]
        self.assertEqual(row["result_kind"], "destination")
        self.assertEqual(row["name"], "Kyoto")
        self.assertEqual(
            row["target_url"],
            "/search?q=Kyoto&intent=trips&destination=Kyoto&page=1&sort=best_match",
        )

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_search_api_legacy_destination_query_is_canonicalized_to_trips_query(self) -> None:
        response = self.client.get("/frontend-api/search/?destination=Kyoto")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["intent"], "trips")
        self.assertEqual(payload["query"], "Kyoto")
        self.assertTrue(payload["meta"]["legacy_destination_query_mapped"])
        self.assertEqual(payload["meta"]["canonical_params"]["q"], "Kyoto")
        self.assertEqual(payload["meta"]["canonical_params"]["destination"], "Kyoto")
        self.assertEqual(payload["meta"]["canonical_params"]["sort"], "best_match")

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_search_api_people_filters_travel_tag_and_hosted_only(self) -> None:
        response = self.client.get("/frontend-api/search/?intent=people&travel_tag=Food&hosted_only=true")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["intent"], "people")
        self.assertEqual(payload["applied_filters"]["travel_tag"], "Food")
        self.assertTrue(payload["applied_filters"]["hosted_only"])
        usernames = {row["username"] for row in payload["results"]}
        self.assertIn("kyoto_host", usernames)
        self.assertNotIn("food_scout", usernames)
        self.assertEqual(payload["results"][0]["url"], "/u/kyoto_host/")


class FrontendShellTests(TestCase):
    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_shell_injects_brand_assets_and_inline_runtime_config(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dist_dir = Path(temp_dir)
            assets_dir = dist_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            (dist_dir / "index.html").write_text(
                (
                    "<!doctype html><html><head><title>Lovable</title></head>"
                    "<body><div id=\"root\"></div>"
                    "<script type=\"module\" src=\"/assets/index.js\"></script></body></html>"
                ),
                encoding="utf-8",
            )
            (assets_dir / "index.js").write_text("console.log('frontend');", encoding="utf-8")

            with override_settings(LOVABLE_FRONTEND_DIST_DIR=dist_dir):
                request = RequestFactory().get("/")
                response = frontend_entrypoint_view(request)
                self.assertEqual(response.status_code, 200)
                html = response.content.decode("utf-8")
                self.assertIn("/static/frontend-brand/tokens.css", html)
                self.assertIn("/static/frontend-brand/overrides.css", html)
                self.assertIn('data-tapne-runtime="inline-config"', html)
                self.assertIn("window.__TAPNE_FRONTEND_CONFIG__", html)
                self.assertNotIn("/frontend-runtime.js", html)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_shell_deduplicates_existing_brand_assets_and_runtime_script(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dist_dir = Path(temp_dir)
            assets_dir = dist_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            (dist_dir / "index.html").write_text(
                (
                    "<!doctype html><html><head><title>Lovable</title>"
                    '<link rel="stylesheet" href="/static/frontend-brand/tokens.css">'
                    '<link rel="stylesheet" href="/static/frontend-brand/overrides.css">'
                    "</head><body><div id=\"root\"></div>"
                    '<script src="/frontend-runtime.js"></script>'
                    "<script type=\"module\" src=\"/assets/index.js\"></script></body></html>"
                ),
                encoding="utf-8",
            )
            (assets_dir / "index.js").write_text("console.log('frontend');", encoding="utf-8")

            with override_settings(LOVABLE_FRONTEND_DIST_DIR=dist_dir):
                request = RequestFactory().get("/")
                response = frontend_entrypoint_view(request)
                self.assertEqual(response.status_code, 200)
                html = response.content.decode("utf-8")
                self.assertEqual(html.count("frontend-brand/tokens"), 1)
                self.assertEqual(html.count("frontend-brand/overrides"), 1)
                self.assertNotIn('<script src="/frontend-runtime.js"></script>', html)
                self.assertEqual(html.count('data-tapne-runtime="inline-config"'), 1)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_shell_renders_for_authenticated_member_with_live_session_payload(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dist_dir = Path(temp_dir)
            assets_dir = dist_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            (dist_dir / "index.html").write_text(
                (
                    "<!doctype html><html><head><title>Lovable</title></head>"
                    "<body><div id=\"root\"></div>"
                    "<script type=\"module\" src=\"/assets/index.js\"></script></body></html>"
                ),
                encoding="utf-8",
            )
            (assets_dir / "index.js").write_text("console.log('frontend');", encoding="utf-8")

            user = UserModel.objects.create_user(
                username="shell-user",
                email="shell@example.com",
                password="S3curePassw0rd!!",
            )
            Trip.objects.create(
                host=user,
                title="Authenticated Shell Trip",
                summary="Trip row used to exercise datetime serialization in the shell payload.",
                destination="Goa",
                starts_at=timezone.now() + timezone.timedelta(days=14),
                is_published=True,
            )

            with override_settings(LOVABLE_FRONTEND_DIST_DIR=dist_dir):
                request = RequestFactory().get("/")
                request.user = user
                response = frontend_entrypoint_view(request)
                self.assertEqual(response.status_code, 200)
                html = response.content.decode("utf-8")
                self.assertIn("shell-user", html)
                self.assertIn("created_trips", html)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_shell_renders_for_trip_detail_entrypoint_route(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dist_dir = Path(temp_dir)
            assets_dir = dist_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            (dist_dir / "index.html").write_text(
                (
                    "<!doctype html><html><head><title>Lovable</title></head>"
                    "<body><div id=\"root\"></div>"
                    "<script type=\"module\" src=\"/assets/index.js\"></script></body></html>"
                ),
                encoding="utf-8",
            )
            (assets_dir / "index.js").write_text("console.log('frontend');", encoding="utf-8")

            with override_settings(LOVABLE_FRONTEND_DIST_DIR=dist_dir):
                request = RequestFactory().get("/trips/1/")
                response = frontend_entrypoint_view(request, trip_id=1)
                self.assertEqual(response.status_code, 200)
                html = response.content.decode("utf-8")
                self.assertIn('data-tapne-runtime="inline-config"', html)
                self.assertIn("window.__TAPNE_FRONTEND_CONFIG__", html)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_shell_renders_for_blog_detail_entrypoint_route(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dist_dir = Path(temp_dir)
            assets_dir = dist_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            (dist_dir / "index.html").write_text(
                (
                    "<!doctype html><html><head><title>Lovable</title></head>"
                    "<body><div id=\"root\"></div>"
                    "<script type=\"module\" src=\"/assets/index.js\"></script></body></html>"
                ),
                encoding="utf-8",
            )
            (assets_dir / "index.js").write_text("console.log('frontend');", encoding="utf-8")

            with override_settings(LOVABLE_FRONTEND_DIST_DIR=dist_dir):
                request = RequestFactory().get("/blogs/vietnam/")
                response = frontend_entrypoint_view(request, slug="vietnam")
                self.assertEqual(response.status_code, 200)
                html = response.content.decode("utf-8")
                self.assertIn('data-tapne-runtime="inline-config"', html)
                self.assertIn("window.__TAPNE_FRONTEND_CONFIG__", html)


class FrontendShellToggleTests(TestCase):
    @staticmethod
    def _reload_urlconfs() -> None:
        clear_url_caches()
        importlib.reload(frontend_urls)
        importlib.reload(tapne_urls)
        set_urlconf(None)

    @override_settings(LOVABLE_FRONTEND_ENABLED=False)
    def test_trips_route_still_serves_spa_shell_when_retired_lovable_flag_is_false(self) -> None:
        self._reload_urlconfs()
        self.addCleanup(self._reload_urlconfs)

        response = self.client.get("/trips/")

        self.assertEqual(response.status_code, 200)
        self.assertIn('<div id="root">', response.content.decode("utf-8"))

    @override_settings(LOVABLE_FRONTEND_ENABLED=False)
    def test_frontend_api_routes_stay_available_when_lovable_is_disabled(self) -> None:
        self._reload_urlconfs()
        self.addCleanup(self._reload_urlconfs)

        response = self.client.get("/frontend-api/session/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    @override_settings(DEBUG=True, MEDIA_URL="/media/")
    def test_debug_media_route_serves_files_before_spa_catchall(self) -> None:
        with TemporaryDirectory() as temp_dir:
            media_root = Path(temp_dir)
            image_path = media_root / "trip_banners" / "demo.jpg"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(b"demo image bytes")

            with override_settings(MEDIA_ROOT=media_root):
                self._reload_urlconfs()
                self.addCleanup(self._reload_urlconfs)

                response = self.client.get("/media/trip_banners/demo.jpg")
                try:
                    response_content = (
                        cast(StreamingHttpResponse, response).getvalue()
                        if getattr(response, "streaming", False)
                        else response.content
                    )
                finally:
                    response.close()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'<div id="root">', response_content)
        self.assertEqual(response_content, b"demo image bytes")
