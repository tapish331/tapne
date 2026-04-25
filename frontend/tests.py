from __future__ import annotations

import importlib
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import Client, TestCase, override_settings
from django.urls import clear_url_caches, set_urlconf
from django.utils import timezone

import frontend.urls as frontend_urls
import tapne.urls as tapne_urls
from blogs.models import Blog
from frontend.views import frontend_entrypoint_view
from reviews.models import Review
from social.models import FollowRelation
from trips.models import Trip

UserModel = get_user_model()


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

        create_response = self.client.post(
            "/frontend-api/trips/drafts/",
            data=(
                '{"title":"Live Draft","destination":"Goa","summary":"Draft summary",'
                '"highlights":["Beach walk","Cafe stops"],"trip_vibe":["Social"],'
                '"starts_at":"2030-01-10T10:00:00+05:30","ends_at":"2030-01-12T10:00:00+05:30",'
                '"total_seats":"8","total_trip_price":"24000"}'
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        created_trip_id = create_response.json()["trip"]["id"]

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

        detail_response = self.client.get(f"/frontend-api/trips/{created_trip_id}/")
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = detail_response.json()
        self.assertEqual(detail_payload["source"], "live-db")
        self.assertEqual(detail_payload["host"]["username"], "frontend-user")
        self.assertGreaterEqual(len(detail_payload["participants"]), 1)


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
    def test_trips_route_does_not_render_spa_shell_when_lovable_is_disabled(self) -> None:
        self._reload_urlconfs()
        self.addCleanup(self._reload_urlconfs)

        response = self.client.get("/trips/")

        self.assertEqual(response.status_code, 404)
        self.assertNotIn('<div id="root">', response.content.decode("utf-8"))

    @override_settings(LOVABLE_FRONTEND_ENABLED=False)
    def test_frontend_api_routes_stay_available_when_lovable_is_disabled(self) -> None:
        self._reload_urlconfs()
        self.addCleanup(self._reload_urlconfs)

        response = self.client.get("/frontend-api/session/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
