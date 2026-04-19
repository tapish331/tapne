# Baseline Reference

This file preserves the original reference material. The operational intent has
not changed.

These tables are reference only. They are not authoritative. Always regenerate
the live inventory from the current source first, then diff against this file.

## Key File Map

| Purpose | Path |
|---|---|
| Lovable source router | `lovable/src/App.tsx` |
| TypeScript API contracts | `lovable/src/types/api.ts` |
| Messaging contracts | `lovable/src/types/messaging.ts` |
| Dev mode detection | `lovable/src/lib/mode.ts` |
| API client | `lovable/src/lib/api.ts` |
| Mock request handler | `lovable/src/lib/devMock.ts` |
| Mock data fixtures | `lovable/src/data/mockData.ts` |
| Bootstrap entry | `lovable/src/main.tsx` |
| Auth and session API calls | `lovable/src/contexts/AuthContext.tsx` |
| Trip draft API calls | `lovable/src/contexts/DraftContext.tsx` |
| Production router | `frontend_spa/src/App.tsx` |
| Production API client | `frontend_spa/src/lib/api.ts` |
| Runtime config types | `frontend_spa/src/lib/config.ts` |
| Mock bypass stub | `frontend_spa/src/lib/devMockStub.ts` |
| Mock data stub | `frontend_spa/src/data/mockDataStub.ts` |
| External Vite config | `frontend_spa/vite.production.config.ts` |
| Build script | `infra/build-lovable-production-frontend.ps1` |
| Django URL routing | `frontend/urls.py` |
| Django views and runtime config injection | `frontend/views.py` |
| Root URL conf | `tapne/urls.py` |
| Feature flags | `tapne/settings.py` |
| Built artifact | `artifacts/lovable-production-dist/` |

## Routes (April 2026 Baseline)

| Route path | Component |
|---|---|
| `/` | `Index` |
| `/trips` | `BrowseTrips` |
| `/trips/:id` | `TripDetail` |
| `/create-trip` | `CreateTrip` |
| `/my-trips` | `MyTrips` |
| `/experiences` | `Experiences` |
| `/experiences/create` | `ExperienceCreate` |
| `/experiences/edit` | `ExperienceEdit` |
| `/experiences/:slug` | `ExperienceDetail` |
| `/blogs` | `Experiences` (alias) |
| `/travelers` | `Travelers` |
| `/bookmarks` | `Bookmarks` |
| `/inbox` | `Inbox` |
| `/manage-trip/:id` | `ManageTrip` |
| `/login` | `Login` |
| `/signup` | `SignUp` |
| `/profile` | `Profile` |
| `/profile/:userId` | `Profile` |
| `*` | `NotFound` / `UnderConstructionPage` |

## TapneRuntimeConfig.api Keys (April 2026 Baseline)

| Key | Django endpoint | Primary HTTP methods | Notes |
|---|---|---|---|
| `base` | `/frontend-api` | - | URL prefix, not a direct endpoint |
| `session` | `/frontend-api/session/` | GET | Bootstrap session check |
| `login` | `/frontend-api/auth/login/` | POST | `{ email, password }` |
| `signup` | `/frontend-api/auth/signup/` | POST | `{ first_name, email, password }` |
| `logout` | `/frontend-api/auth/logout/` | POST | |
| `home` | `/frontend-api/home/` | GET | Returns `HomeResponse` |
| `trips` | `/frontend-api/trips/` | GET, GET `/{id}/`, POST `/{id}/join-request/`, POST `/{id}/duplicate/` | |
| `blogs` | `/frontend-api/blogs/` | GET, GET `/{slug}/`, POST, PATCH `/{slug}/`, DELETE `/{slug}/` | |
| `my_trips` | `/frontend-api/my-trips/` | GET | Returns `MyTripsResponse` |
| `trip_drafts` | `/frontend-api/trips/drafts/` | POST, GET/PATCH `/{id}/`, DELETE `/{id}/`, POST `/{id}/publish/` | |
| `profile_me` | `/frontend-api/profile/me/` | GET, PATCH | Own profile |
| `bookmarks` | `/frontend-api/bookmarks/` | GET, POST `/{trip_id}/`, DELETE `/{trip_id}/` | |
| `activity` | `/frontend-api/activity/` | GET | |
| `settings` | `/frontend-api/settings/` | GET | |
| `hosting_inbox` | `/frontend-api/hosting-inbox/` | GET | `?status=all` supported |
| `dm_inbox` | `/frontend-api/dm/inbox/` | GET, GET/POST via threads | also `GET /dm/threads/{id}/`, `POST /dm/inbox/{id}/messages/` |
| `manage_trip` | `/frontend-api/manage-trip/` | GET `/{id}/`, POST `/{id}/booking-status/`, POST `/{id}/participants/{p}/remove/`, POST `/{id}/cancel/`, POST `/{id}/message/` | URL prefix only |
| `messages` | `/frontend-api/messages/` | - | Deferred - not yet called by any page |
| `trip_chat` | `/frontend-api/trip-chat/` | - | Deferred - not yet called by any page |
| `users_search` | `/frontend-api/users/search/` | GET | User autocomplete search |
| `notifications` | `/frontend-api/notifications/` | GET | Navbar notification badge fetch, gated on `isAuthenticated` |
| `trip_reviews` | `/frontend-api/trips/` | POST `/{id}/reviews/` | Base prefix |
| `dm_start` | `/frontend-api/dm/start/` | POST | `{ host_username } -> { ok, thread_id }` |

