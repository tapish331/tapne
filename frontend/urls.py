from __future__ import annotations

from django.conf import settings
from django.urls import path, re_path

from . import views

app_name = "frontend"

urlpatterns = [
    path("frontend-runtime.js", views.runtime_config_js, name="runtime-config-js"),
    path("frontend-api/session/", views.session_api_view, name="api-session"),
    path("frontend-api/auth/login/", views.auth_login_api_view, name="api-auth-login"),
    path("frontend-api/auth/signup/", views.auth_signup_api_view, name="api-auth-signup"),
    path("frontend-api/auth/logout/", views.auth_logout_api_view, name="api-auth-logout"),
    path("frontend-api/home/", views.home_api_view, name="api-home"),
    path("frontend-api/trips/", views.trip_list_api_view, name="api-trips-list"),
    path("frontend-api/trips/<int:trip_id>/", views.trip_detail_api_view, name="api-trips-detail"),
    path("frontend-api/trips/drafts/", views.trip_draft_create_api_view, name="api-trip-draft-create"),
    path("frontend-api/trips/drafts/<int:trip_id>/", views.trip_draft_detail_api_view, name="api-trip-draft-detail"),
    path(
        "frontend-api/trips/drafts/<int:trip_id>/publish/",
        views.trip_draft_publish_api_view,
        name="api-trip-draft-publish",
    ),
    path("frontend-api/my-trips/", views.my_trips_api_view, name="api-my-trips"),
    path("frontend-api/blogs/", views.blog_list_api_view, name="api-blogs-list"),
    path("frontend-api/blogs/<slug:slug>/", views.blog_detail_api_view, name="api-blogs-detail"),
    path("frontend-api/profile/me/", views.my_profile_api_view, name="api-profile-me"),
    path("frontend-api/bookmarks/", views.bookmarks_api_view, name="api-bookmarks"),
    path("frontend-api/activity/", views.activity_api_view, name="api-activity"),
    path("frontend-api/settings/", views.settings_api_view, name="api-settings"),
    path("frontend-api/hosting-inbox/", views.hosting_inbox_api_view, name="api-hosting-inbox"),
    path("frontend-api/dm/inbox/", views.dm_inbox_api_view, name="api-dm-inbox"),
    path("frontend-api/dm/threads/<int:thread_id>/", views.dm_thread_api_view, name="api-dm-thread"),
    path("frontend-api/trips/<int:trip_id>/join-request/", views.trip_join_request_api_view, name="api-trip-join-request"),
    path("frontend-api/manage-trip/<int:trip_id>/", views.manage_trip_api_view, name="api-manage-trip"),
    path("frontend-api/manage-trip/<int:trip_id>/booking-status/", views.manage_trip_booking_status_view, name="api-manage-trip-booking-status"),
    re_path(r"^frontend-api/manage-trip/(?P<trip_id>\d+)/participants/(?P<participant_id>\d+)/remove/$", views.manage_trip_remove_participant_view, name="api-manage-trip-remove-participant"),
    path("frontend-api/manage-trip/<int:trip_id>/cancel/", views.manage_trip_cancel_view, name="api-manage-trip-cancel"),
    path("frontend-api/manage-trip/<int:trip_id>/message/", views.manage_trip_message_view, name="api-manage-trip-message"),
    path(
        "frontend-api/hosting-requests/<int:request_id>/decision/",
        views.hosting_decision_api_view,
        name="api-hosting-decision",
    ),
    re_path(r"^assets/(?P<asset_path>.+)$", views.frontend_asset_view, name="asset"),
    re_path(
        r"^(?P<artifact_name>(?:favicon\.ico|placeholder\.svg|manifest\.webmanifest|site\.webmanifest))$",
        views.frontend_root_artifact_view,
        name="root-artifact",
    ),
]

