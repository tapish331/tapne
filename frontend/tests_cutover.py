from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from accounts.models import AccountProfile
from blogs.models import Blog

UserModel = get_user_model()


class FrontendCutoverRegressionTests(TestCase):
    def setUp(self) -> None:
        self.password = "CutoverPass!123456"
        self.user = UserModel.objects.create_user(
            username="cutover-user",
            email="cutover@example.com",
            password=self.password,
        )

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_legacy_profile_route_redirects_to_canonical_users_route(self) -> None:
        response = self.client.get("/u/cutover-user/?from=notif")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/users/cutover-user?from=notif")

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_legacy_search_route_redirects_to_canonical_search_route(self) -> None:
        response = self.client.get("/search/?q=goa&tab=stories")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/search?q=goa&tab=stories")

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_legacy_auth_routes_redirect_away_from_spa_catchall(self) -> None:
        for path in ("/accounts/login/", "/accounts/signup/", "/accounts/logout/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], "/")

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_blog_create_can_save_draft_for_author(self) -> None:
        self.client.login(username="cutover-user", password=self.password)

        response = self.client.post(
            "/frontend-api/blogs/",
            data='{"title":"Draft story","body":"Draft body","status":"draft"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        slug = response.json()["blog"]["slug"]
        draft = Blog.objects.get(slug=slug)
        self.assertFalse(draft.is_published)

        list_response = self.client.get("/frontend-api/blogs/?author=me")
        self.assertEqual(list_response.status_code, 200)
        statuses = {
            row["slug"]: row.get("status")
            for row in list_response.json()["blogs"]
        }
        self.assertEqual(statuses[slug], "draft")

        detail_response = self.client.get(f"/frontend-api/blogs/{slug}/")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["blog"]["slug"], slug)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_blog_patch_can_publish_draft_and_hidden_draft_returns_404_for_guests(self) -> None:
        draft = Blog.objects.create(
            author=self.user,
            slug="hidden-draft-story",
            title="Hidden Draft",
            excerpt="Private",
            body="Draft body",
            is_published=False,
        )

        guest_response = self.client.get(f"/frontend-api/blogs/{draft.slug}/")
        self.assertEqual(guest_response.status_code, 404)

        self.client.login(username="cutover-user", password=self.password)
        patch_response = self.client.patch(
            f"/frontend-api/blogs/{draft.slug}/",
            data='{"status":"published"}',
            content_type="application/json",
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.content)

        draft.refresh_from_db()
        self.assertTrue(draft.is_published)

    @override_settings(TAPNE_ENABLE_DEMO_DATA=False)
    def test_profile_patch_preserves_unchanged_legacy_email(self) -> None:
        legacy_user = UserModel.objects.create_user(
            username="legacy-profile",
            email="legacy@tapne.local",
            password=self.password,
        )
        legacy_profile = AccountProfile.objects.get(user=legacy_user)
        legacy_profile.display_name = "Legacy Profile"
        legacy_profile.save(update_fields=["display_name"])
        self.client.login(username="legacy-profile", password=self.password)

        response = self.client.patch(
            "/frontend-api/profile/me/",
            data='{"display_name":"Legacy Updated","travel_tags":["Food","Solo"]}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["profile"]["display_name"], "Legacy Updated")
        self.assertEqual(payload["profile"]["travel_tags"], ["Food", "Solo"])
