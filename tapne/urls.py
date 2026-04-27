# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest, JsonResponse
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import URLPattern, URLResolver, include, path, re_path
from django.views.generic import RedirectView, TemplateView
from django.views.static import serve as static_serve

from frontend.views import frontend_entrypoint_view

from . import seo


def health(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok", "service": "tapne-placeholder"})


# Only backend-only routes live here. Every user-facing URL is served by the
# Lovable SPA shell via the global catch-all at the bottom. Django-rendered
# page apps were retired in the SPA cutover; each remaining app `include`
# below is expected to expose API/file-serving routes only — not templated
# pages. See RULES.md §3.
urlpatterns: list[URLPattern | URLResolver] = []

if settings.DEBUG:
    urlpatterns.append(
        path(
            "static/frontend-brand/<path:path>",
            static_serve,
            {"document_root": settings.BASE_DIR / "static" / "frontend-brand"},
        )
    )

urlpatterns += [
    path("", include("frontend.urls")),
    re_path(
        r"^u/(?P<username>[^/]+)/?$",
        RedirectView.as_view(url="/users/%(username)s", permanent=False, query_string=True),
        name="legacy-user-profile-redirect",
    ),
    path(
        "search/",
        RedirectView.as_view(url="/search", permanent=False, query_string=True),
        name="legacy-search-redirect",
    ),
    path(
        "accounts/login/",
        RedirectView.as_view(url="/", permanent=False, query_string=True),
        name="legacy-login-redirect",
    ),
    path(
        "accounts/signup/",
        RedirectView.as_view(url="/", permanent=False, query_string=True),
        name="legacy-signup-redirect",
    ),
    path(
        "accounts/logout/",
        RedirectView.as_view(url="/", permanent=False, query_string=True),
        name="legacy-logout-redirect",
    ),
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
    path("health/", health, name="health"),
    path("runtime/", include("runtime.urls")),
    path("uploads/", include("media.urls")),
    # Retained app includes serve backend APIs only (banner file-serving,
    # destination autocomplete, appearance JSON) — their templated page
    # views were removed in the SPA cutover.
    path("trips/", include("trips.urls")),
    path("settings/", include("settings_app.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()

urlpatterns += [
    # Global SPA catch-all — must be last. Every URL not matched above is
    # served as the Lovable SPA shell.
    re_path(r"^.*$", frontend_entrypoint_view, name="spa-catchall"),
]
