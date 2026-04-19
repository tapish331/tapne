from __future__ import annotations

from django.urls import path, re_path

from . import views

app_name = "frontend"

urlpatterns = [
    path("frontend-runtime.js", views.runtime_config_js, name="runtime-config-js"),
    path("frontend-api/session/", views.session_api_view, name="api-session"),
    path("frontend-api/auth/login/", views.auth_login_api_view, name="api-auth-login"),
    path("frontend-api/auth/signup/", views.auth_signup_api_view, name="api-auth-signup"),
    path("frontend-api/auth/logout/", views.auth_logout_api_view, name="api-auth-logout"),
    path("frontend-api/auth/send-otp/", views.send_otp_api_view, name="api-auth-send-otp"),
    path("frontend-api/auth/verify-otp/", views.verify_otp_api_view, name="api-auth-verify-otp"),
    path("frontend-api/users/search/", views.user_search_api_view, name="api-users-search"),
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
    # Profile/me endpoints must be declared BEFORE the generic `profile/<profile_id>/` regex
    # at the bottom, since Django URL resolution walks in order.
    path("frontend-api/profile/me/", views.my_profile_api_view, name="api-profile-me"),
    path("frontend-api/profile/me/followers/", views.profile_followers_api_view, name="api-profile-followers"),
    path("frontend-api/profile/me/following/", views.profile_following_api_view, name="api-profile-following"),
    path("frontend-api/bookmarks/", views.bookmarks_api_view, name="api-bookmarks"),
    path("frontend-api/bookmarks/<int:trip_id>/", views.bookmark_trip_api_view, name="api-bookmark-trip"),
    path("frontend-api/activity/", views.activity_api_view, name="api-activity"),
    path("frontend-api/settings/", views.settings_api_view, name="api-settings"),
    path("frontend-api/hosting-inbox/", views.hosting_inbox_api_view, name="api-hosting-inbox"),
    path("frontend-api/dm/inbox/", views.dm_inbox_api_view, name="api-dm-inbox"),
    path("frontend-api/dm/threads/<int:thread_id>/", views.dm_thread_api_view, name="api-dm-thread"),
    path("frontend-api/dm/inbox/<int:thread_id>/messages/", views.dm_send_message_api_view, name="api-dm-send-message"),
    path("frontend-api/trips/<int:trip_id>/join-request/", views.trip_join_request_api_view, name="api-trip-join-request"),
    path("frontend-api/trips/<int:trip_id>/duplicate/", views.trip_duplicate_api_view, name="api-trip-duplicate"),
    path("frontend-api/manage-trip/<int:trip_id>/", views.manage_trip_api_view, name="api-manage-trip"),
    path("frontend-api/manage-trip/<int:trip_id>/booking-status/", views.manage_trip_booking_status_view, name="api-manage-trip-booking-status"),
    re_path(r"^frontend-api/manage-trip/(?P<trip_id>\d+)/participants/(?P<participant_id>\d+)/remove/$", views.manage_trip_remove_participant_view, name="api-manage-trip-remove-participant"),
    path("frontend-api/manage-trip/<int:trip_id>/cancel/", views.manage_trip_cancel_view, name="api-manage-trip-cancel"),
    path("frontend-api/manage-trip/<int:trip_id>/message/", views.manage_trip_message_view, name="api-manage-trip-message"),
    path("frontend-api/trips/<int:trip_id>/review/", views.trip_review_create_api_view, name="api-trip-review-create"),
    path("frontend-api/account/deactivate/", views.account_deactivate_api_view, name="api-account-deactivate"),
    path("frontend-api/account/delete/", views.account_delete_api_view, name="api-account-delete"),
    path(
        "frontend-api/hosting-requests/<int:request_id>/decision/",
        views.hosting_decision_api_view,
        name="api-hosting-decision",
    ),
    path("frontend-api/trips/<int:trip_id>/reviews/", views.trip_review_submit_api_view, name="api-trip-review-submit"),
    path("frontend-api/reviews/", views.reviews_list_api_view, name="api-reviews-list"),
    path("frontend-api/dm/start/", views.dm_start_thread_api_view, name="api-dm-start-thread"),
    re_path(r"^frontend-api/profile/(?P<profile_id>[^/]+)/follow/$", views.profile_follow_api_view, name="api-profile-follow"),
    re_path(r"^frontend-api/profile/(?P<profile_id>[^/]+)/$", views.profile_detail_api_view, name="api-profile-detail"),
    path("frontend-api/notifications/", views.notifications_api_view, name="api-notifications"),
    path("frontend-api/auth/google/start/", views.google_oauth_start_view, name="api-google-oauth-start"),
    path("frontend-api/auth/google/callback/", views.google_oauth_callback_view, name="api-google-oauth-callback"),
    re_path(r"^assets/(?P<asset_path>.+)$", views.frontend_asset_view, name="asset"),
    re_path(
        r"^(?P<artifact_name>(?:favicon\.ico|placeholder\.svg|manifest\.webmanifest|site\.webmanifest))$",
        views.frontend_root_artifact_view,
        name="root-artifact",
    ),
]

