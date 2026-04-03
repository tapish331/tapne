# Current-State Audit

Use this file to ground the cutover plan in the repo as it exists now.

## 1. Current production serving model

- `tapnetravel.com` is deployed through the Django/Cloud Run pipeline:
  - [infra/run-cloud-run-workflow.ps1](e:/tapne/infra/run-cloud-run-workflow.ps1)
  - [infra/Dockerfile.web](e:/tapne/infra/Dockerfile.web)
- That pipeline now supports both serving modes:
  - Django-rendered public pages when `LOVABLE_FRONTEND_ENABLED=false`
  - Lovable SPA shell served through Django when `LOVABLE_FRONTEND_ENABLED=true`

Implication:

- do not assume the live site is still in an older pre-cutover mode
- inspect current settings, deployed shell behavior, and live verification output on every invocation

## 2. Lovable production blockers — RESOLVED

The former production blockers have been resolved through the external override build layer and the dual-mode architecture. This section documents what was fixed and how.

### Auth — RESOLVED

- [lovable/src/contexts/AuthContext.tsx](e:/tapne/lovable/src/contexts/AuthContext.tsx)

Current behavior (production / Django mode):

- On mount, hydrates user state from `window.TAPNE_RUNTIME_CONFIG.session` (Django-injected).
- Calls `GET cfg.api.session` to verify/refresh the Django session.
- Login, signup, logout, and profile updates all call real Django endpoints via `cfg.api.*`.
- No mock fallback in production.

Dev mode behavior (Lovable editor):

- `mode.ts` injects a dev runtime config; `IS_DEV_MODE = true`.
- Login accepts any credentials and sets the first mock user (`devMock.ts`).
- Session state is in-memory and resets on page reload (expected in Lovable dev).

### Drafts — RESOLVED

- [lovable/src/contexts/DraftContext.tsx](e:/tapne/lovable/src/contexts/DraftContext.tsx)

Current behavior (production / Django mode):

- Loads drafts from `GET cfg.api.my_trips` on mount (when session is authenticated).
- Create/update/delete/publish all route to `cfg.api.trip_drafts` via real Django API calls.
- No `localStorage` involvement.

Dev mode behavior:

- `devMock.ts` handles all trip draft operations in-memory.
- Drafts persist for the session but reset on page reload.

### Core catalogs and detail pages — RESOLVED

All pages now fetch data through `lovable/src/lib/api.ts` using `cfg.api.*` URLs:

- [lovable/src/pages/Index.tsx](e:/tapne/lovable/src/pages/Index.tsx) — `GET cfg.api.home`
- [lovable/src/pages/BrowseTrips.tsx](e:/tapne/lovable/src/pages/BrowseTrips.tsx) — `GET cfg.api.trips`
- [lovable/src/pages/TripDetail.tsx](e:/tapne/lovable/src/pages/TripDetail.tsx) — `GET cfg.api.trips + id`
- [lovable/src/pages/MyTrips.tsx](e:/tapne/lovable/src/pages/MyTrips.tsx) — `GET cfg.api.my_trips`
- [lovable/src/pages/Profile.tsx](e:/tapne/lovable/src/pages/Profile.tsx) — `GET cfg.api.my_trips`
- [lovable/src/pages/Blogs.tsx](e:/tapne/lovable/src/pages/Blogs.tsx) — `GET cfg.api.blogs`

`lovable/src/data/mockData.ts` is no longer imported by any page or component. It is only used by `lovable/src/lib/devMock.ts` for Lovable dev mode. The production Vite build aliases `@/lib/devMock` to a no-op stub, so `mockData.ts` is excluded from the production bundle entirely.

### Route shell — RESOLVED

- Django serves the SPA shell for all browser-navigable URLs via `frontend_entrypoint_view`.
- The override `frontend_spa/src/App.tsx` uses `createBrowserRouter` (not `BrowserRouter`), imports all user-facing pages from `@/pages/*` (real Lovable source), and preserves the full provider tree from `lovable/src/App.tsx`.
- The `*` catch-all points to `UnderConstructionPage` (styled, uses Lovable Navbar/Footer/tokens).
- Explicit `re_path` patterns in `frontend/urls.py` cover all parameterised Django routes before app-specific `urls.py` files can intercept them.

## 2b. Dual-mode architecture

Lovable now has a built-in dual-mode system that does not require any manual switching:

| Signal | Mode | Behavior |
|---|---|---|
| `window.TAPNE_RUNTIME_CONFIG` is **absent** at page load | Lovable dev mode | `mode.ts` injects mock config, `IS_DEV_MODE = true`, all API calls return mock data from `devMock.ts` |
| `window.TAPNE_RUNTIME_CONFIG` is **present** at page load (Django-injected) | Django production mode | `IS_DEV_MODE = false`, all API calls hit real Django endpoints |

