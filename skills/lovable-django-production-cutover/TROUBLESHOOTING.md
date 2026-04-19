# Troubleshooting And Verification Gates

This file preserves the original troubleshooting intent while moving it out of
the main operator runbook.

Use this file when:

- a route, endpoint, or runtime config key is missing
- response shapes drift from TypeScript
- auth, CSRF, router, or provider behavior breaks
- the production shell renders but the browser still fails
- you need to decide whether a problem is Django-fixable or a true Lovable showstopper

## Gap Fix Protocol

Apply fixes in this order:

1. missing Django view -> add it in `frontend/views.py` and `frontend/urls.py`
2. missing runtime config api key -> add it to `_runtime_config_payload()["api"]`
3. missing response field -> fix the relevant Django builder/model/view
4. missing SPA entrypoint URL -> add it to `frontend/urls.py`
5. missing SPA router entry -> add it to `frontend_spa/src/App.tsx`
6. wrong Vite alias -> fix `frontend_spa/vite.production.config.ts`
7. always use `DjangoJSONEncoder` for JSON responses
8. if Django TypedDict field names differ from TypeScript field names, build the response shape explicitly instead of passing the TypedDict through
9. if the frontend expects `draft` but Django returns `trip`, fix the response key name
10. if the frontend fetches once and filters client-side, the backend must return the full set the client expects
11. audit `cfg.api.base` interpolations separately; they do not appear in the api-key audit
12. re-run the production build after every fix

## Auth-Gate And Unauthenticated-State Audit

For every page or context that makes API calls, determine:

1. whether the frontend auth-gates before firing the request
2. what happens if the request still fires unauthenticated
3. whether Django returns `_member_only_error()` before any protected DB access

Check these known hot spots every run:

| Component | Risk | Expected behavior |
|---|---|---|
| `CreateTrip.tsx` | `createDraft()` may fire before auth hydrates | 401 path must not still show success UI |
| `DraftContext.tsx` | may depend on frozen bootstrap auth | should depend on live auth state |
| `Inbox.tsx` | may assume authenticated array shapes | unauthenticated path must not crash |

## Mock Bypass Mechanism

The production build relies on these aliases in `frontend_spa/vite.production.config.ts`:

- `@/lib/devMock` -> `frontend_spa/src/lib/devMockStub.ts`
- `@/data/mockData` -> `frontend_spa/src/data/mockDataStub.ts`

Every run, verify the alias targets still match the current import paths used by
the Lovable source. If Lovable changed the import path, update the Vite alias.

If a new `TapneRuntimeConfig.api` key exists in the TypeScript contract but the
backend implementation is still being wired, add a placeholder runtime-config
path like `/frontend-api/<resource>/` immediately so the contract remains
complete, then finish the backend endpoint work.

## Acceptance Gates

### Checklist A - Route parity and entrypoints

For every route extracted from `lovable/src/App.tsx`:

- `frontend_spa/src/App.tsx` has a matching route
- `frontend/urls.py` has a matching SPA shell URL pointing at `frontend_entrypoint_view`

### Checklist B - API call coverage

For every call site extracted from the frontend:

- a concrete Django URL exists
- the correct HTTP method is handled
- the view logic matches the frontend expectation

### Checklist C - Runtime config coverage

Every key in `TapneRuntimeConfig.api` must appear in `_runtime_config_payload()["api"]`.

### Checklist D - Response shape fidelity

Required method:

1. read the TypeScript interface field by field
2. read the Django return shape field by field
3. verify exact field names
4. verify nested arrays and nested objects

Failure conditions:

- required field missing
- nested array element shape mismatched
- Django returns counts or preview fields where the frontend expects full arrays
- camelCase drift
- required fields can be absent or null in some paths

If any field is wrong, fix it before moving on.

### Checklist E - Build artifact

Run:

```powershell
pwsh -File infra/build-lovable-production-frontend.ps1
```

Pass conditions:

- build exits 0
- `artifacts/lovable-production-dist/index.html` exists
- the build does not dirty `lovable/`
- `resolveMockRequest` does not appear in the production bundle
- runtime config references remain in the bundle

Useful checks:

```bash
grep -c "resolveMockRequest" artifacts/lovable-production-dist/assets/*.js
grep -r "TAPNE_RUNTIME_CONFIG" artifacts/lovable-production-dist/ || echo "not found in bundle"
```

### Checklist F - Live shell verification

Run Django locally:

```bash
python manage.py runserver 0.0.0.0:8000
```

Verify:

- each SPA-owned route returns the frontend shell with injected runtime config
- each Django API endpoint returns valid JSON in the expected shape
- `/health/` returns healthy JSON
- `/admin/` is not shadowed by the SPA
- `/u/<username>/` is Django-owned
- `/runtime/health/` returns healthy JSON

### Checklist G - No-op frontend interactions

Read:

- modal components found via `handleSubmit` / `onSubmit`
- contact/message button click handlers
- `DropdownMenuItem` handlers, especially in `Navbar.tsx`

Confirm:

- modals that change state actually make API calls
- DM-start CTAs create the thread before navigating
- notification dropdown items have real click handlers
- auth-sensitive context loads depend on live auth state, not frozen bootstrap state

Any failure here is usually a Lovable showstopper.

### Checklist H - CSRF after modal login

Read `lovable/src/lib/api.ts` and confirm:

- `csrfHeaders()` reads from `document.cookie` using `c.csrf.cookie_name`
- `c.csrf.token` is only a fallback when the cookie row is absent

If the frontend reads the page-load CSRF token directly, POST/PATCH/DELETE calls will fail after modal login.

### Checklist I - Providers that use router hooks

Read `frontend_spa/src/App.tsx` and confirm:

- any provider that calls `useNavigate()`, `useLocation()`, or `useParams()` is rendered inside the router tree
- `DraftProvider` is inside `RootLayout`, not wrapping `<RouterProvider>`

### Checklist J - Real browser render and console gate

Use a real browser, not just `curl`.

Minimum pass conditions:

- `/` renders visible content
- `#root` is not blank
- no `pageerror`
- no `console.error`
- JS bundle is served with a JavaScript MIME type
- no router/provider crash

Hard failures:

- blank screen
- empty `#root`
- uncaught render error
- `console.error`
- JS MIME mismatch
- `useNavigate() may be used only in the context of a <Router> component`
- `useAuth must be used within AuthProvider`

Do not deploy on HTTP-200-only evidence.

## Recurring Failure Patterns

These issues have recurred and must be checked every run.

1. `CreateTrip.tsx` fires draft creation before auth hydrates and then shows success UI anyway.
2. `DraftContext.tsx` or similar contexts read frozen bootstrap auth state instead of live auth state.
3. `Inbox.tsx` or similar consumers assume authenticated array shapes and crash on unauthenticated responses.
4. Modal submit handlers are cosmetic-only: toast plus close, no API call.
5. Navigation-only CTAs should create a server record before navigation, but do not.
6. Dropdown/menu items render without `onClick`.
7. CSRF token becomes stale after modal login.
8. Providers using router hooks wrap `<RouterProvider>`.
9. Legacy `frontend_spa/` components import the wrong AuthContext and crash under Lovable's provider tree.

## Lovable Prompt Boundary

Write a Lovable prompt only when:

1. the required behavior exists in the rendered frontend
2. Django/runtime config/`frontend_spa/` cannot correct it
3. the user sees a visible production failure

Use one prompt only. Keep it concrete and minimal.
