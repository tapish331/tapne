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

## Current Route Baseline (April 2026)

| Route | Lovable component |
|---|---|
| `/` | `Index` |
| `/trips` | `BrowseTrips` |
| `/trips/preview` | `TripPreview` |
| `/trips/:id` | `TripDetail` |
| `/create-trip` | `CreateTrip` |
| `/my-trips` | `MyTrips` |
| `/experiences` | `Experiences` |
| `/experiences/create` | `ExperienceCreate` |
| `/experiences/edit` | `ExperienceEdit` |
| `/experiences/:slug` | `ExperienceDetail` |
| `/blogs` | `Experiences` |
| `/travel-hosts` | `TravelHosts` |
| `/bookmarks` | `Bookmarks` |
| `/inbox` | `Inbox` |
| `/manage-trip/:id` | `ManageTrip` |
| `/login` | `Login` |
| `/signup` | `SignUp` |
| `/profile` | `Profile` |
| `/profile/:userId` | `Profile` |
| `*` | `NotFound` / `UnderConstructionPage` |

## Current Minimum Flow Baseline (April 2026)

| Flow id | Route | Primary action | Expected automation tier |
|---|---|---|---|
| `guest_home_shell` | `/` | initial render | `automated_smoke` |
| `guest_trip_catalog` | `/trips` | list render with live data | `automated_smoke` |
| `guest_trip_detail` | `/trips/:id` | detail render with live data | `automated_smoke` or `automated_full` |
| `auth_login_then_post` | `/login` or login modal | authenticate, then perform immediate POST | `automated_smoke` |
| `draft_create_publish` | `/create-trip` | create, save, publish draft | `automated_smoke` |
| `my_trips_reload_persistence` | `/my-trips` | verify published or duplicated trip survives reload | `automated_smoke` or `automated_full` |
| `inbox_send_message` | `/inbox` | send DM message | `automated_full`, often `automated_smoke` if stable |
| `trip_detail_dm_start` | `/trips/:id` | start DM and land on inbox thread | `automated_full` |
| `manage_trip_status_change` | `/manage-trip/:id` | booking status mutation | `automated_full`, or `automated_smoke` if this is the main host flow |
| `hosting_request_decision` | `/manage-trip/:id` or hosting inbox UI | approve or deny request | `automated_full` |
| `bookmark_toggle` | `/trips/:id` or `/bookmarks` | save or unsave trip | `automated_full` |
| `profile_follow_toggle` | `/profile/:userId` | follow or unfollow | `automated_full` |
| `experience_create_edit` | `/experiences/create` and `/experiences/:slug` | create or edit experience | `automated_full` |

## Baseline Data Sources For Seeded Flows

| Flow family | Bootstrap command(s) |
|---|---|
| auth/session | `bootstrap_accounts` |
| home/trips | `bootstrap_feed`, `bootstrap_trips` |
| blogs/experiences | `bootstrap_blogs` |
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
