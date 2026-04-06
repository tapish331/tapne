---
name: lovable-django-production-cutover
description: >
  Executes the full Tapne production cutover: git pull both repos, extract every
  frontend route/API key/mock pattern from the CURRENT files, connect each to the exact
  Django counterpart, fix any remaining Django gaps, and write one Lovable prompt only if
  a true showstopper remains that cannot be resolved from Django alone. Never modifies
  files under lovable/.
---

# Lovable → Django Production Cutover

## Absolute restriction

**Never write, patch, create, rename, or delete anything under `lovable/`.**
Only `git pull` is allowed there. Treat any other write to that tree as unconditional refusal.

---

## When invoked, execute this exact sequence — no stops, no memos

---

## Step 1 — Git pull both repos

```bash
git pull
git -C lovable pull
```

Report the HEAD SHA of each repo after pull so the run is traceable.

---

## Step 2 — Extract all routes, API keys, and backend communication from the frontend

> **Nothing in this step is pre-answered. Read the actual current files every time.**
> The **Baseline Reference** section at the bottom of this skill lists what existed
> as of April 2026. Diff your findings against it and explicitly flag every item that is NEW
> (present in current files but not in the baseline) and every item that is REMOVED
> (in the baseline but gone from the current files). New items drive all the work in Steps 3–6.

Read these files in full:

- [lovable/src/App.tsx](../../lovable/src/App.tsx)
- [lovable/src/types/api.ts](../../lovable/src/types/api.ts)
- [lovable/src/types/messaging.ts](../../lovable/src/types/messaging.ts) ← **required**: Inbox uses ThreadData/InboxResponse from here, not api.ts
- [lovable/src/lib/mode.ts](../../lovable/src/lib/mode.ts)
- [lovable/src/lib/api.ts](../../lovable/src/lib/api.ts)
- [lovable/src/lib/devMock.ts](../../lovable/src/lib/devMock.ts)
- [lovable/src/data/mockData.ts](../../lovable/src/data/mockData.ts)
- [lovable/src/main.tsx](../../lovable/src/main.tsx)
- [lovable/src/contexts/AuthContext.tsx](../../lovable/src/contexts/AuthContext.tsx)
- [lovable/src/contexts/DraftContext.tsx](../../lovable/src/contexts/DraftContext.tsx)
- [frontend_spa/src/App.tsx](../../frontend_spa/src/App.tsx)
- [frontend_spa/src/lib/api.ts](../../frontend_spa/src/lib/api.ts)
- [frontend_spa/vite.production.config.ts](../../frontend_spa/vite.production.config.ts)

Also scan for any additional `*.ts` type files imported by pages/contexts/components:

```bash
grep -rn "from \"@/types/" lovable/src/pages lovable/src/contexts lovable/src/components \
  --include="*.ts" --include="*.tsx" | grep -v "api\|messaging" | sort -u
```

Any type file found here must also be read in full — it may define response shapes that Django must satisfy.

Then scan every page component and context for any additional `cfg.api.*` usages, direct fetch calls, or `apiGet`/`apiPost`/`apiPatch`/`apiDelete` calls:

```bash
grep -rn "apiGet\|apiPost\|apiPatch\|apiDelete\|cfg\.api\.\|cfg\.auth\." \
  lovable/src/pages lovable/src/contexts lovable/src/components \
  --include="*.ts" --include="*.tsx"
```

Produce four fresh tables from what you actually read — do **not** copy-paste the baseline:

### 2a. Page routes — extracted from lovable/src/App.tsx vs frontend_spa/src/App.tsx

One row per `<Route>` in `lovable/src/App.tsx`. Compare against `frontend_spa/src/App.tsx`.
If Lovable has a route not mirrored in `frontend_spa/src/App.tsx`, flag it.
If `frontend_spa/src/App.tsx` has an extra route not in Lovable, flag it.

### 2b. TapneRuntimeConfig.api keys — extracted from lovable/src/types/api.ts

