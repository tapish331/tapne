from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from blogs.models import Blog
from frontend.views import frontend_entrypoint_view
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


class FrontendShellTests(TestCase):
    @override_settings(LOVABLE_FRONTEND_ENABLED=True, TAPNE_ENABLE_DEMO_DATA=False)
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

    @override_settings(LOVABLE_FRONTEND_ENABLED=True, TAPNE_ENABLE_DEMO_DATA=False)
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

    @override_settings(LOVABLE_FRONTEND_ENABLED=True, TAPNE_ENABLE_DEMO_DATA=False)
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

    @override_settings(LOVABLE_FRONTEND_ENABLED=True, TAPNE_ENABLE_DEMO_DATA=False)
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

    @override_settings(LOVABLE_FRONTEND_ENABLED=True, TAPNE_ENABLE_DEMO_DATA=False)
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
