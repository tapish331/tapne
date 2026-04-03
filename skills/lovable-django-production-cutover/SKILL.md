---
name: lovable-django-production-cutover
description: Cut over `tapnetravel.com` so a built Lovable app becomes the real frontend while Django remains the real backend, without editing files inside `lovable/`. Use when the task is to replace Lovable mock/local-only behavior through external source-override builds, runtime shell injection, same-origin Django APIs, and production deploy changes so the shipped frontend is fully real.
---

# Lovable Django Production Cutover

Use this skill when the goal is not visual parity, but a real frontend-backend split:

- Lovable is the shipped browser UI
- Django is the real backend for auth, data, uploads, business logic, and admin
- `tapnetravel.com` must be fully operational
- nothing under `lovable/` may be edited

Read `references/current-state-audit.md` first. Read `references/deployment-blueprint.md` before changing infra.
Read `references/no-touch-override-build.md` before deciding anything is "blocked by immutable frontend code".
Read `references/operational-hardening.md` before closing the work or trusting a deploy.

## Non-Negotiable Rules

1. Never edit files under `lovable/`.
2. Never ship mock, demo, or local-only behavior on production routes.
3. Treat any remaining `mockData`, fake auth, fake booking/application flows, or `localStorage`-only persistence as a cutover blocker.
4. Keep centralized frontend control outside `lovable/`, not copied across generated files.
5. Build Lovable to an output directory outside `lovable/` so the generated bundle can be wrapped, patched, and deployed without violating rule 1.
6. Verify real end-to-end behavior against Django-backed routes and data before calling the work done.
7. Do not accept "the Lovable source is immutable" as a reason to stop. The default solution is an external source-override build layer, not surrender.
8. Do not treat health checks and static asset checks as enough. The public root route and the live SPA shell must be verified explicitly.
9. Prefer inline runtime/bootstrap config in the served HTML shell over a second blocking request to `/frontend-runtime.js`.
10. Any server-rendered bootstrap payload that can contain Django-native values must be serialized with a Django-safe encoder, not raw `json.dumps(...)`.
11. Lovable is the sole source for every user-facing page and modal. No Django template may render a public-facing HTML page. Every URL a browser user can navigate to must resolve to the Lovable SPA shell. Django must not send its own rendered HTML for any public route — including legal pages, profile pages, search, settings, and activity.
12. For any URL that exists in Django but has no corresponding Lovable page, Django must serve the Lovable SPA shell. The SPA catch-all route (`*`) must be overridden externally to render a styled "Under Construction" page — never a bare 404 and never a Django-rendered template. See `references/override-targets.md` for the override spec and the full route gap table.
13. `static/frontend-brand/tokens.css` must be an exact mirror of the CSS variable values declared in `lovable/src/index.css`. No value may deviate from what Lovable ships by default. The file exists solely to externalise control so future changes have one place to edit — not to alter current appearance. `static/frontend-brand/overrides.css` must remain empty unless a deliberate visual change is explicitly requested.
14. The override `App.tsx` in `frontend_spa/` must import **all** user-facing pages from `@/pages/*` (i.e. the real Lovable source pages under `lovable/src/pages/`). The only permitted `@frontend/pages/*` import is `UnderConstructionPage`. Every other page must come from `@/`. Importing a custom replacement page from `@frontend/pages/*` instead of the real Lovable page is a critical regression — it strips out all Lovable UI (carousels, tabs, custom components) and replaces it with a stripped-down shell.
15. The override `App.tsx` must preserve every React provider that exists in `lovable/src/App.tsx`. Read `lovable/src/App.tsx` before writing the override and mirror the provider tree exactly: `QueryClientProvider`, `AuthProvider`, `DraftProvider`, `TooltipProvider`, both `Toaster`s. Dropping any provider causes silent runtime failures across all pages.
16. Every Django URL that previously rendered an HTML template must have an explicit SPA shell pattern in `frontend/urls.py` **before** the Django app's own `urls.py` is included. The global catch-all in `tapne/urls.py` is a safety net, not a substitute for explicit patterns. Parameterised routes (`trips/<id>/edit/`, `trips/<id>/delete/`, `blogs/<slug>/edit/`, `u/<username>/`, etc.) must be listed explicitly with `re_path`. Never assume the catch-all will reach them first — Django's URL resolver matches in declaration order and app-specific `urls.py` files are included before the catch-all.
17. After every `lovable/` submodule pull, verify that the four dual-mode files are still present and intact: `lovable/src/lib/mode.ts`, `lovable/src/lib/devMock.ts`, `lovable/src/lib/api.ts`, and `lovable/src/main.tsx`. Lovable can silently overwrite any of them during normal development. A missing or reverted `mode.ts` makes `IS_DEV_MODE` permanently undefined (crash). A reverted `api.ts` removes the mock interception and sends real fetch calls to `/__devmock__/*` URLs that do not exist on Django. Re-apply the dual-mode changes before building whenever these files have regressed.

