# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from accounts import views as accounts_views
from django.contrib import admin
from django.http import HttpRequest, JsonResponse
from django.urls import URLPattern, URLResolver, include, path
from django.views.generic import TemplateView

from . import seo


def health(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok", "service": "tapne-placeholder"})


urlpatterns: list[URLPattern | URLResolver] = [
    path(
        "google7c0adbf9fe517d15.html",
        TemplateView.as_view(
            template_name="google7c0adbf9fe517d15.html",
            content_type="text/html",
        ),
        name="google-site-verification",
    ),
    path("robots.txt", seo.robots_txt_view, name="robots-txt"),
    path("sitemap.xml", seo.sitemap_xml_view, name="sitemap-xml"),
    path("about/", TemplateView.as_view(template_name="pages/legal/about.html"), name="about"),
    path(
        "how-it-works/",
        TemplateView.as_view(template_name="pages/legal/how_it_works.html"),
        name="how-it-works",
    ),
    path("safety/", TemplateView.as_view(template_name="pages/legal/safety.html"), name="safety"),
    path("contact/", TemplateView.as_view(template_name="pages/legal/contact.html"), name="contact"),
    path("terms/", TemplateView.as_view(template_name="pages/legal/terms.html"), name="terms"),
    path("privacy/", TemplateView.as_view(template_name="pages/legal/privacy.html"), name="privacy"),
    path("", include("feed.urls")),
    path("health/", health, name="health"),
    path("runtime/", include("runtime.urls")),
    path("uploads/", include("media.urls")),
    path("search/", include("search.urls")),
    path("accounts/", include("accounts.urls")),
    path("trips/", include("trips.urls")),
    path("blogs/", include("blogs.urls")),
    path("social/", include("social.urls")),
    path("enroll/", include("enrollment.urls")),
    path("interactions/", include("interactions.urls")),
    path("reviews/", include("reviews.urls")),
    path("activity/", include("activity.urls")),
    path("settings/", include("settings_app.urls")),
    path("u/<str:username>/", accounts_views.public_profile_view, name="public-profile"),
    path("admin/", admin.site.urls),
]
