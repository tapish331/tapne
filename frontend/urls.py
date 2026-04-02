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
            path("", views.frontend_entrypoint_view, name="entrypoint-home"),
            path("trips", views.frontend_entrypoint_view, name="entrypoint-trips"),
            path("trips/", views.frontend_entrypoint_view),
            re_path(r"^trips/(?P<trip_id>\d+)/?$", views.frontend_entrypoint_view, name="entrypoint-trip-detail"),
            path("blogs", views.frontend_entrypoint_view, name="entrypoint-blogs"),
            path("blogs/", views.frontend_entrypoint_view),
            re_path(
                r"^blogs/(?P<slug>(?!create$)[-a-zA-Z0-9_]+)/?$",
                views.frontend_entrypoint_view,
                name="entrypoint-blog-detail",
            ),
            path("login", views.frontend_entrypoint_view, name="entrypoint-login"),
            path("login/", views.frontend_entrypoint_view),
            path("signup", views.frontend_entrypoint_view, name="entrypoint-signup"),
            path("signup/", views.frontend_entrypoint_view),
            path("profile", views.frontend_entrypoint_view, name="entrypoint-profile"),
            path("profile/", views.frontend_entrypoint_view),
            path("create-trip", views.frontend_entrypoint_view, name="entrypoint-create-trip"),
            path("create-trip/", views.frontend_entrypoint_view),
            path("my-trips", views.frontend_entrypoint_view, name="entrypoint-my-trips"),
            path("my-trips/", views.frontend_entrypoint_view),
        ]
    )