## Use This Skill When

- The user wants Lovable to become the real frontend for `tapnetravel.com`.
- The user wants Django to remain the real backend.
- The current Django templates should stop being the main public UI.
- The user explicitly disallows changes inside `lovable/`.
- The work includes Cloud Run, Django routing, static/frontend asset serving, session/auth integration, or replacing frontend mock behavior with real backend behavior.

## Repo Facts

- Public deployment for this repo runs through [infra/run-cloud-run-workflow.ps1](e:/tapne/infra/run-cloud-run-workflow.ps1) and [infra/Dockerfile.web](e:/tapne/infra/Dockerfile.web).
- Depending on `LOVABLE_FRONTEND_ENABLED`, those deploy paths can serve Django-rendered public pages or the Lovable SPA shell through Django.
- Do not assume the live site is still in an earlier Django-only mode. Verify the current live shell and revision on every invocation.
- Lovable is a standalone Vite SPA from [lovable/package.json](e:/tapne/lovable/package.json).
- **Dual-mode architecture** — Lovable operates in two modes controlled entirely by whether `window.TAPNE_RUNTIME_CONFIG` is present at page load:
  - **Lovable dev mode** (`window.TAPNE_RUNTIME_CONFIG` absent): `lovable/src/lib/mode.ts` detects absence, injects a mock runtime config with `/__devmock__/*` API URLs, and sets `IS_DEV_MODE = true`. All API calls in `lovable/src/lib/api.ts` are intercepted by `lovable/src/lib/devMock.ts`, which returns in-memory mock responses built from `mockData.ts`. Auth, drafts, and all page data work fully in the Lovable editor without Django.
  - **Django production mode** (`window.TAPNE_RUNTIME_CONFIG` present, injected by Django): `IS_DEV_MODE = false`. `mode.ts` does not overwrite the real config. All `api.ts` functions skip mock interception and execute real Django fetch calls exactly as before.
  - The switch is automatic — no manual flag or env var needed. Pulling `lovable/` into this repo and building with Django's HTML shell injection activates Django mode.
- The four dual-mode files that must stay intact across Lovable submodule updates:
  - [lovable/src/lib/mode.ts](e:/tapne/lovable/src/lib/mode.ts) — mode detection and dev config injection (must be first import in main.tsx)
  - [lovable/src/lib/devMock.ts](e:/tapne/lovable/src/lib/devMock.ts) — in-memory mock API resolver for dev mode
  - [lovable/src/lib/api.ts](e:/tapne/lovable/src/lib/api.ts) — IS_DEV_MODE interception in all four API functions
  - [lovable/src/main.tsx](e:/tapne/lovable/src/main.tsx) — `import "@/lib/mode"` must be the first import