### Additional `cfg.api.base` Patterns

| URL shape | HTTP | Used in | Django view | Notes |
|---|---|---|---|---|
| `/frontend-api/profile/{id}/` | GET | `Profile.tsx` | `profile_detail_api_view` | username or numeric id |
| `/frontend-api/profile/{username}/follow/` | POST, DELETE | `Profile.tsx` | `profile_follow_api_view` | follow/unfollow |
| `/frontend-api/hosting-requests/{id}/decision/` | POST | `ManageTrip.tsx`, `ApplicationManager.tsx` | `hosting_decision_api_view` | `{ decision }` |

These `cfg.api.base` URLs are easy to miss because they are not named api keys.

## Django URL -> View Map (April 2026 Baseline)

| URL pattern | View |
|---|---|
| `GET /frontend-api/session/` | `session_api_view` |
| `POST /frontend-api/auth/login/` | `auth_login_api_view` |
| `POST /frontend-api/auth/signup/` | `auth_signup_api_view` |
| `POST /frontend-api/auth/logout/` | `auth_logout_api_view` |
| `GET /frontend-api/home/` | `home_api_view` |
| `GET,POST /frontend-api/trips/` | `trip_list_api_view` |
| `GET /frontend-api/trips/{trip_id}/` | `trip_detail_api_view` |
| `POST /frontend-api/trips/drafts/` | `trip_draft_create_api_view` |
| `GET,PATCH /frontend-api/trips/drafts/{trip_id}/` | `trip_draft_detail_api_view` |
| `POST /frontend-api/trips/drafts/{trip_id}/publish/` | `trip_draft_publish_api_view` |
| `GET /frontend-api/my-trips/` | `my_trips_api_view` |
| `GET,POST /frontend-api/blogs/` | `blog_list_api_view` |
| `GET,PATCH,DELETE /frontend-api/blogs/{slug}/` | `blog_detail_api_view` |
| `GET,PATCH /frontend-api/profile/me/` | `my_profile_api_view` |
| `GET /frontend-api/bookmarks/` | `bookmarks_api_view` |
| `POST,DELETE /frontend-api/bookmarks/{trip_id}/` | `bookmark_trip_api_view` |
| `GET /frontend-api/activity/` | `activity_api_view` |
| `GET /frontend-api/settings/` | `settings_api_view` |
| `GET /frontend-api/hosting-inbox/` | `hosting_inbox_api_view` |
| `GET /frontend-api/dm/inbox/` | `dm_inbox_api_view` |
| `GET /frontend-api/dm/threads/{thread_id}/` | `dm_thread_api_view` |
| `POST /frontend-api/dm/inbox/{thread_id}/messages/` | `dm_send_message_api_view` |
| `POST /frontend-api/trips/{trip_id}/join-request/` | `trip_join_request_api_view` |
| `POST /frontend-api/trips/{trip_id}/duplicate/` | `trip_duplicate_api_view` |
| `GET /frontend-api/manage-trip/{trip_id}/` | `manage_trip_api_view` |
| `POST /frontend-api/manage-trip/{trip_id}/booking-status/` | `manage_trip_booking_status_view` |
| `POST /frontend-api/manage-trip/{trip_id}/participants/{participant_id}/remove/` | `manage_trip_remove_participant_view` |
| `POST /frontend-api/manage-trip/{trip_id}/cancel/` | `manage_trip_cancel_view` |
| `POST /frontend-api/manage-trip/{trip_id}/message/` | `manage_trip_message_view` |
| `POST /frontend-api/hosting-requests/{request_id}/decision/` | `hosting_decision_api_view` |
| `GET /frontend-api/profile/{profile_id}/` | `profile_detail_api_view` |
| `GET /frontend-api/users/search/` | `users_search_api_view` |
| `POST /frontend-api/trips/{trip_id}/reviews/` | `trip_review_submit_api_view` |
| `POST /frontend-api/dm/start/` | `dm_start_thread_api_view` |
| `GET /frontend-api/notifications/` | `notifications_api_view` |
| `POST,DELETE /frontend-api/profile/{profile_id}/follow/` | `profile_follow_api_view` |