One row per key in the `api` field of `TapneRuntimeConfig`. For each key, note:
- The key name (e.g. `trips`)
- The `/__devmock__/...` URL used in `mode.ts` DEV_RUNTIME_CONFIG
- HTTP methods that `lovable/src/lib/api.ts` and page components call against it

### 2c. All API call patterns — extracted from pages, contexts, and components

One row per distinct call site: file, API key used (`cfg.api.X`), HTTP method, any URL interpolation (e.g. `${cfg.api.trips}${id}/`), request body fields.

### 2d. Django URL → view map — extracted from frontend/urls.py

One row per URL pattern: HTTP method, path, view function name.

After producing these tables, write a **Diff summary**:

```
NEW routes (in lovable/src/App.tsx, not in baseline):         [list or "none"]
NEW api keys in TapneRuntimeConfig (not in baseline):          [list or "none"]
NEW api call patterns (not in baseline):                       [list or "none"]
NEW django endpoints (in frontend/urls.py, not in baseline):   [list or "none"]
REMOVED from baseline:                                         [list or "none"]
```

If all diffs are "none", state that explicitly and continue.

---

## Step 3 — Connect every route and API call to the exact Django backend handler

Read [frontend/urls.py](../../frontend/urls.py) and [frontend/views.py](../../frontend/views.py) in full first.

For **every** entry in your Step 2c table:

1. Resolve the full URL from the `cfg.api.*` key + any interpolation (e.g. `cfg.api.trips` → `/frontend-api/trips/`, full call → `/frontend-api/trips/${id}/`).
2. Find the corresponding Django URL pattern and view in `frontend/urls.py`.
3. If it exists and is correct → mark ✓.
4. If it is missing or wrong → mark ✗ and fix it now (add view + URL entry). Do not defer.

**Also scan for `cfg.api.base` interpolation patterns** — these are NOT named api keys but still need Django endpoints:

```bash
grep -rn "cfg\.api\.base" lovable/src/pages lovable/src/contexts lovable/src/components \
  --include="*.ts" --include="*.tsx"
```

Each result like `${cfg.api.base}/profile/${profileId}/` needs a matching `frontend-api/profile/<id>/` URL in `frontend/urls.py`. These are easy to miss because they don't appear in `TapneRuntimeConfig.api`.

Decision rules for NEW items found in the diff:

- **New route in lovable/src/App.tsx** → needs a matching `<Route>` in `frontend_spa/src/App.tsx` AND a Django SPA entrypoint URL in `frontend/urls.py` (pointing at `views.frontend_entrypoint_view`).
- **New `TapneRuntimeConfig.api` key** → needs a corresponding entry in `_runtime_config_payload()` in `frontend/views.py` AND a Django URL+view to handle it.
- **New API call against an existing key at a new URL shape** (e.g. new `/${id}/action/` suffix) → needs a new Django URL pattern and view.
- **New call in a context or component not previously scanned** → treat the same as a page-level call.

For items carried over from the baseline, verify they still exist and still match. If anything drifted, fix it.

### 3b. Auth-gate and unauthenticated-state audit

For every page and context that makes API calls, determine:

1. **Does the page auth-gate before calling the API?** Read the component and check whether it guards behind `isAuthenticated` / `requireAuth()` before firing the request.
2. **What happens if the user is NOT authenticated and the call fires anyway?** The Django view returns `_member_only_error()` (401). Does the frontend handle this gracefully (silent catch), or does it show a success toast anyway?
3. **Does the Django view return the correct 401 with a clear error body?** Confirm `_member_only_error()` is called before any DB access.

Known unauthenticated-path issues to check every run:

| Component | Risk | Expected behaviour |
|---|---|---|
| `CreateTrip.tsx` | `createDraft()` fires on mount even before auth hydrates | Django rejects with 401; `draftId` stays null; `saveDraftData()` is a no-op; but toast may fire anyway — Lovable prompt needed if toast fires when `draftId == null` |
| `DraftContext.tsx` | Loads drafts from `my_trips` on mount, gated by `cfg.session.authenticated` | Verify the gate is checking the session before firing |
| `Inbox.tsx` | Calls `dm_inbox` then calls `.find()` on result | Verify unauthenticated response is `{ threads: [] }` not an error object |