- `lovable/src/data/mockData.ts` is no longer a production blocker — it is only used by `devMock.ts` for Lovable dev mode. In the production build, `@/lib/devMock` is aliased to `frontend_spa/src/lib/devMockStub.ts`, which excludes both `devMock.ts` and `mockData.ts` from the bundle entirely.
- The former mock blockers in Lovable are now resolved:
  - `lovable/src/contexts/AuthContext.tsx` — Django session-backed (real login/signup/profile via `cfg.api.*`)
  - `lovable/src/contexts/DraftContext.tsx` — Django-backed draft CRUD (real persistence via `cfg.api.trip_drafts`)
  - All pages (`Index`, `BrowseTrips`, `TripDetail`, `MyTrips`, `Profile`, `Blogs`) — Django API-backed via `apiGet/apiPost` through `lovable/src/lib/api.ts`
- Lovable SPA pages (from [lovable/src/App.tsx](e:/tapne/lovable/src/App.tsx)): `/`, `/trips`, `/trips/:id`, `/create-trip`, `/my-trips`, `/blogs`, `/login`, `/signup`, `/profile`, `*` (catch-all).
- Django routes with user-facing HTML that are NOT covered by a Lovable page — these must all resolve to the Lovable SPA shell, where the `*` catch-all renders the "Under Construction" page:
  - `/about/`, `/how-it-works/`, `/safety/`, `/contact/`, `/terms/`, `/privacy/`
  - `/search/`
  - `/u/<username>/` (public user profile)
  - `/settings/`, `/settings/appearance/`
  - `/social/bookmarks/`
  - `/interactions/dm/`, `/interactions/dm/<id>/`
  - `/reviews/<type>/<id>/`
  - `/activity/`
  - `/blogs/create/`, `/blogs/<slug>/`, `/blogs/<slug>/edit/`, `/blogs/<slug>/delete/`
  - `/enroll/hosting/inbox/`
- Django routes with user-facing HTML that ARE covered by a Lovable page — these must redirect to the SPA equivalent instead of rendering a Django template:
  - `/accounts/login/` → `/login`
  - `/accounts/signup/` → `/signup`
  - `/accounts/me/` and `/accounts/me/edit/` → `/profile`
  - `/trips/` → `/trips`
  - `/trips/create/` → `/create-trip`
  - `/trips/mine/` → `/my-trips`
  - `/trips/<id>/` → `/trips/<id>`
  - `/trips/<id>/edit/` → `/create-trip?draft=<id>`
  - `/blogs/` → `/blogs`
  - `/` (feed home Django view) → covered by SPA fallback
- The SPA catch-all must be implemented via a **global Django catch-all** appended at the very end of `tapne/urls.py` (after all real routes) when `LOVABLE_FRONTEND_ENABLED=True`. This guarantees every unclaimed URL serves the SPA shell rather than a 404 or Django template.
- Lovable already exposes theme variables in [lovable/src/index.css](e:/tapne/lovable/src/index.css), which makes centralized external overrides feasible.

## Allowed Modification Surfaces

- Django apps, models, views, serializers, templates, and settings
- `infra/**`
- new static assets and runtime config files outside `lovable/`
- external override modules, external Vite config, and build wrapper code outside `lovable/`
- new wrapper templates or SPA fallback views in Django
- generated Lovable build output outside `lovable/`
- deployment scripts, container build steps, and Cloud Run routing

## Forbidden Shortcuts