### SPA Entrypoint Routes

| URL pattern | Named route |
|---|---|
| `GET /` | `entrypoint-home` |
| `GET /trips` | `entrypoint-trips` |
| `GET /trips/{trip_id}` | `entrypoint-trip-detail` |
| `GET /trips/{trip_id}/edit` | `entrypoint-trip-edit` |
| `GET /trips/create/` | `entrypoint-trip-create` |
| `GET /trips/mine/` | `entrypoint-trip-mine` |
| `GET /create-trip` | `entrypoint-create-trip` |
| `GET /my-trips` | `entrypoint-my-trips` |
| `GET /experiences` | `entrypoint-experiences` |
| `GET /experiences/create` | `entrypoint-experience-create` |
| `GET /experiences/:slug` | `entrypoint-experience-detail` |
| `GET /blogs` | `entrypoint-blogs` |
| `GET /travelers` | `entrypoint-travelers` |
| `GET /bookmarks` | `entrypoint-bookmarks-spa` |
| `GET /inbox` | `entrypoint-inbox` |
| `GET /manage-trip/:id` | `entrypoint-manage-trip` |
| `GET /login` | `entrypoint-login` |
| `GET /signup` | `entrypoint-signup` |
| `GET /profile` | `entrypoint-profile` |
| `GET /profile/:userId` | `entrypoint-profile-detail` |
| `GET /accounts/login/` | `entrypoint-accounts-login` |
| `GET /accounts/signup/` | `entrypoint-accounts-signup` |
| `GET /accounts/me/` | `entrypoint-accounts-me` |
| `re_path r"^.*$"` | `spa-catchall` |

## Mock Patterns (April 2026 Baseline)

| Mock pattern in `devMock.ts` | Django replacement |
|---|---|
| `GET /__devmock__/session/` | `session_api_view` -> `SessionResponse` |
| `POST /__devmock__/auth/login/` | `auth_login_api_view` |
| `POST /__devmock__/auth/signup/` | `auth_signup_api_view` |
| `GET /__devmock__/home/` | `home_api_view` |
| `GET /__devmock__/trips/` | `trip_list_api_view` |
| `GET /__devmock__/trips/{id}/` | `trip_detail_api_view` |
| `POST /__devmock__/trips/drafts/` | `trip_draft_create_api_view` |
| `GET,PATCH /__devmock__/trip-drafts/{id}/` | `trip_draft_detail_api_view` |
| `POST /__devmock__/trip-drafts/{id}/publish/` | `trip_draft_publish_api_view` |
| `GET /__devmock__/my-trips/` | `my_trips_api_view` |
| `GET /__devmock__/blogs/` | `blog_list_api_view` |
| `GET,POST,PATCH,DELETE /__devmock__/blogs/{slug}/` | `blog_detail_api_view` |
| `GET,PATCH /__devmock__/accounts/me/` | `my_profile_api_view` |
| `GET /__devmock__/bookmarks/` | `bookmarks_api_view` |
| `POST,DELETE /__devmock__/bookmarks/{id}/` | `bookmark_trip_api_view` |
| `GET /__devmock__/activity/` | `activity_api_view` |
| `GET /__devmock__/settings/` | `settings_api_view` |
| `GET /__devmock__/hosting/inbox/` | `hosting_inbox_api_view` |
| `GET /__devmock__/dm/inbox/` | `dm_inbox_api_view` |
| `POST /__devmock__/dm/inbox/{id}/messages/` | `dm_send_message_api_view` |
| `GET,POST /__devmock__/manage-trip/{id}/` | `manage_trip_api_view` and action views |
| `POST /__devmock__/hosting-requests/{id}/decision/` | `hosting_decision_api_view` |
| `mockData.ts` trip fixtures | Django trip payload builders |
| `mockData.ts` user fixtures | `User` + `AccountProfile` payloads |
| `IS_DEV_MODE = window.TAPNE_RUNTIME_CONFIG === undefined` | production always injects runtime config |