### 3c. Backend-owned routes — never handed to the SPA

These are always Django-only regardless of what Lovable adds. Check they are still present and not accidentally shadowed by the SPA catch-all in `tapne/urls.py`:

- `/admin/`
- `/health/`
- `/runtime/`
- `/uploads/`
- `/search/`
- `/accounts/login/` and `/accounts/signup/` (Django form views — SPA serves its own `/login` and `/signup`)
- `/trips/` (Django template URLs when `LOVABLE_FRONTEND_ENABLED=False`)
- `/sitemap.xml`
- `/robots.txt`
- `/google*.html` (site verification)
- `/assets/...` (built frontend static assets)
- `/u/<username>/` (public profile — Django view, not SPA route)
- Any root-level static artifacts (favicon, manifest)

---

## Step 4 — Extract all mock/fake/placeholder patterns from the frontend

> **Again: read the actual current files. Do not assume the mock is identical to the baseline.**

Re-read `lovable/src/lib/devMock.ts` and `lovable/src/data/mockData.ts`:

```bash
grep -rn "import\|from" lovable/src/lib/devMock.ts
grep -rn "import\|from" lovable/src/data/mockData.ts
```

Produce a fresh list of:

- Every URL pattern handled by `resolveMockRequest()` in `devMock.ts` (the `/__devmock__/...` paths it dispatches on)
- Every hardcoded value in `devMock.ts` that simulates a real Django response (auth state, user fields, trip shapes, etc.)
- Every data fixture in `mockData.ts` that shapes what the frontend expects from Django (trip fields, user fields, blog fields)
- Any new mock patterns present in the current `devMock.ts` that are absent from the baseline

Write a **Mock diff summary** (new mock patterns vs baseline, removed mock patterns vs baseline).

---

## Step 5 — Connect every mock pattern to its exact Django replacement

For every mock pattern found in Step 4:

1. Identify the Django view and response shape that serves the real equivalent.
2. Verify the view exists in `frontend/urls.py` and `frontend/views.py`.
3. Verify the response shape matches what `lovable/src/types/api.ts` declares (all required fields present, correct types, snake_case names throughout).
4. If a Django view is missing or its response shape is wrong → fix it now.

### 5a. The mock bypass mechanism

The production build excludes `devMock.ts` and the fixture data from the bundle via two Vite aliases in `frontend_spa/vite.production.config.ts`:

```ts
"@/lib/devMock"   → frontend_spa/src/lib/devMockStub.ts   // stubs resolveMockRequest
"@/data/mockData" → frontend_spa/src/data/mockDataStub.ts  // stubs ApplicationQuestion types
```

In production, `IS_DEV_MODE` is always `false` because `window.TAPNE_RUNTIME_CONFIG` is defined (Django injects it before the bundle executes). This means all `if (IS_DEV_MODE)` branches are dead code and the real `fetch()` calls are used.

Verify:
- The `@/lib/devMock` alias `find` value in `vite.production.config.ts` matches the exact import path used in `lovable/src/lib/api.ts`.
- The `@/data/mockData` alias `find` value matches the exact import path used in `lovable/src/pages/CreateTrip.tsx` (and any other pages that import from mockData).
- If Lovable changed either import path, update the alias `find` value in `frontend_spa/vite.production.config.ts` now (this file is outside `lovable/`, so edits are allowed).

### 5b. Baseline mock-to-Django map (for reference — not the authoritative extraction)

See the **Baseline Reference** section at the bottom of this skill.

### 5c. Runtime config injection — verify it covers every new api key

`_frontend_shell_html()` in `frontend/views.py` injects:

```html
<script data-tapne-runtime="inline-config">
  window.__TAPNE_FRONTEND_CONFIG__ = {...};
  window.TAPNE_RUNTIME_CONFIG = window.__TAPNE_FRONTEND_CONFIG__;
</script>
```