- Do not leave Lovable auth backed by fake `setUser(users[0])`.
- Do not leave trip/blog/profile pages reading compiled mock catalogs in production.
- Do not rely on `localStorage` as the system of record for drafts, bookings, or applications.
- Do not cut traffic over to a frontend route until create/read/update/delete flows are real.
- Do not solve theme control by hand-editing compiled bundle colors in many places; centralize via injected CSS variables and override files.
- Do not default to raw post-build bundle surgery if the problem can be solved more cleanly with external source-level alias overrides.
- **Do not write custom `@frontend/pages/*` replacements for pages that Lovable already implements.** The Lovable source pages (`@/pages/*`) must be used directly. Custom page replacements bypass the entire Lovable UI and produce visually broken pages. Only create `@frontend/` components for things that do not exist at all in Lovable (e.g. `UnderConstructionPage`).
- **Do not omit providers when writing the override `App.tsx`.** Read `lovable/src/App.tsx` first and copy the provider tree exactly. A missing `QueryClientProvider` or `DraftProvider` breaks all data-fetching and draft management silently.
- **Do not rely on the global `tapne/urls.py` catch-all to intercept parameterised Django routes.** Django resolves URLs in declaration order — app-specific `urls.py` files (trips, blogs, accounts) are included before the catch-all, so `trips/<id>/edit/` and similar paths will be matched by the Django template view unless an explicit SPA shell pattern is declared in `frontend/urls.py` first.
- **Do not add visual CSS rules to `overrides.css`.** Rules like `font-family: serif`, `border-radius: ... !important`, or `box-shadow: ... !important` change the visual appearance of the app relative to standalone Lovable. `overrides.css` exists only for non-visual functional fixes (z-index corrections, etc.) unless a deliberate visual change is explicitly requested by the user.
- **Do not let the production Vite build include `devMock.ts` or `mockData.ts`.** The production build entry (`frontend_spa/`) must alias `@/lib/devMock` to `frontend_spa/src/lib/devMockStub.ts` in `frontend_spa/vite.production.config.ts`. Without this stub, the bundle carries all mock trip and user data, fails the `"mock_data"` banned-marker artifact check, and is ~50 KB larger than necessary. The stub is already in place — do not remove it or remove the alias.
- **Do not remove or weaken the dual-mode files in `lovable/src/lib/`.** If Lovable overwrites `mode.ts`, `devMock.ts`, `api.ts`, or `main.tsx` during a submodule update, re-apply the dual-mode changes before building. Check with `git diff HEAD~1 -- lovable/src/lib/api.ts lovable/src/lib/mode.ts lovable/src/main.tsx` after every submodule pull.

## Workflow

### 1. Audit Lovable production blockers

Run the bundled audit script:

```powershell
python skills/lovable-django-production-cutover/scripts/audit_lovable_blockers.py --repo-root e:\tapne
```

This identifies mock-data imports, local-only storage, and fake state patterns that block production cutover.
It is intentionally rerun each time because Lovable is expected to evolve.

Then inspect:

- `references/current-state-audit.md`
- `references/override-targets.md`
- [lovable/src/App.tsx](e:/tapne/lovable/src/App.tsx)

Do not start infra work before you know which Lovable routes are still fake.

### 1b. Verify dual-mode files after every submodule pull (run every time)

After pulling `lovable/` changes, verify these four files are still intact before doing anything else. Lovable can silently overwrite them during normal development sessions.

```bash
# Check if any dual-mode files were changed in the latest lovable commit
cd lovable && git diff HEAD~1 -- src/lib/mode.ts src/lib/devMock.ts src/lib/api.ts src/main.tsx
```

For each file, confirm:

| File | Required condition |
|---|---|
| `lovable/src/main.tsx` | First import is `import "@/lib/mode"` |
| `lovable/src/lib/mode.ts` | Exports `IS_DEV_MODE`, injects `DEV_RUNTIME_CONFIG` when dev, all `/__devmock__/*` API URLs present |
| `lovable/src/lib/api.ts` | Imports `IS_DEV_MODE` and `resolveMockRequest`; all four functions have `if (IS_DEV_MODE) return resolveMockRequest(...)` as first line |
| `lovable/src/lib/devMock.ts` | Exports `resolveMockRequest`; handles session, auth, home, trips, trip detail, blogs, my-trips, draft CRUD, profile |

If any file has been overwritten by Lovable, re-apply the dual-mode changes (see `references/no-touch-override-build.md` Section "Dual-mode system"). Then continue with the rest of the workflow.

### 1d. Audit the override App.tsx and frontend/urls.py (run every time)

Before touching anything else, cross-check these two files against `lovable/src/App.tsx`:

