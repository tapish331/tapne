---
name: lovable-django-production-cutover
description: >
  Executes the Tapne Lovable-to-Django production cutover with the same intent as
  the original skill: refresh lovable/ in place, extract the current frontend
  contract from source, connect every route/API/mock dependency to Django, fix all
  Django-side gaps that are fixable outside lovable/, verify the production build
  and real browser behavior, write one Lovable prompt only for true frontend
  showstoppers, and deploy when the cutover includes deployment.
---

# Lovable to Django Production Cutover

This split is structural only. The operational intent of the original skill MUST
NOT CHANGE.

Use this file as the operator runbook. The companion docs are normative parts of
the skill, not optional notes:

- [BASELINE.md](./BASELINE.md): reference tables and file map
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md): gap protocol, recurring failures, verification gates
- [DEPLOY.md](./DEPLOY.md): Cloud Run workflow and deployment rules

## Hard Rules

1. The only allowed in-place change under `lovable/` is `git -C lovable pull --ff-only`.
2. After that pull completes, `git -C lovable status` must be clean before any further step runs.
3. Do not patch, create, rename, delete, install, build, or normalize line endings anywhere under `lovable/`.
4. Current source is authoritative every run. `BASELINE.md` is reference only.
5. If a gap can be fixed outside `lovable/`, fix it now. Do not defer it into a Lovable prompt.
6. Do not deploy until the production build, live shell checks, and real browser checks all pass.
7. Write exactly one Lovable prompt only when the rendered production behavior is broken and cannot be corrected from Django, runtime config, or `frontend_spa/`.

## Step 1 - Refresh Repos And Require A Clean Lovable Worktree

Run:

```powershell
git pull
git rev-parse HEAD
git -C lovable pull --ff-only
git -C lovable rev-parse HEAD
git -C lovable status
```

Stop immediately if `git -C lovable status` is not clean. Report:

- Django repo SHA after pull
- Lovable SHA after pull
- any dirty paths if the run is blocked

## Step 2 - Extract The Current Frontend Contract From Source

Read these files in full first:

- [lovable/src/App.tsx](../../lovable/src/App.tsx)
- [lovable/src/types/api.ts](../../lovable/src/types/api.ts)
- [lovable/src/types/messaging.ts](../../lovable/src/types/messaging.ts)
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

Then scan:

```bash
grep -rn "from \"@/types/" lovable/src/pages lovable/src/contexts lovable/src/components --include="*.ts" --include="*.tsx" | grep -v "api\|messaging" | sort -u
grep -rn "apiGet\|apiPost\|apiPatch\|apiDelete\|cfg\.api\.\|cfg\.auth\." lovable/src/pages lovable/src/contexts lovable/src/components --include="*.ts" --include="*.tsx"
grep -rn "cfg\.api\.base" lovable/src/pages lovable/src/contexts lovable/src/components --include="*.ts" --include="*.tsx"
```

Any extra type file found by the `@/types/` scan must also be read in full.

Produce four fresh tables from the current source:

1. Route parity: `lovable/src/App.tsx` vs `frontend_spa/src/App.tsx`
2. `TapneRuntimeConfig.api` keys and URL/method usage
3. Distinct frontend API call sites and URL shapes
4. Django URL -> view map from `frontend/urls.py`

Also produce a fresh mock diff summary from current source:

- every URL pattern handled by `resolveMockRequest()` in `devMock.ts`
- every hardcoded value in `devMock.ts` that simulates a server response
- every shape-bearing fixture in `mockData.ts`
- new mock patterns vs baseline
- removed mock patterns vs baseline

After that, write a diff summary against `BASELINE.md`:

- new routes
- new api keys
- new api call patterns
- new Django endpoints
- removed baseline items

If all diffs are none, say so explicitly.

## Step 3 - Connect Every Route, API Call, And Mock Dependency To Django

Read [frontend/urls.py](../../frontend/urls.py) and [frontend/views.py](../../frontend/views.py) in full.

For every extracted frontend dependency:

1. Resolve the concrete URL shape the frontend calls.
2. Find the matching Django URL and view.
3. If it exists and matches, mark it confirmed.
4. If it is missing or wrong, fix it now outside `lovable/`.

This includes:

- named `cfg.api.*` calls
- `cfg.api.base` interpolated URLs
- SPA entrypoint URLs in `frontend/urls.py`
- matching routes in `frontend_spa/src/App.tsx`
- `_runtime_config_payload()` coverage for every `TapneRuntimeConfig.api` key
- mock replacement coverage for every pattern found in `devMock.ts` and `mockData.ts`