`_runtime_config_payload()` in `frontend/views.py` must include an `api` key for every entry in `TapneRuntimeConfig.api` (from `lovable/src/types/api.ts`). If a new api key was added to the TypeScript type but is missing from `_runtime_config_payload()`, add it now — even if the endpoint is deferred (use a placeholder path like `/frontend-api/<resource>/`).

---

## Step 6 — Identify gaps, fix in Django, write Lovable prompt only if showstopper

Run these verification checklists in order. Fix each failure before moving to the next.

### Checklist A — All extracted routes have both SPA router entries and Django entrypoints

For every route in `lovable/src/App.tsx` marked ✗ in Step 3 → confirm the fix was applied:
- `frontend_spa/src/App.tsx` has a matching `<Route>`
- `frontend/urls.py` has a matching SPA shell URL pointing at `frontend_entrypoint_view`

### Checklist B — All API calls resolve to a Django endpoint

For every call site marked ✗ in Step 3 → confirm the Django URL+view was added.

### Checklist C — TapneRuntimeConfig.api keys all present in _runtime_config_payload()

Compare `TapneRuntimeConfig.api` keys against `_runtime_config_payload()["api"]` in `frontend/views.py`. Every key in the TypeScript interface must be present in the Django payload. Flag and add any missing ones.

### Checklist D — Response shapes match TypeScript contracts

> **This checklist applies to EVERY endpoint — not just new ones. Existing endpoints can be broken from day one. Do not skip any row in the interface table.**

For every interface in **all** lovable type files (`api.ts`, `messaging.ts`, any others found in Step 2) that Django must produce:

**Required verification method — do not shortcut:**

1. Read the TypeScript interface field-by-field.
2. Read the actual Django view function body (or the builder it calls) and find the `return` / `JsonResponse(...)` statement.
3. For every required TypeScript field, confirm the exact field name appears in the Django return dict.
4. For array fields (`participants`, `messages`, `threads`, etc.) confirm each element of the array also satisfies the nested interface — read the inner builder or loop body.

Failure conditions — any of these is a ✗:
- A required TypeScript field is absent from the Django return dict entirely
- A required array field is present but elements have different field names (e.g. Django returns `created_at`, TypeScript expects `sent_at`)
- A required array field is missing from the Django response (e.g. TypeScript says `messages: MessageData[]` but Django omits `messages` key or returns `message_count` instead)
- Field names are camelCase in Django (Tapne uses snake_case throughout — no conversion)
- A non-optional field can be `None`/missing in certain code paths

If ANY field is wrong: fix the Django view now. Do not move to the next checklist item until fixed.

### Checklist E — Build and artifact

Run the production build:

```powershell
pwsh -File infra/build-lovable-production-frontend.ps1
```

Verify:
- [ ] Build exits 0
- [ ] `artifacts/lovable-production-dist/index.html` exists
- [ ] No `/__devmock__/` URLs remain in the bundle (confirms mock bypass aliases worked)
- [ ] No `IS_DEV_MODE` branches with real fetch logic remain active (dead code eliminated by bundler)

Check for devmock URLs in the built bundle:
```bash
grep -r "__devmock__" artifacts/lovable-production-dist/ | grep -v "node_modules"
```
Any match is a failure — the mock bypass alias did not apply.

Also check that `TAPNE_RUNTIME_CONFIG` is referenced (confirms production mode detection):
```bash
grep -r "TAPNE_RUNTIME_CONFIG" artifacts/lovable-production-dist/ || echo "not found in bundle"
```

### Checklist F — Live shell verification

```bash
python manage.py runserver 0.0.0.0:8000
```

For every SPA-owned page route found in Step 2a:
- [ ] `GET <route>` returns 200 with `data-tapne-runtime="inline-config"` in the HTML
- [ ] The injected `window.__TAPNE_FRONTEND_CONFIG__` contains an `api` key for every `TapneRuntimeConfig.api` key

For every Django API endpoint found in Step 2d:
- [ ] Returns valid JSON with the expected shape