**`frontend_spa/src/App.tsx` checklist:**

1. Open `lovable/src/App.tsx` and list every import, every provider, every route.
2. In `frontend_spa/src/App.tsx`, confirm:
   - Every page import uses `@/pages/<PageName>` (Lovable source) — **not** `@frontend/pages/<PageName>`.
   - The only `@frontend/pages/*` import is `UnderConstructionPage`.
   - The provider tree matches `lovable/src/App.tsx` exactly: `QueryClientProvider`, `AuthProvider`, `DraftProvider`, `TooltipProvider`, `Toaster` (both variants).
   - The route list matches `lovable/src/App.tsx` exactly — same paths, same page components, same `*` catch-all (pointing to `UnderConstructionPage`).
3. If any page is imported from `@frontend/pages/*` other than `UnderConstructionPage`, replace it with `@/pages/*` immediately — this is a critical visual regression.

**`frontend/urls.py` checklist:**

1. List every Django URL pattern across all `urls.py` files that renders an HTML template for a browser user (see route tables in `references/current-state-audit.md`).
2. For every such URL, confirm `frontend/urls.py` has an explicit SPA shell pattern (`path(...)` or `re_path(...)` pointing to `frontend_entrypoint_view`) that will be matched **before** the Django template view.
3. Pay special attention to parameterised routes: `trips/<id>/edit/`, `trips/<id>/delete/`, `blogs/<slug>/edit/`, `blogs/<slug>/delete/`, `u/<username>/`, `interactions/dm/<id>/`.
4. Verify using Django's URL resolver:
   ```bash
   python manage.py shell -c "
   from django.urls import resolve
   for url in ['/trips/1/edit/', '/accounts/login/', '/u/testuser/']:
       print(url, '->', resolve(url).func.__name__)
   "
   ```
   Every URL must resolve to `frontend_entrypoint_view`, not a template-rendering view.

### 2. Define route ownership

Route ownership in this repo is permanently fixed:

- `spa-public`: **every browser-navigable URL** — served by the Lovable SPA shell via Django's SPA fallback. Includes all routes defined in `lovable/src/App.tsx` and all Django user-facing URLs listed in the Repo Facts section above. No exceptions.
- `backend-only`: `/frontend-api/**`, `/admin/`, `/uploads/`, `/runtime/`, `/trips/<id>/banner/`, `/trips/api/destination/**`, `/accounts/logout/`, `/enroll/trips/<id>/request/`, `/enroll/requests/<id>/approve|deny/`, `/social/follow/**`, `/social/bookmark|unbookmark/`, `/interactions/comment/`, `/interactions/reply/`, `/interactions/dm/open/`, `/interactions/dm/<id>/send/`, `/reviews/create/`, `/runtime/health/`, `/robots.txt`, `/sitemap.xml`, `google*.html`. These are called by the SPA via `fetch()` — they never render HTML for a user.

**There is no `django-web` class.** Django no longer renders any user-facing page. Every URL not in `backend-only` gets the SPA shell.