Decision rules for new items:

- new route -> matching route in `frontend_spa/src/App.tsx` and matching SPA entrypoint URL in `frontend/urls.py`
- new `TapneRuntimeConfig.api` key -> matching `_runtime_config_payload()` entry and matching Django URL/view
- new call against an existing key at a new URL shape -> new Django URL/view
- new call found in a context or component -> treat it exactly like a page-level call

Also audit auth-gates and unauthenticated behavior for every page or context that
makes API calls:

- verify whether the frontend guards behind `isAuthenticated` or `requireAuth()`
- verify what happens if the call still fires unauthenticated
- verify Django returns `_member_only_error()` before any protected DB work
- explicitly check `CreateTrip.tsx`, `DraftContext.tsx`, and `Inbox.tsx`

Also verify backend-owned routes are not shadowed by the SPA catch-all:

- `/admin/`
- `/health/`
- `/runtime/`
- `/uploads/`
- `/search/`
- `/accounts/login/`
- `/accounts/signup/`
- `/trips/` when the Lovable frontend is disabled
- `/sitemap.xml`
- `/robots.txt`
- `/google*.html`
- `/assets/...`
- `/u/<username>/`
- root-level static artifacts

If you hit a recurring failure pattern, use [TROUBLESHOOTING.md](./TROUBLESHOOTING.md).

## Step 4 - Verify Contracts, Build, Live Shell, And Real Browser Behavior

### 4a. Response shape verification

For every TypeScript interface the frontend expects from Django:

1. Read the interface field by field.
2. Read the actual Django view or builder that returns it.
3. Confirm every required field name exists exactly as declared.
4. Confirm nested arrays and nested objects also match.

Tapne uses snake_case throughout. Do not allow camelCase drift.

Use the interface map and baseline expectations in [BASELINE.md](./BASELINE.md). Use the failure catalog in [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) when shapes or auth/runtime behavior drift.

### 4b. Production build

Run:

```powershell
pwsh -File infra/build-lovable-production-frontend.ps1
```

The build must:

- exit 0
- create `artifacts/lovable-production-dist/index.html`
- keep `git -C lovable status --short` unchanged across the build
- exclude real mock handler execution from the production bundle
- verify the `@/lib/devMock` and `@/data/mockData` aliases still match the current Lovable import paths

### 4c. Live shell verification

Start Django locally and verify:

- every SPA-owned route returns the frontend shell with injected runtime config
- every Django API endpoint returns JSON in the expected shape
- backend-owned routes remain backend-owned

### 4d. Real browser verification

Before any deploy, use a real browser against the local Django server and prove:

- `/` renders visible content
- no blank shell / empty `#root`
- no `pageerror`
- no `console.error`
- no router/provider crash
- JS assets are served with a JavaScript MIME type: `text/javascript` or `application/javascript`
- the app does not crash with errors such as `useNavigate() may be used only in the context of a <Router> component` or `useAuth must be used within AuthProvider`

Do not deploy on HTTP-200-only evidence. Use [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) for the exact browser and incident gates.

## Step 5 - Decide Whether A Lovable Prompt Is Required

Write a Lovable prompt only if all three are true:

1. the required behavior exists in the rendered production frontend
2. the issue cannot be corrected from Django, runtime config, or `frontend_spa/`
3. the mismatch causes a visible user-facing failure

If required, write exactly one prompt in this format:

```text
CONTEXT: ...
PROBLEM: ...
REQUIRED CHANGE: ...
DO NOT CHANGE: ...
```

Keep it under 200 words. Do not mention Django internals or paths outside `lovable/`.

## Step 6 - Deploy When The Cutover Includes Deployment

If the task includes deployment, follow [DEPLOY.md](./DEPLOY.md) exactly.

At minimum, confirm:

- the workflow builds a fresh Lovable production artifact before image build
- smoke test paths are valid for the SPA-era deployment
- any newly required secrets or env vars are wired through the workflow
- the Cloud Run workflow is executed only after Steps 1-5 pass

## Reporting When Done

Report:

1. Django SHA and Lovable SHA after pull
2. Step 2 diff summary
3. how each new item was connected or fixed
4. build artifact result
5. live shell verification result
6. real browser verification result
7. Lovable prompt text, or `No Lovable prompt needed`
8. deployment result and any workflow changes, if deployment was part of the run