if settings.LOVABLE_FRONTEND_ENABLED:
    urlpatterns.extend(
        [
            # ── SPA root ──────────────────────────────────────────────────────────
            path("", views.frontend_entrypoint_view, name="entrypoint-home"),

            # ── Trips ─────────────────────────────────────────────────────────────
            # These must be declared here (frontend.urls is included first in
            # tapne/urls.py) so they are matched before trips/urls.py, which would
            # otherwise serve Django HTML templates for the same paths.
            path("trips", views.frontend_entrypoint_view, name="entrypoint-trips"),
            path("trips/", views.frontend_entrypoint_view),
            path("trips/create/", views.frontend_entrypoint_view, name="entrypoint-trip-create"),
            path("trips/mine/", views.frontend_entrypoint_view, name="entrypoint-trip-mine"),
            re_path(r"^trips/(?P<trip_id>\d+)/?$", views.frontend_entrypoint_view, name="entrypoint-trip-detail"),
            re_path(r"^trips/(?P<trip_id>\d+)/edit/?$", views.frontend_entrypoint_view, name="entrypoint-trip-edit"),
            re_path(r"^trips/(?P<trip_id>\d+)/delete/?$", views.frontend_entrypoint_view, name="entrypoint-trip-delete"),

            # ── Blogs ─────────────────────────────────────────────────────────────
            path("blogs", views.frontend_entrypoint_view, name="entrypoint-blogs"),
            path("blogs/", views.frontend_entrypoint_view),
            path("blogs/create/", views.frontend_entrypoint_view, name="entrypoint-blog-create"),
            re_path(
                r"^blogs/(?P<slug>(?!create$)[-a-zA-Z0-9_]+)/?$",
                views.frontend_entrypoint_view,
                name="entrypoint-blog-detail",
            ),
            re_path(
                r"^blogs/(?P<slug>[-a-zA-Z0-9_]+)/edit/?$",
                views.frontend_entrypoint_view,
                name="entrypoint-blog-edit",
            ),

            # ── Accounts ─────────────────────────────────────────────────────────
            # /accounts/login/ and /accounts/signup/ would otherwise hit the Django
            # template views inside accounts/urls.py.
            path("accounts/login/", views.frontend_entrypoint_view, name="entrypoint-accounts-login"),
            path("accounts/signup/", views.frontend_entrypoint_view, name="entrypoint-accounts-signup"),
            path("accounts/me/", views.frontend_entrypoint_view, name="entrypoint-accounts-me"),
            path("accounts/me/edit/", views.frontend_entrypoint_view, name="entrypoint-accounts-me-edit"),

            # ── Auth SPA routes (no trailing-slash variants) ──────────────────────
            path("login", views.frontend_entrypoint_view, name="entrypoint-login"),
            path("login/", views.frontend_entrypoint_view),
            path("signup", views.frontend_entrypoint_view, name="entrypoint-signup"),
            path("signup/", views.frontend_entrypoint_view),

            # ── Trip management ──────────────────────────────────────────────────
            re_path(r"^manage-trip/(?P<trip_id>\d+)/?$", views.frontend_entrypoint_view, name="entrypoint-manage-trip"),

            # ── Profile / trip management ─────────────────────────────────────────
            path("profile", views.frontend_entrypoint_view, name="entrypoint-profile"),
            path("profile/", views.frontend_entrypoint_view),
            path("create-trip", views.frontend_entrypoint_view, name="entrypoint-create-trip"),
            path("create-trip/", views.frontend_entrypoint_view),
            path("my-trips", views.frontend_entrypoint_view, name="entrypoint-my-trips"),
            path("my-trips/", views.frontend_entrypoint_view),

            # ── Other Django HTML pages (served via SPA Under Construction) ───────
            path("search/", views.frontend_entrypoint_view, name="entrypoint-search"),
            path("activity/", views.frontend_entrypoint_view, name="entrypoint-activity"),
            path("settings/", views.frontend_entrypoint_view, name="entrypoint-settings"),
            path("settings/appearance/", views.frontend_entrypoint_view, name="entrypoint-settings-appearance"),
            path("social/bookmarks/", views.frontend_entrypoint_view, name="entrypoint-bookmarks"),
            path("interactions/dm/", views.frontend_entrypoint_view, name="entrypoint-dm-inbox"),
            re_path(r"^interactions/dm/(?P<thread_id>\d+)/?$", views.frontend_entrypoint_view, name="entrypoint-dm-thread"),
            path("enroll/hosting/inbox/", views.frontend_entrypoint_view, name="entrypoint-hosting-inbox"),
            re_path(r"^u/(?P<username>[^/]+)/?$", views.frontend_entrypoint_view, name="entrypoint-public-profile"),
        ]
    )
