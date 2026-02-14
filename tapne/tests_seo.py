from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from blogs.models import Blog
from trips.models import Trip

SEO_ALLOWED_HOSTS = ["testserver", "tapnetravel.com", "www.tapnetravel.com"]
UserModel = get_user_model()


@override_settings(
    ALLOWED_HOSTS=SEO_ALLOWED_HOSTS,
    CANONICAL_HOST="tapnetravel.com",
    CANONICAL_SCHEME="https",
    CANONICAL_HOST_REDIRECT_ENABLED=False,
)
class SeoMetadataTests(TestCase):
    def setUp(self) -> None:
        self.password = "SeoPass!123456"
        self.host = UserModel.objects.create_user(
            username="seo-host",
            email="seo-host@example.com",
            password=self.password,
        )

    def test_google_site_verification_file_is_served_at_root(self) -> None:
        response = self.client.get("/google7c0adbf9fe517d15.html", HTTP_HOST="tapnetravel.com")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "google-site-verification: google7c0adbf9fe517d15.html")

    def test_robots_txt_includes_sitemap_on_canonical_host(self) -> None:
        response = self.client.get("/robots.txt", HTTP_HOST="www.tapnetravel.com")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response["Content-Type"])
        self.assertContains(response, "User-agent: *")
        self.assertContains(response, "Allow: /")
        self.assertContains(response, "Sitemap: https://tapnetravel.com/sitemap.xml")

    def test_sitemap_xml_lists_core_routes(self) -> None:
        response = self.client.get("/sitemap.xml", HTTP_HOST="www.tapnetravel.com")

        self.assertEqual(response.status_code, 200)
        self.assertIn("application/xml", response["Content-Type"])
        self.assertContains(response, "<urlset")
        self.assertContains(response, "<loc>https://tapnetravel.com/</loc>")
        self.assertContains(response, "<loc>https://tapnetravel.com/search/</loc>")
        self.assertContains(response, "<loc>https://tapnetravel.com/trips/</loc>")
        self.assertContains(response, "<loc>https://tapnetravel.com/blogs/</loc>")

    def test_base_template_emits_canonical_link(self) -> None:
        response = self.client.get("/", HTTP_HOST="www.tapnetravel.com")

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<link rel="canonical" href="https://tapnetravel.com/">',
        )

    def test_base_template_emits_open_graph_and_twitter_tags(self) -> None:
        response = self.client.get("/", HTTP_HOST="www.tapnetravel.com")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<meta property="og:site_name" content="tapne">')
        self.assertContains(response, '<meta property="og:type" content="website">')
        self.assertContains(response, '<meta name="twitter:card" content="summary">')

    def test_home_page_emits_json_ld_script(self) -> None:
        response = self.client.get("/", HTTP_HOST="www.tapnetravel.com")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<script type="application/ld+json">')
        self.assertContains(response, '"@type":"WebSite"')

    def test_primary_navigation_does_not_include_creators_tab(self) -> None:
        response = self.client.get("/", HTTP_HOST="www.tapnetravel.com")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<a href="/search/?type=users">Creators</a>')

    def test_trip_detail_emits_dynamic_title_and_breadcrumbs(self) -> None:
        trip = Trip.objects.create(
            host=self.host,
            title="Kyoto Spring Food Walk",
            summary="Street-food and market route.",
            description="Detailed itinerary for two days in Kyoto.",
            destination="Kyoto",
            starts_at=timezone.now() + timedelta(days=7),
            traffic_score=42,
        )

        response = self.client.get(reverse("trips:detail", kwargs={"trip_id": trip.pk}), HTTP_HOST="www.tapnetravel.com")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>Kyoto Spring Food Walk | tapne</title>", html=True)
        self.assertContains(response, '<nav class="breadcrumbs" aria-label="Breadcrumb">')
        self.assertContains(response, '>Trips<')
        self.assertContains(response, '>Kyoto Spring Food Walk<')
        self.assertContains(response, '"@type":"TouristTrip"')
        self.assertContains(response, '"@type":"BreadcrumbList"')

    def test_blog_detail_emits_dynamic_title_and_structured_data(self) -> None:
        blog = Blog.objects.create(
            author=self.host,
            slug="kyoto-market-notes",
            title="Kyoto Market Notes",
            excerpt="Quick field notes from Nishiki.",
            body="Practical route notes and food stop recommendations.",
            is_published=True,
        )

        response = self.client.get(reverse("blogs:detail", kwargs={"slug": blog.slug}), HTTP_HOST="www.tapnetravel.com")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>Kyoto Market Notes | tapne</title>", html=True)
        self.assertContains(response, '<nav class="breadcrumbs" aria-label="Breadcrumb">')
        self.assertContains(response, '>Blogs<')
        self.assertContains(response, '>Kyoto Market Notes<')
        self.assertContains(response, '"@type":"BlogPosting"')
        self.assertContains(response, '"@type":"BreadcrumbList"')

    def test_public_profile_emits_creators_breadcrumb_and_profile_meta(self) -> None:
        response = self.client.get(reverse("public-profile", kwargs={"username": self.host.username}), HTTP_HOST="www.tapnetravel.com")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"<title>{self.host.username} | tapne</title>", html=True)
        self.assertContains(response, '<meta property="og:type" content="profile">')
        self.assertContains(response, '<nav class="breadcrumbs" aria-label="Breadcrumb">')
        self.assertContains(response, '>Creators<')
        self.assertContains(response, f'>@{self.host.username}<')
        self.assertContains(response, '"@type":"Person"')
        self.assertContains(response, '"@type":"BreadcrumbList"')

    def test_search_users_page_has_creators_breadcrumb(self) -> None:
        response = self.client.get(f"{reverse('search:search')}?type=users", HTTP_HOST="www.tapnetravel.com")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>Creators | tapne</title>", html=True)
        self.assertContains(response, '<nav class="breadcrumbs" aria-label="Breadcrumb">')
        self.assertContains(response, '>Creators<')


@override_settings(
    ALLOWED_HOSTS=SEO_ALLOWED_HOSTS,
    CANONICAL_HOST="tapnetravel.com",
    CANONICAL_SCHEME="https",
    CANONICAL_HOST_REDIRECT_ENABLED=True,
)
class CanonicalHostRedirectMiddlewareTests(TestCase):
    def test_redirects_www_host_to_canonical_host(self) -> None:
        response = self.client.get("/search/?q=kyoto", HTTP_HOST="www.tapnetravel.com", secure=True)

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://tapnetravel.com/search/?q=kyoto")

    def test_does_not_redirect_when_request_already_uses_canonical_host(self) -> None:
        response = self.client.get("/search/?q=kyoto", HTTP_HOST="tapnetravel.com", secure=True)

        self.assertEqual(response.status_code, 200)