## Known Hardcoded Mock Or Placeholder Patterns

| Location | Hardcoded value | Required fix |
|---|---|---|
| `Navbar.tsx` | fake notifications array | Lovable prompt: fetch from `cfg.api.notifications` |
| `LoginModal.tsx` | fake Google credentials | Lovable prompt: use `cfg.google_oauth_url` or hide the button |
| `HeroSection.tsx` | fallback stats strings | Django fix: always return `stats` |
| `CreateTrip.tsx handleSaveDraft` | success toast when `draftId == null` | Lovable prompt: guard toast |
| `CreateTrip.tsx handleSubmit` | navigate to `/login` instead of `requireAuth()` | Lovable prompt: replace with modal auth path |
| `CreateTrip.tsx handleSubmit` | success toast after null draft publish path | Lovable prompt: guard publish before toast |

If the issue is Django-fixable, fix it in Django. If it is truly frontend-only and user-visible, include it in the single Lovable prompt.

## Key TypeScript Interfaces To Verify Against Django

Tapne uses snake_case throughout. Django responses must match the TypeScript field names exactly.

| TypeScript interface | Source file | Django view / builder | Critical nested fields |
|---|---|---|---|
| `SessionUser` | `api.ts` | `_session_user_payload()` | - |
| `SessionResponse` | `api.ts` | `session_api_view` | - |
| `TripData` | `api.ts` | `Trip.to_trip_data()` and enrichers | `highlights`, `itinerary_days`, `faqs` |
| `TripDetailResponse` | `api.ts` | `trip_detail_api_view` | `similar_trips[]` |
| `TripListResponse` | `api.ts` | `trip_list_api_view` | `trips[]` |
| `MyTripsResponse` | `api.ts` | `my_trips_api_view` | `trips[]` |
| `ManageTripResponse` | `api.ts` | `manage_trip_api_view` | `participants[]`, `applications[]` |
| `BlogData` | `api.ts` | blog views | `tags[]` |
| `HomeResponse` | `api.ts` | `home_api_view` | `community_profiles[]`, `testimonials[]`, `stats` |
| `EnrollmentRequestData` | `api.ts` | `hosting_inbox_api_view` | - |
| `TapneRuntimeConfig` | `api.ts` | `_runtime_config_payload()` | every `api{}` key |
| `ProfileResponse` | `Profile.tsx` | `profile_detail_api_view` | `profile{}`, `trips_hosted[]`, `trips_joined[]`, `reviews[]`, `gallery[]` |
| `CommunityProfile` | `api.ts` | `home_api_view` | `username`, `display_name`, `bio`, `location` |
| `InboxResponse` | `messaging.ts` | `dm_inbox_api_view` | `threads[]` |
| `ThreadData` | `messaging.ts` | `dm_inbox_api_view` | `participants[]`, `messages[]` |
| `MessageData` | `messaging.ts` | `dm_inbox_api_view` loop | `id`, `thread_id`, `sender_username`, `sender_display_name`, `body`, `sent_at` |

Warnings:

- `messaging.ts` is authoritative for inbox/thread/message shapes. Do not audit only `api.ts`.
- Django `DMThreadPreviewData` is not the same shape as TypeScript `ThreadData`. Build the frontend response explicitly.