Files that implement the dual-mode system (must not be overwritten by Lovable):

| File | Role |
|---|---|
| [lovable/src/main.tsx](e:/tapne/lovable/src/main.tsx) | First import is `import "@/lib/mode"` — must run before any component |
| [lovable/src/lib/mode.ts](e:/tapne/lovable/src/lib/mode.ts) | Detects mode; injects `DEV_RUNTIME_CONFIG` with `/__devmock__/*` URLs in dev mode |
| [lovable/src/lib/devMock.ts](e:/tapne/lovable/src/lib/devMock.ts) | In-memory mock API resolver; converts `mockData.ts` types to Django API shapes |
| [lovable/src/lib/api.ts](e:/tapne/lovable/src/lib/api.ts) | `IS_DEV_MODE` short-circuit in all four functions (`apiGet`, `apiPost`, `apiPatch`, `apiDelete`) |
| [frontend_spa/src/lib/devMockStub.ts](e:/tapne/frontend_spa/src/lib/devMockStub.ts) | No-op production stub; replaces `devMock.ts` in the external override build |

The production Vite config (`frontend_spa/vite.production.config.ts`) aliases `@/lib/devMock` to `devMockStub.ts`. This keeps the production bundle free of mock trip/user data.

## 3. Good news for cutover

### Theme variables already exist

- [lovable/src/index.css](e:/tapne/lovable/src/index.css)

This means centralized external control is feasible through injected CSS variables and override styles without editing source files under `lovable/`.

All CSS variable values are already known. The complete set to copy verbatim into `static/frontend-brand/tokens.css`:

| Variable | `:root` value | `.dark` value |
|---|---|---|
| `--background` | `160 20% 98%` | `200 20% 8%` |
| `--foreground` | `200 25% 10%` | `160 10% 92%` |
| `--card` | `0 0% 100%` | `200 15% 12%` |
| `--card-foreground` | `200 25% 10%` | `160 10% 92%` |
| `--popover` | `0 0% 100%` | `200 15% 12%` |
| `--popover-foreground` | `200 25% 10%` | `160 10% 92%` |
| `--primary` | `174 55% 42%` | `174 55% 42%` |
| `--primary-foreground` | `0 0% 100%` | `0 0% 100%` |
| `--secondary` | `170 25% 94%` | `200 15% 18%` |
| `--secondary-foreground` | `200 25% 15%` | `160 10% 85%` |
| `--muted` | `170 15% 94%` | `200 10% 18%` |
| `--muted-foreground` | `200 10% 46%` | `200 8% 55%` |
| `--accent` | `174 40% 90%` | `174 30% 18%` |
| `--accent-foreground` | `174 55% 25%` | `174 40% 75%` |
| `--destructive` | `0 72% 55%` | `0 62% 50%` |
| `--destructive-foreground` | `0 0% 100%` | `0 0% 100%` |
| `--border` | `170 20% 88%` | `200 12% 20%` |
| `--input` | `170 20% 88%` | `200 12% 20%` |
| `--ring` | `174 55% 42%` | `174 55% 42%` |
| `--radius` | `0.625rem` | (same) |
| `--sidebar-background` | `160 20% 97%` | `200 15% 10%` |
| `--sidebar-foreground` | `200 15% 30%` | `160 10% 80%` |
| `--sidebar-primary` | `174 55% 42%` | `174 55% 42%` |
| `--sidebar-primary-foreground` | `0 0% 100%` | `0 0% 100%` |
| `--sidebar-accent` | `170 25% 94%` | `200 15% 18%` |
| `--sidebar-accent-foreground` | `200 25% 15%` | `160 10% 85%` |
| `--sidebar-border` | `170 20% 88%` | `200 12% 20%` |
| `--sidebar-ring` | `174 55% 42%` | `174 55% 42%` |

Font: `'Inter', system-ui, -apple-system, sans-serif` on `body`.
Border radius base: `0.625rem`.

### The app can be built independently

- [lovable/package.json](e:/tapne/lovable/package.json)

This enables:

- external build outputs
- post-build transforms outside `lovable/`
- separate packaging and deploy integration

## 4. Django user-facing route inventory

These Django URL patterns currently render HTML templates for browser users. Every one of them must stop rendering Django HTML. The required action for each:

### Routes with a matching Lovable SPA page → redirect to SPA path

