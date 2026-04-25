# Baseline Reference

This file preserves the original reference material while moving it out of the
main operator runbook.

These tables are reference only. They are not authoritative. Always regenerate
the live inventory from current source first, then diff against this file.

## Key File Map

| Purpose | Path |
|---|---|
| Parent cutover contract | `skills/lovable-django-production-cutover/SKILL.md` |
| Lovable route source | `lovable/src/App.tsx` |
| Production route source | `frontend_spa/src/App.tsx` |
| Runtime config + API types | `lovable/src/types/api.ts` |
| Messaging types | `lovable/src/types/messaging.ts` |
| API client + CSRF behavior | `lovable/src/lib/api.ts` |
| Auth flows | `lovable/src/contexts/AuthContext.tsx` |
| Draft flows | `lovable/src/contexts/DraftContext.tsx` |
| Django runtime config + JSON views | `frontend/views.py` |
| Django route map | `frontend/urls.py` |
| Production build script | `infra/build-lovable-production-frontend.ps1` |
| Existing browser-workflow reference | `.github/workflows/visual-audit-pr-guardrail.yml` |
| Existing storage-state script reference | `skills/webpage-visual-perfection-audit/scripts/create_storage_state.py` |
| Seed commands | `accounts/management/commands/bootstrap_accounts.py` and sibling `bootstrap_*` commands |
| Test output root | `artifacts/` |

## Current Route Baseline (April 2026 — post-SPA-rebuild)

| Route | Lovable component | Notes |
|---|---|---|
| `/` | `Index` | |
| `/trips` | `BrowseTrips` | |
| `/trips/new` | `CreateTrip` | replaces retired `/create-trip` |
| `/trips/:tripId/edit` | `CreateTrip` | |
| `/trips/:tripId` | `TripDetail` | host sees ApplicationManager here |
| `/stories` | `Stories` | replaces retired `/experiences` and `/blogs` |
| `/stories/new` | `StoryCreate` | replaces retired `/experiences/create` |
| `/stories/:storyId/edit` | `StoryEdit` | replaces retired `/experiences/edit?slug=` |
| `/stories/:storyId` | `StoryDetail` | replaces retired `/experiences/:slug` |
| `/profile` | `Profile` | own profile |
| `/profile/edit` | `ProfileEdit` | |
| `/users/:profileId` | `Profile` | replaces retired `/profile/:userId` |
| `/messages` | `Messages` | replaces retired `/inbox`; h2 still reads "Inbox" |
| `/bookmarks` | `Bookmarks` | |
| `/search` | `Search` | |
| `/notifications` | `Notifications` | |
| `/settings` | `Settings` | |
| `/dashboard` | `Dashboard` (nested) | replaces retired `/my-trips` |
| `/dashboard/trips` | `DashboardTrips` | Joined + Managed tabs |
| `/dashboard/stories` | `DashboardStories` | |
| `/dashboard/reviews` | `DashboardReviews` | |
| `/dashboard/subscriptions` | `DashboardSubscriptions` | |
| `*` | `UnderConstructionPage` | production catch-all |

### Retired routes (do not add back to frontend/urls.py)

`/create-trip`, `/my-trips`, `/manage-trip/:id`, `/inbox`, `/experiences/*`,
`/blogs`, `/travel-hosts`, `/login` (modal only), `/signup` (modal only),
`/profile/:userId` (replaced by `/users/:profileId`)

## Current Minimum Flow Baseline (April 2026)

