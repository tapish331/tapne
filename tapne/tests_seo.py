from __future__ import annotations

from django.test import TestCase, override_settings

SEO_ALLOWED_HOSTS = ["testserver", "tapnetravel.com", "www.tapnetravel.com"]


@override_settings(
    ALLOWED_HOSTS=SEO_ALLOWED_HOSTS,
    CANONICAL_HOST="tapnetravel.com",
    CANONICAL_SCHEME="https",
    CANONICAL_HOST_REDIRECT_ENABLED=False,
)
class SeoMetadataTests(TestCase):
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