| Django URL | Template | Action |
|---|---|---|
| `/` (feed home) | `pages/home.html` | SPA fallback covers it |
| `/accounts/login/` | account login form | Redirect to `/login` |
| `/accounts/signup/` | account signup form | Redirect to `/signup` |
| `/accounts/me/` | `pages/accounts/me.html` | Redirect to `/profile` |
| `/accounts/me/edit/` | `pages/accounts/me_edit.html` | Redirect to `/profile` |
| `/trips/` | `pages/trips/list.html` | Redirect to `/trips` |
| `/trips/create/` | `pages/trips/form.html` | Redirect to `/create-trip` |
| `/trips/mine/` | `pages/trips/mine.html` | Redirect to `/my-trips` |
| `/trips/<id>/` | `pages/trips/detail.html` | Redirect to `/trips/<id>` |
| `/trips/<id>/edit/` | `pages/trips/form.html` | Redirect to `/create-trip?draft=<id>` |
| `/blogs/` | `pages/blogs/list.html` | Redirect to `/blogs` |

### Routes with no Lovable page → SPA catch-all (“Under Construction”)

| Django URL | Template currently served |
|---|---|
| `/about/` | `pages/legal/about.html` |
| `/how-it-works/` | `pages/legal/how_it_works.html` |
| `/safety/` | `pages/legal/safety.html` |
| `/contact/` | `pages/legal/contact.html` |
| `/terms/` | `pages/legal/terms.html` |
| `/privacy/` | `pages/legal/privacy.html` |
| `/search/` | `pages/search.html` |
| `/u/<username>/` | `pages/users/profile.html` |
| `/settings/` | `pages/settings/index.html` |
| `/social/bookmarks/` | `pages/social/bookmarks.html` |
| `/interactions/dm/` | `pages/interactions/dm_inbox.html` |
| `/interactions/dm/<id>/` | `pages/interactions/dm_thread.html` |
| `/reviews/<type>/<id>/` | `pages/reviews/list.html` |
| `/activity/` | `pages/activity/index.html` |
| `/blogs/create/` | `pages/blogs/form.html` |
| `/blogs/<slug>/` | `pages/blogs/detail.html` |
| `/blogs/<slug>/edit/` | `pages/blogs/form.html` |
| `/blogs/<slug>/delete/` | (form) |
| `/enroll/hosting/inbox/` | `pages/enrollment/hosting_inbox.html` |
| `/trips/<id>/delete/` | (form) |

These resolve to the SPA shell. React Router's `*` catch-all route renders the “Under Construction” component. The component must use the same Lovable design tokens so it visually belongs to the app.

### Routes that remain Django-only (backend-only, never render user-facing HTML)

`/frontend-api/**`, `/admin/`, `/uploads/`, `/runtime/`, `/enroll/trips/<id>/request/`, `/enroll/requests/<id>/approve|deny/`, `/social/follow/**`, `/social/bookmark/`, `/social/unbookmark/`, `/interactions/comment/`, `/interactions/reply/`, `/interactions/dm/open/`, `/interactions/dm/<id>/send/`, `/reviews/create/`, `/trips/<id>/banner/`, `/trips/api/destination/**`, `/accounts/logout/`, `/robots.txt`, `/sitemap.xml`, `google*.html`, `/health/`.

## 5. What “production and actual” means in this repo

For this cutover, a route is not production-ready unless:

- the frontend route is served from the real domain
- reads are backed by Django data
- writes hit Django endpoints and persist
- auth is real
- reload/deep-link behavior works
- there is no reliance on in-memory or local-only state for the system of record
- the route is served from the Lovable SPA shell — not a Django template

## 6. Cutover mindset

Do not ask “can the Lovable page be shown?” Ask:

- is the route browser-accessible on the real domain?
- is all displayed data real?
- do actions persist?
- is the frontend shell controllable outside `lovable/`?
- can the route survive a hard refresh and a new browser session?

## 7. Important upgrade to the strategy

These blockers are not excuses to keep the public cutover incomplete.

For this repo, each blocker should be treated as one of:

- an external source-override target
- a runtime/bootstrap shell injection target
- a post-build artifact patch target

The default answer to immutable Lovable source is:

- replace the offending module from outside `lovable/`
- rebuild
- verify that the final artifact no longer contains the fake/local-only behavior

Only call something a real blocker after the external override build and artifact validation paths have both been exhausted.

## 8. Operational blind spots to avoid repeating

These are not Lovable source blockers, but they are real cutover blockers if left unchecked:

- a deploy can pass health/static smoke checks while `/` still fails
- a shell can work for signed-out users and `500` for signed-in users if inline runtime JSON is not serialized safely
- an artifact can look correct while the live domain still fails because runtime/bootstrap injection was not verified after deploy
- PowerShell deploy scripts can fail in Windows environments if they assume `ConvertFrom-Json -Depth` support or fragile switch forwarding

Treat these as part of production readiness, not postscript cleanup.