Plus:
- [ ] `GET /health/` returns `{"status": "ok", ...}`
- [ ] `GET /admin/` is not accidentally shadowed by the SPA
- [ ] `GET /u/<username>/` is handled by Django, not the SPA shell
- [ ] `GET /runtime/health/` returns `{"status": "ok"}`

---

### Fix protocol for gaps found in Step 6

1. Missing Django view → add to `frontend/views.py` + `frontend/urls.py`
2. Missing api key in runtime config → add to `_runtime_config_payload()["api"]` in `frontend/views.py`
3. Missing response field → add to the relevant Django model method or builder function in the appropriate app (`trips/`, `blogs/`, `accounts/`, `enrollment/`, `interactions/`, etc.)
4. Missing SPA entrypoint URL → add to `frontend/urls.py` under the `if settings.LOVABLE_FRONTEND_ENABLED:` block, pointing at `views.frontend_entrypoint_view`
5. Missing SPA router entry → add to `frontend_spa/src/App.tsx`
6. Wrong Vite alias → fix in `frontend_spa/vite.production.config.ts`
7. Use `DjangoJSONEncoder` for all JSON responses — never raw `json.dumps`
8. **Response returns data but view passes through a Django TypedDict with different field names** → build the response shape inline in the view, field by field, mapping Django names to TypeScript names. Do NOT spread a Django TypedDict directly if its field names differ from what the TypeScript interface declares.
9. **Django view returns `trip` but context expects `draft`** → check the key name in the `JsonResponse` matches exactly what the frontend destructures (e.g. `data.draft` vs `data.trip`).
10. **Django view returns only one tab's trips** → if the frontend fetches once and filters all tabs client-side, the view must return ALL trips (drafts + published + past) in a single response. Check `MyTrips.tsx` and `DraftContext.tsx` for how many fetches they make.
11. **Missing `frontend-api/profile/<id>/` endpoint** → `Profile.tsx` calls `${cfg.api.base}/profile/${profileId}/` which does NOT go through a named `cfg.api.*` key. This URL must be registered in `frontend/urls.py` and handled by a view. Check every `cfg.api.base` interpolation — they are invisible to the api-key audit.
12. Re-run the build after every fix

---

### When to write a Lovable prompt

Only write a Lovable prompt if ALL of the following are simultaneously true:

1. A required behavior exists in the **rendered frontend** (not just mock/dev code)
2. That behavior cannot be correctly served by fixing the Django views, `_runtime_config_payload()`, or `frontend_spa/vite.production.config.ts`
3. The mismatch causes a visible user-facing failure on a production route

If this condition is met, write exactly one prompt covering all showstoppers found. Format:

```
CONTEXT: [one sentence describing what changed in Lovable]
PROBLEM: [exact symptom the user sees in the browser]
REQUIRED CHANGE: [minimal, concrete change needed in the Lovable frontend]
DO NOT CHANGE: [list what must remain exactly as-is]
```

Keep the prompt under 200 words. Do not mention Django internals, file paths outside `lovable/`, or implementation details that Lovable cannot act on.

---

## Reporting when done

1. HEAD SHAs after pull (Django repo + lovable submodule)
2. Diff summary from Step 2 — new/removed routes, api keys, call patterns, Django endpoints
3. For each new item: how it was connected (new Django view, new api key in runtime config, new router entry, or existing handler confirmed sufficient)
4. Build artifact status (clean / what was found in devmock check)
5. Live shell verification results (pass/fail per route and per API endpoint)
6. Lovable prompt text if written, or "No Lovable prompt needed — all gaps resolved from Django side"

---

## Key file map (verify after each pull — paths are stable but content may change)