Django URL patterns that previously rendered HTML templates for public-facing routes must be converted to one of:
  - a redirect to the equivalent SPA path (if one exists in `lovable/src/App.tsx`), OR
  - a pass-through to the SPA catch-all (if there is no Lovable page — the SPA's `*` route will render "Under Construction")

### 3. Build Lovable through an external override layer

Default approach for this repo:

1. keep `lovable/` source untouched
2. create production replacement modules outside `lovable/`
3. build the app with an external Vite config that aliases specific Lovable imports to those replacement modules
4. emit the build artifact outside the Lovable tree

This is the primary method for removing fake logic without source edits. Use post-build transforms only for shell injection or residual fixes that aliasing cannot reach.

Read:

- `references/no-touch-override-build.md`
- `references/override-targets.md`

Typical replacements in this repo:

- fake auth context -> Django session-backed auth context
- `mockData` imports -> live data facade with the same export shape
- localStorage draft context -> Django-backed draft provider with identical external API
- fake booking/application logic -> same-origin Django API mutations

### 4. Build Lovable outside the source tree

Do not build into `lovable/dist` if you need to patch or wrap output. Build externally:

```powershell
pwsh -File infra/build-lovable-production-frontend.ps1
```

Use the external output directory as the deployable frontend artifact. This keeps the source tree untouched while allowing production packaging work.

If you are using an external override build config, keep it outside `lovable/` too.

### 5. Externalize centralized frontend control

Keep frontend control in files outside `lovable/`:

- `static/frontend-brand/tokens.css`
- `static/frontend-brand/overrides.css`
- `static/frontend-brand/runtime-config.js`

For this repo, the preferred production shell is:

- inline `window.__TAPNE_FRONTEND_CONFIG__` in the served HTML
- no hard dependency on `/frontend-runtime.js` for the public page bootstrap

Load them into the shipped frontend shell after the Lovable bundle is built:

- `tokens.css`: CSS variable declarations that must exactly match `lovable/src/index.css` — both `:root` and `.dark` blocks. Copy the values verbatim. Do not invent or change any value. The purpose is externalised control, not visual change.
- `overrides.css`: must be empty by default. Only add rules here when a deliberate visual change is explicitly requested by the user. Never populate it as part of a standard cutover.
- `runtime-config.js`: API base URL, environment flags, auth/bootstrap config

**Exact token values to use in `tokens.css`** (sourced from `lovable/src/index.css`):

`:root` block:
```css
--background: 160 20% 98%;
--foreground: 200 25% 10%;
--card: 0 0% 100%;
--card-foreground: 200 25% 10%;
--popover: 0 0% 100%;
--popover-foreground: 200 25% 10%;
--primary: 174 55% 42%;
--primary-foreground: 0 0% 100%;
--secondary: 170 25% 94%;
--secondary-foreground: 200 25% 15%;
--muted: 170 15% 94%;
--muted-foreground: 200 10% 46%;
--accent: 174 40% 90%;
--accent-foreground: 174 55% 25%;
--destructive: 0 72% 55%;
--destructive-foreground: 0 0% 100%;
--border: 170 20% 88%;
--input: 170 20% 88%;
--ring: 174 55% 42%;
--radius: 0.625rem;
--sidebar-background: 160 20% 97%;
--sidebar-foreground: 200 15% 30%;
--sidebar-primary: 174 55% 42%;
--sidebar-primary-foreground: 0 0% 100%;
--sidebar-accent: 170 25% 94%;
--sidebar-accent-foreground: 200 25% 15%;
--sidebar-border: 170 20% 88%;
--sidebar-ring: 174 55% 42%;
```

`.dark` block:
```css
--background: 200 20% 8%;
--foreground: 160 10% 92%;
--card: 200 15% 12%;
--card-foreground: 160 10% 92%;
--popover: 200 15% 12%;
--popover-foreground: 160 10% 92%;
--primary: 174 55% 42%;
--primary-foreground: 0 0% 100%;
--secondary: 200 15% 18%;
--secondary-foreground: 160 10% 85%;
--muted: 200 10% 18%;
--muted-foreground: 200 8% 55%;
--accent: 174 30% 18%;
--accent-foreground: 174 40% 75%;
--destructive: 0 62% 50%;
--destructive-foreground: 0 0% 100%;
--border: 200 12% 20%;
--input: 200 12% 20%;
--ring: 174 55% 42%;
--sidebar-background: 200 15% 10%;
--sidebar-foreground: 160 10% 80%;
--sidebar-primary: 174 55% 42%;
--sidebar-primary-foreground: 0 0% 100%;
--sidebar-accent: 200 15% 18%;
--sidebar-accent-foreground: 160 10% 85%;
--sidebar-border: 200 12% 20%;
--sidebar-ring: 174 55% 42%;
```

Font: `font-family: 'Inter', system-ui, -apple-system, sans-serif;` on `body`.

Border radius: `--radius: 0.625rem`. Derived values (`lg`, `md`, `sm`) are computed by Tailwind — do not redeclare them.

If the build output needs injection, patch the external build artifact or serve it through a Django wrapper template. Do not patch files under `lovable/`.
If the injected runtime payload includes datetimes, decimals, or model-derived data, use Django-safe JSON serialization.

### 6. Replace mock behavior with real backend behavior

This is the core cutover requirement.

For each Lovable route or modal:

1. identify which data or actions are currently fake
2. expose or refine the corresponding Django backend contract
3. connect the shipped frontend to real endpoints
4. confirm browser behavior against real records

Acceptable implementation patterns without editing `lovable/`:

- external source-level alias overrides for specific Lovable modules
- server-rendered bootstrap JSON injected into the SPA shell
- wrapper-injected runtime shims
- post-build JavaScript transforms against the external build output
- same-origin Django APIs consumed by the shipped frontend
- reverse proxy rules that keep browser URLs stable while splitting frontend and backend responsibilities

Preferred order:

1. external source-level override build
2. same-origin backend API contract
3. server/bootstrap runtime injection
4. post-build artifact transform only where needed

Do not mark a route blocked merely because the original Lovable source uses fake logic. First prove that:

- the import cannot be overridden externally, and
- the remaining behavior cannot be replaced through runtime/bootstrap or deterministic artifact transforms

Only then is it a real blocker.

### 7. Use Django as the real backend

Django remains responsible for:

- session/auth and identity
- profiles
- trips, blogs, drafts, bookings, applications
- uploads/media access
- business rules and validation
- admin and operational endpoints

Favor same-origin APIs for the browser app so cookies, CSRF, and deployment are simpler on `tapnetravel.com`.

When replacing a Lovable module externally, preserve its public API shape whenever possible. The replacement module should make the compiled app believe it is still talking to the same context/provider/data helpers, but all reads and writes must route to Django-backed truth.

### 8. Serve the frontend correctly in production

Recommended pattern for this repo:

- Django/Cloud Run serves backend endpoints and, if simplest, the compiled frontend asset shell too
- non-API public routes fall back to the Lovable SPA entrypoint
- backend routes stay owned by Django
- static frontend assets come from WhiteNoise or a dedicated static bucket/CDN, depending on deployment constraints

Any Cloud Run or container changes should be made in:

- [infra/Dockerfile.web](e:/tapne/infra/Dockerfile.web)
- [infra/run-cloud-run-workflow.ps1](e:/tapne/infra/run-cloud-run-workflow.ps1)
- related deploy scripts under [infra](e:/tapne/infra)

When touching PowerShell deploy/orchestration scripts:

- keep Windows PowerShell 5.1 compatibility in mind
- do not depend on `ConvertFrom-Json -Depth`
- verify switch/boolean forwarding between scripts end-to-end
- if immutable `lovable/` lockfiles are out of sync, use a disposable install strategy outside `lovable/` rather than editing tracked files there

### 9. Production acceptance checklist

Do not close the work until all relevant items are true:

- public frontend routes render the Lovable UI on the real domain
- no frontend route depends on mock data
- auth is real
- drafts are server-backed or otherwise truly persisted by Django
- trips/blogs/profile data are real
- create/update/delete flows write through Django
- direct refresh on SPA routes works in production
- build and deploy are reproducible from repo scripts
- centralized color/font/shape control exists outside `lovable/`
- `static/frontend-brand/tokens.css` CSS variable values are identical to `lovable/src/index.css` — no visual deviation
- `static/frontend-brand/overrides.css` is empty (no unsolicited visual overrides)
- the built artifact no longer contains banned mock/local-only markers
- the built artifact does not require `/frontend-runtime.js` to boot
- the served root HTML includes inline runtime config
- the root route works for both signed-out and signed-in sessions
- no Django template is being served for any browser-navigable URL (run `grep -r "render(request" <all_app_views>` and confirm every hit is either a `backend-only` endpoint or has been replaced by an SPA redirect/fallback)
- every Django URL that previously rendered a user-facing template now either redirects to the SPA equivalent or falls through to the SPA catch-all
- the SPA catch-all (`*` route) renders an "Under Construction" page — not a blank screen, not a Django 404, not an error
- the "Under Construction" page uses the same Lovable design tokens (colors, font, radius) as the rest of the SPA — it must look like it belongs to the same app
- `frontend_spa/src/App.tsx` imports every user-facing page from `@/pages/*` (Lovable source) — no `@frontend/pages/*` imports except `UnderConstructionPage`
- `frontend_spa/src/App.tsx` provider tree matches `lovable/src/App.tsx` exactly (`QueryClientProvider`, `AuthProvider`, `DraftProvider`, `TooltipProvider`, both `Toaster`s)
- `frontend/urls.py` has explicit SPA shell patterns for every parameterised Django route that previously rendered a template (`trips/<id>/edit/`, `trips/<id>/delete/`, `blogs/<slug>/edit/`, `u/<username>/`, etc.) — verified with Django's URL resolver
- `static/frontend-brand/overrides.css` contains no visual CSS rules (no font-family overrides, no `!important` border-radius or shadow overrides) — only non-visual functional fixes are permitted
- dual-mode files in `lovable/src/lib/` are intact: `mode.ts` exports `IS_DEV_MODE` and injects mock config, `devMock.ts` exports `resolveMockRequest`, `api.ts` has IS_DEV_MODE interception in all four functions, `main.tsx` imports `@/lib/mode` first
- `frontend_spa/vite.production.config.ts` aliases `@/lib/devMock` to `frontend_spa/src/lib/devMockStub.ts` — verified present in the alias map
- production bundle does not contain `mockData` in any JS bundle or source map file (confirmed by artifact checker — a failure here means the devMockStub alias was not applied)

Run the bundled verifier against the final artifact:

```powershell
python skills/lovable-django-production-cutover/scripts/verify_cutover_artifact.py ^
  --repo-root e:\tapne ^
  --build-dir e:\tapne\artifacts\lovable-production-dist
```

Then verify the live deployment, not just the artifact:

```powershell
python skills/lovable-django-production-cutover/scripts/verify_live_cutover.py ^
  --base-url https://tapnetravel.com/
```

### 10. Browser verification

Always verify with real renders, not assumptions.

Use the browser loop to check:

- signed-out and signed-in states
- direct route loads
- create/edit/publish flows
- 404 and fallback handling
- responsive breakpoints
- fresh browser session with no legacy localStorage state
- hard refresh after auth, drafts, bookings, and application actions
- that source-override replacements actually drive the visible UI rather than dormant backend endpoints
- that `/` does not blank-screen because of bootstrap/runtime config failures
- that the active Cloud Run revision is not still serving `500` requests after deploy

For visual QA or screenshot sweeps, also use:

- `../webpage-visual-perfection-audit/SKILL.md`

## Reporting

When closing the work, report:

- which routes are now Lovable-fronted
- which routes remain Django-rendered and why
- which mock blockers were removed
- where centralized brand/runtime control lives
- how the build and deploy flow changed
- what was verified in the browser against real backend data

## Resources

- `references/current-state-audit.md`: repo-specific mock blocker inventory
- `references/deployment-blueprint.md`: production serving and cutover patterns for this repo
- `references/no-touch-override-build.md`: primary strategy for replacing immutable Lovable modules
- `references/operational-hardening.md`: runtime shell, workflow, and live verification guardrails
- `references/override-targets.md`: repo-specific Lovable module override map
- `scripts/audit_lovable_blockers.py`: quick audit for mock/local-only frontend blockers
- `scripts/verify_cutover_artifact.py`: final check that the emitted frontend artifact no longer contains banned mock/local-only patterns
- `scripts/verify_live_cutover.py`: live-domain check for the hardened SPA shell and same-origin Django APIs