| Flow id | Route | Primary action | Coverage tier |
|---|---|---|---|
| `guest_home_shell` | `/` | initial render | `automated_smoke` |
| `guest_trip_catalog` | `/trips` | list render with live data | `automated_smoke` |
| `guest_trip_detail` | `/trips/:id` | detail render with live data | `automated_smoke` |
| `auth_navbar_modal_login_then_post` | `/` → modal | login via navbar modal, POST DM | `automated_smoke` |
| `draft_create_publish` | `/trips/new` → `/dashboard/trips` | create, save, publish trip | `automated_smoke` |
| `modal_login_booking_post` | `/trips/:id` → modal | modal login then book | `automated_full` |
| `signup_modal` | `/` → modal signup | create isolated account | `automated_full` |
| `story_create_edit` | `/stories/new` → `/stories/:slug/edit` | create and edit story | `automated_full` |
| `story_delete` | `/stories/:slug` | delete story button | `automated_full` |
| `inbox_send_message` | `/messages` | send DM | `automated_smoke` (via login test) |
| `trip_detail_dm_start` | `/trips/:id` → `/messages?thread=` | Ask a Question → thread | `automated_full` |
| `manage_trip_application_approve` | `/trips/:id` ApplicationManager | approve pending application | `automated_full` |
| `manage_trip_booking_status` | `/trips/:id` Host Controls | Close / Reopen Bookings | `automated_full` |
| `manage_trip_cancel` | `/trips/:id` Host Controls | Cancel Trip dialog | `automated_full` |
| `manage_trip_remove_participant` | `/trips/:id` ApplicationManager | Remove Participant confirm | `automated_full` |
| `manage_trip_message_all` | `/trips/:id` ApplicationManager | Message All dialog | `automated_full` |
| `bookmark_toggle` | `/trips/:id` | save / unsave trip | `automated_full` |
| `profile_follow_toggle` | `/users/:profileId` | follow / unfollow | `automated_full` |
| `trip_review_submit` | `/trips/:id` review modal | submit review | `automated_full` |

## Known cfg.api.base Interpolations (RULES.md §3 invariant)

These bypass named api keys.  `api.base = "/frontend-api"` so they resolve
correctly today, but any rename of the base path would silently break them.
Fix path is a Lovable prompt (Scope 1).

| File | Usage |
|---|---|
| `lovable/src/pages/Profile.tsx:118` | `${cfg.api.base}/profile/${profileId}/` |
| `lovable/src/pages/Profile.tsx:340` | `${cfg.api.base}/profile/${p.username}/follow/` |
| `lovable/src/components/ApplicationManager.tsx:57` | `${cfg.api.base}/hosting-requests/${reqId}/decision/` |
| `lovable/src/components/ApplicationManager.tsx:70` | `${cfg.api.base}/trips/${tripId}/participants/${uid}/remove/` |
| `lovable/src/components/ApplicationManager.tsx:87` | `${cfg.api.base}/trips/${tripId}/broadcast/` |
| `lovable/src/pages/TripDetail.tsx:620` | `${cfg.api.base}/trips/${trip.id}/booking-status/` |
| `lovable/src/pages/TripDetail.tsx:738` | `${cfg.api.base}/trips/${trip.id}/cancel/` |
| `lovable/src/pages/dashboard/DashboardSubscriptions.tsx:50-51` | `${cfg.api.base}/profile/me/followers/` and `.../following/` |

## Baseline Data Sources For Seeded Flows

| Flow family | Bootstrap command(s) |
|---|---|
| auth/session | `bootstrap_accounts` |
| home/trips | `bootstrap_feed`, `bootstrap_trips` |
| blogs/stories | `bootstrap_blogs` |
| bookmarks/follows/profile | `bootstrap_social` |
| host inbox/manage trip | `bootstrap_enrollment` |
| DMs/inbox | `bootstrap_interactions` |
| reviews/activity | `bootstrap_reviews`, `bootstrap_activity` |
| settings/runtime/media | `bootstrap_settings`, `bootstrap_runtime`, `bootstrap_media` |

## Baseline CI Shape

| Lane | Command | Purpose |
|---|---|---|
| PR smoke | `pytest -m smoke tests/e2e` | fast guardrail for core user journeys |
| Manual/full | `pytest tests/e2e` | broader regression sweep |