| Purpose | Path |
|---|---|
| Lovable source router | `lovable/src/App.tsx` |
| TypeScript API contracts | `lovable/src/types/api.ts` |
| Dev mode detection | `lovable/src/lib/mode.ts` |
| API client (fetch wrapper + IS_DEV_MODE branches) | `lovable/src/lib/api.ts` |
| Mock request handler | `lovable/src/lib/devMock.ts` |
| Mock data fixtures | `lovable/src/data/mockData.ts` |
| Bootstrap entry | `lovable/src/main.tsx` |
| Auth + session API calls | `lovable/src/contexts/AuthContext.tsx` |
| Trip draft API calls | `lovable/src/contexts/DraftContext.tsx` |
| Production router (mirrors Lovable routes) | `frontend_spa/src/App.tsx` |
| Production API client | `frontend_spa/src/lib/api.ts` |
| Runtime config types | `frontend_spa/src/lib/config.ts` |
| Mock bypass stub (devMock) | `frontend_spa/src/lib/devMockStub.ts` |
| Mock data stub (ApplicationQuestion types) | `frontend_spa/src/data/mockDataStub.ts` |
| External Vite config (alias overrides) | `frontend_spa/vite.production.config.ts` |
| Build script | `infra/build-lovable-production-frontend.ps1` |
| Django URL routing (frontend + SPA entrypoints) | `frontend/urls.py` |
| Django views, runtime config injection | `frontend/views.py` |
| Root URL conf | `tapne/urls.py` |
| Feature flags | `tapne/settings.py` (`LOVABLE_FRONTEND_ENABLED`, `LOVABLE_FRONTEND_REQUIRE_LIVE_DATA`, `LOVABLE_FRONTEND_DIST_DIR`) |
| Built artifact | `artifacts/lovable-production-dist/` |

---

## Baseline reference

> These tables record the state as of the April 2026 cutover work.
> They exist to speed up the Step 2 diff — they are NOT the authoritative extraction.
> Always produce fresh tables from the current files first; then compare against these.

### Routes (April 2026 baseline)

**lovable/src/App.tsx routes:**

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

---

### TapneRuntimeConfig.api keys (April 2026 baseline)

| Key | Django endpoint | Primary HTTP methods | Notes |
|---|---|---|---|
| `base` | `/frontend-api` | — | URL prefix, not a direct endpoint |
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
| `messages` | `/frontend-api/messages/` | — | Deferred — not yet called by any page |
| `trip_chat` | `/frontend-api/trip-chat/` | — | Deferred — not yet called by any page |

**Additional endpoints not accessed via a named api key (use `cfg.api.base` prefix):**

| URL shape | HTTP | Used in | Django view | Notes |
|---|---|---|---|---|
| `/frontend-api/profile/{id}/` | GET | `Profile.tsx` | `profile_detail_api_view` | `${cfg.api.base}/profile/${profileId}/` — profile_id is username OR numeric id |
| `/frontend-api/profile/{username}/follow/` | POST, DELETE | `Profile.tsx` | *(deferred)* | Follow/unfollow |
| `/frontend-api/hosting-requests/{id}/decision/` | POST | `ManageTrip.tsx`, `ApplicationManager.tsx` | `hosting_decision_api_view` | `{ decision }` |

> **Warning:** These `cfg.api.base` patterns are NOT in `TapneRuntimeConfig.api` and do NOT appear in the api-key audit. Run a dedicated grep for `cfg.api.base` every run to catch them.

---

### Django URL → view map (April 2026 baseline)

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

**SPA entrypoint routes (all → `frontend_entrypoint_view`):**

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
| `re_path r"^.*$"` (catch-all in tapne/urls.py) | `spa-catchall` |

---

### Mock patterns (April 2026 baseline)