# SPA entrypoint URLs. These render the Lovable shell via frontend_entrypoint_view
# and must mirror the planned client routes declared in lovable/src/App.tsx.
# A global catch-all in tapne/urls.py serves the same shell for any unmatched URL,
# but the explicit entries here keep the planned-vs-deployed audit honest
# (see RULES.md Section 6 drift rules). Static sub-paths must come BEFORE
# any sibling regex that would also match them.
urlpatterns.extend(
    [
        # ── Home ──────────────────────────────────────────────────────────────
        path("", views.frontend_entrypoint_view, name="entrypoint-home"),

            # ── Trips ─────────────────────────────────────────────────────────────
            path("trips", views.frontend_entrypoint_view, name="entrypoint-trips"),
            path("trips/", views.frontend_entrypoint_view),
            path("trips/new", views.frontend_entrypoint_view, name="entrypoint-trip-new"),
            path("trips/new/", views.frontend_entrypoint_view),
            re_path(r"^trips/(?P<trip_id>\d+)/edit/?$", views.frontend_entrypoint_view, name="entrypoint-trip-edit"),
            re_path(r"^trips/(?P<trip_id>\d+)/?$", views.frontend_entrypoint_view, name="entrypoint-trip-detail"),

            # ── Stories ───────────────────────────────────────────────────────────
            path("stories", views.frontend_entrypoint_view, name="entrypoint-stories"),
            path("stories/", views.frontend_entrypoint_view),
            path("stories/new", views.frontend_entrypoint_view, name="entrypoint-story-new"),
            path("stories/new/", views.frontend_entrypoint_view),
            re_path(
                r"^stories/(?P<story_id>(?!new$)[-a-zA-Z0-9_]+)/edit/?$",
                views.frontend_entrypoint_view,
                name="entrypoint-story-edit",
            ),
            re_path(
                r"^stories/(?P<story_id>(?!new$)[-a-zA-Z0-9_]+)/?$",
                views.frontend_entrypoint_view,
                name="entrypoint-story-detail",
            ),

            # ── Profile / Users ───────────────────────────────────────────────────
            path("profile", views.frontend_entrypoint_view, name="entrypoint-profile"),
            path("profile/", views.frontend_entrypoint_view),
            path("profile/edit", views.frontend_entrypoint_view, name="entrypoint-profile-edit"),
            path("profile/edit/", views.frontend_entrypoint_view),
            re_path(r"^users/(?P<profile_id>[^/]+)/?$", views.frontend_entrypoint_view, name="entrypoint-users-detail"),

            # ── Messaging & utility ───────────────────────────────────────────────
            path("messages", views.frontend_entrypoint_view, name="entrypoint-messages"),
            path("messages/", views.frontend_entrypoint_view),
            path("bookmarks", views.frontend_entrypoint_view, name="entrypoint-bookmarks"),
            path("bookmarks/", views.frontend_entrypoint_view),
            path("search", views.frontend_entrypoint_view, name="entrypoint-search"),
            path("search/", views.frontend_entrypoint_view),
            path("notifications", views.frontend_entrypoint_view, name="entrypoint-notifications"),
            path("notifications/", views.frontend_entrypoint_view),
            path("settings", views.frontend_entrypoint_view, name="entrypoint-settings"),
            path("settings/", views.frontend_entrypoint_view),

            # ── Dashboard ─────────────────────────────────────────────────────────
            path("dashboard", views.frontend_entrypoint_view, name="entrypoint-dashboard"),
            path("dashboard/", views.frontend_entrypoint_view),
            path("dashboard/trips", views.frontend_entrypoint_view, name="entrypoint-dashboard-trips"),
            path("dashboard/trips/", views.frontend_entrypoint_view),
            path("dashboard/stories", views.frontend_entrypoint_view, name="entrypoint-dashboard-stories"),
            path("dashboard/stories/", views.frontend_entrypoint_view),
            path("dashboard/reviews", views.frontend_entrypoint_view, name="entrypoint-dashboard-reviews"),
            path("dashboard/reviews/", views.frontend_entrypoint_view),
            path("dashboard/subscriptions", views.frontend_entrypoint_view, name="entrypoint-dashboard-subscriptions"),
            path("dashboard/subscriptions/", views.frontend_entrypoint_view),
        ]
    )