| Mock pattern in devMock.ts | Django replacement |
|---|---|
| `GET /__devmock__/session/` | `session_api_view` → `SessionResponse` shape |
| `POST /__devmock__/auth/login/` hardcoded user | `auth_login_api_view` → `request.user` |
| `POST /__devmock__/auth/signup/` | `auth_signup_api_view` |
| `GET /__devmock__/home/` fixture trips/blogs | `home_api_view` → `HomeResponse` |
| `GET /__devmock__/trips/` mock trip list | `trip_list_api_view` → `TripListResponse` |
| `GET /__devmock__/trips/{id}/` | `trip_detail_api_view` → `TripDetailResponse` |
| `POST /__devmock__/trips/drafts/` | `trip_draft_create_api_view` |
| `GET,PATCH /__devmock__/trip-drafts/{id}/` | `trip_draft_detail_api_view` |
| `POST /__devmock__/trip-drafts/{id}/publish/` | `trip_draft_publish_api_view` |
| `GET /__devmock__/my-trips/` | `my_trips_api_view` → `MyTripsResponse` |
| `GET /__devmock__/blogs/` fixture blogs | `blog_list_api_view` |
| `GET,POST,PATCH,DELETE /__devmock__/blogs/{slug}/` | `blog_detail_api_view` |
| `GET,PATCH /__devmock__/accounts/me/` | `my_profile_api_view` |
| `GET /__devmock__/bookmarks/` | `bookmarks_api_view` |
| `POST,DELETE /__devmock__/bookmarks/{id}/` | `bookmark_trip_api_view` |
| `GET /__devmock__/activity/` | `activity_api_view` |
| `GET /__devmock__/settings/` | `settings_api_view` |
| `GET /__devmock__/hosting/inbox/` | `hosting_inbox_api_view` |
| `GET /__devmock__/dm/inbox/` | `dm_inbox_api_view` |
| `POST /__devmock__/dm/inbox/{id}/messages/` | `dm_send_message_api_view` |
| `GET,POST /__devmock__/manage-trip/{id}/` | `manage_trip_api_view` + action views |
| `POST /__devmock__/hosting-requests/{id}/decision/` | `hosting_decision_api_view` |
| `mockData.ts` trip fixtures (10–20 trips with full TripData shape) | `Trip` model via `build_trip_list_payload_for_user()` etc. |
| `mockData.ts` user fixtures | `User` + `AccountProfile` via `_member_identity_payload()` |
| `IS_DEV_MODE = window.TAPNE_RUNTIME_CONFIG === undefined` | Django injects `window.TAPNE_RUNTIME_CONFIG` → always `false` in production |

---

### Known hardcoded mock/placeholder patterns that are NOT in devMock.ts

These are baked into component source files and require Lovable prompts — they cannot be fixed from the Django side:

| Location | Hardcoded value | Required fix |
|---|---|---|
| `Navbar.tsx` (top-level `const notifications = [...]`) | 3 fake notification items always shown | Lovable prompt: fetch from `cfg.api.notifications`; remove hardcoded array |
| `LoginModal.tsx` `handleGoogleAuth` | Calls `login("google@tapne.com","google")` — fake credentials | Lovable prompt: check `cfg.google_oauth_url`; if truthy `window.location.href = cfg.google_oauth_url + "?next=" + encodeURIComponent(window.location.pathname)`; if falsy hide the Google button and divider |
| `HeroSection.tsx` stats fallbacks | `"3,000+"` / `"120+"` / `"50+"` shown when `stats` prop is `undefined` | Django fix: always return `stats` key from `home_api_view` (never omit it) |
| `CreateTrip.tsx` `handleSaveDraft` | Shows "Draft saved!" toast even when `draftId == null` (unauthenticated) | Lovable prompt: guard toast behind `draftId != null && isAuthenticated` |

For each entry in this table:
- If the fix is "Django fix" → apply it from the Django side now.
- If the fix is "Lovable prompt" → add it to the Lovable prompt written in Step 6 (only if it causes a visible user-facing failure).

### Key TypeScript interfaces to verify against Django responses (April 2026 baseline)

Tapne uses **snake_case** throughout — Django and TypeScript both use snake_case field names. There is no camelCase conversion. For any new field Lovable adds to a TypeScript interface, the Django view must return a field with exactly the same snake_case name.

| TypeScript interface | Source file | Django view / builder | Critical array fields to verify |
|---|---|---|---|
| `SessionUser` | `api.ts` | `_session_user_payload()` in `frontend/views.py` | — |
| `SessionResponse` | `api.ts` | `session_api_view` | — |
| `TripData` | `api.ts` | `Trip.to_trip_data()` + `enrich_trip_preview_fields()` | `highlights`, `itinerary_days`, `faqs` |
| `TripDetailResponse` | `api.ts` | `trip_detail_api_view` | `similar_trips[]` must be `TripData` |
| `TripListResponse` | `api.ts` | `trip_list_api_view` | `trips[]` must be `TripData` |
| `MyTripsResponse` | `api.ts` | `my_trips_api_view` via `build_my_trips_payload_for_member()` | `trips[]` must be `TripData` |
| `ManageTripResponse` | `api.ts` | `manage_trip_api_view` | `participants[]`, `applications[]` |
| `BlogData` | `api.ts` | `blog_list_api_view` / `blog_detail_api_view` | `tags[]` |
| `HomeResponse` | `api.ts` | `home_api_view` via `build_home_payload_for_user()` | `community_profiles[]`, `testimonials[]` |
| `EnrollmentRequestData` | `api.ts` | `hosting_inbox_api_view` via `build_hosting_inbox_payload_for_member()` | — |
| `TapneRuntimeConfig` | `api.ts` | `_runtime_config_payload()` in `frontend/views.py` | `api{}` must have every key in the TS interface |
| `ProfileResponse` | inline in `Profile.tsx` | `profile_detail_api_view` | `profile{}`, `trips_hosted[]`, `trips_joined[]`, `reviews[]`, `gallery[]` — note: `HomeFeedPayload.profiles` (feed/models.py `ProfileData`) does NOT have `display_name`/`location` fields — `_enrich_profile_cards()` adds them |
| `CommunityProfile` | `api.ts` | `home_api_view` (built inline, not from `HomeFeedPayload.profiles` directly) | fields: `username`, `display_name`, `bio`, `location`; `HomeFeedPayload` uses `ProfileData` which lacks `display_name` — must be remapped via `_enrich_profile_cards()` |
| `HomeResponse.stats` | `api.ts` | `home_api_view` | `{ travelers, trips_hosted, destinations }` — must come from real DB counts, NOT hardcoded fallbacks. `HeroSection` shows fallback values `"3,000+"/"120+"/"50+"` when `stats` is undefined/null — Django must always return this key |
| `HomeResponse.testimonials` | `api.ts` | `home_api_view` | `TestimonialData[]` — return `[]` if no testimonials model; `TestimonialsSection` hides itself when empty |
| `HomeResponse.community_profiles` | `api.ts` | `home_api_view` | `CommunityProfile[]` — `CommunitySection` hides itself when empty; must be non-null array |
| `InboxResponse` | **`messaging.ts`** | `dm_inbox_api_view` (custom builder in `frontend/views.py`) | `threads[]` must be `ThreadData` |
| `ThreadData` | **`messaging.ts`** | built inline in `dm_inbox_api_view` | `participants[]` (username+display_name), `messages[]` (MessageData) |
| `MessageData` | **`messaging.ts`** | built inline in `dm_inbox_api_view` message loop | fields: `id`, `thread_id`, `sender_username`, `sender_display_name`, `body`, `sent_at` |

> **Warning:** `messaging.ts` types are NOT in `api.ts`. They are imported directly by `Inbox.tsx`. If you only check `api.ts` you will miss all DM/messaging shape requirements.
>
> **Warning:** Django's `DMThreadPreviewData` TypedDict in `interactions/models.py` has a **different shape** from TypeScript's `ThreadData`. The `dm_inbox_api_view` must NOT pass `DMThreadPreviewData` through to the frontend — it must build the `ThreadData` shape explicitly. The field mapping is:
> - `peer_username` / `peer_url` → NOT equivalent to `participants[]` array
> - `last_message_preview` → frontend field name is `last_message`
> - `last_message_at` → frontend field name is `last_sent_at`
> - `message_count` → frontend expects `messages[]` array, not a count
> - Missing from Django model: `type`, `title`, `participants[]`, `unread_count`
