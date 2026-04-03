# Operational Hardening

Use this file when the public cutover technically exists but can still fail in production because of deployment, shell bootstrap, or verification gaps.

## 1. Inline runtime config is the safer default

Prefer an inline runtime payload in the served HTML shell over a second blocking request to `/frontend-runtime.js`.

Why:

- a separate runtime script adds another production dependency before React can boot
- if that request returns HTML or `500`, the app can blank-screen before the main bundle hydrates
- inline config keeps the bootstrap path inside the single root document response

For this repo, the hardened shell should:

- inject `window.__TAPNE_FRONTEND_CONFIG__` inline
- include `data-tapne-runtime="inline-config"`
- avoid depending on `/frontend-runtime.js` in the served root HTML

If a runtime JS endpoint still exists for diagnostics or backward compatibility, the public shell should not depend on it.

## 2. Server-rendered bootstrap JSON must be Django-safe

Do not serialize runtime/bootstrap/session payloads for the SPA shell with raw `json.dumps(...)` if they can contain Django-native values such as:

- `datetime`
- `date`
- `Decimal`
- lazily-evaluated or non-plain values pulled from model payload helpers

Use Django-safe serialization for shell bootstrap JSON, for example:

- `DjangoJSONEncoder`
- or a stricter explicit normalization pass before serialization

This matters most on routes that inline authenticated session state. A shell that works for anonymous users can still `500` for signed-in users if the bootstrap payload is not serializable.

## 3. The root shell must be tested in authenticated mode

Do not rely only on API tests or signed-out shell checks.

Add at least one regression test that:

- renders the SPA shell through the Django entrypoint
- attaches an authenticated user to the request
- includes real persisted rows that surface datetimes or related payloads
- asserts the HTML response is `200`

This catches the exact class of failure where:

- `/frontend-api/session/` works
- `/runtime/health/` works
- but `/` still returns `500`

## 4. Artifact verification and live verification are different

Treat these as separate checks:

### Artifact verification

Run against the emitted frontend build directory.

It should confirm:

- banned mock/local-only markers are absent
- shell markers like brand CSS are present
- the artifact does not hard-code `/frontend-runtime.js` as a required dependency

It cannot prove that the live Django shell is injecting runtime config correctly.

### Live verification

Run against the deployed domain.

It should confirm:

- `/` returns `200 text/html`
- root HTML contains inline runtime config
- root HTML does not reference `/frontend-runtime.js`
- `/frontend-api/session/` returns `200`
- `/runtime/health/` returns `200`
- referenced frontend assets return `200`

For this repo, use:

```powershell
python skills/lovable-django-production-cutover/scripts/verify_live_cutover.py ^
  --base-url https://tapnetravel.com/
```

## 5. Smoke tests must include the public root route

Health/static checks alone are insufficient.

Post-deploy smoke should include:

- `/`
- `/frontend-api/session/`
- `/runtime/health/`
- at least one frontend asset referenced by the root HTML

If the site serves an SPA shell, this is the minimum acceptable post-deploy surface.

## 6. Query Cloud Run for actual `500` requests

If the browser only reports a generic `500`, check request logs directly instead of guessing.

Useful pattern:

```powershell
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=tapne-web AND httpRequest.status=500" ^
  --project tapne-487110 ^
  --limit 20 ^
  --format=json
```

Use this to determine:

- whether the failure is current or stale
- which path is failing
- which revision served the failure
- whether the issue is request-specific

## 7. PowerShell workflow scripts must stay Windows-compatible

This repo uses PowerShell deployment scripts from Windows environments. Do not assume PowerShell 7 behavior.

Specifically:

- do not rely on `ConvertFrom-Json -Depth` in Windows PowerShell 5.1
- if you need depth-tolerant parsing, use a compatibility helper
- be careful with switch/boolean forwarding between orchestrator scripts and nested scripts
- do not pass disabled switches as `-SomeSwitch:False` if the downstream binding is fragile

When fixing orchestration, verify the full chain:

- `run-cloud-run-workflow.ps1`
- `setup-custom-domain.ps1`
- `deploy-cloud-run.ps1`

## 8. Immutable `lovable/` does not mean the build must be fragile

If `lovable/package-lock.json` is out of sync with `lovable/package.json`, do not “fix” that by editing tracked files under `lovable/`.

Use a disposable install strategy in the external build path, for example:

- install from `package.json` in the builder stage
- disable lockfile writes in that disposable environment
- keep the repo-owned build logic outside `lovable/`

The rule is:

- no source edits under `lovable/`
- but the production build must still be reproducible

## 9. App.tsx override integrity check

Before building, verify `frontend_spa/src/App.tsx` against `lovable/src/App.tsx`:

```bash
# Every page import in frontend_spa/src/App.tsx must come from @/pages/* (Lovable source).
# The only permitted @frontend/pages/* import is UnderConstructionPage.
grep "from.*@frontend/pages" e:/tapne/frontend_spa/src/App.tsx
```

Expected output: exactly one line — `import UnderConstructionPage from "@frontend/pages/UnderConstructionPage"`.

If any other `@frontend/pages/*` import appears, the page is a custom stripped-down replacement. Replace it with the real Lovable page (`@/pages/<PageName>`). This was the root cause of the wrong-font / no-carousel / no-tabs regression.

Also verify providers are present:

```bash
grep -E "QueryClientProvider|DraftProvider|TooltipProvider" e:/tapne/frontend_spa/src/App.tsx
```

Expected output: both `QueryClientProvider` and `DraftProvider` must appear. If either is missing, add it — missing providers cause silent runtime failures on all pages.

## 11. No Django templates for browser users

Before closing, confirm that no Django view is still rendering an HTML template for a browser-navigable URL.

Quick audit pattern:
```bash
grep -rn "render(request" accounts/views.py trips/views.py blogs/views.py \
  enrollment/views.py interactions/views.py reviews/views.py \
  activity/views.py settings_app/views.py social/views.py search/views.py \
  feed/views.py
```

Every hit must be either:
- a `backend-only` endpoint (returns JSON, processes form POST, or is `/admin/`), OR
- already replaced by a redirect or SPA catch-all

If any hit renders a user-facing HTML template page, it is a cutover blocker.

## 12. Visual parity check for tokens.css

After injecting `tokens.css` into the SPA shell, visually compare:

- a Lovable page rendered in standalone `vite dev` mode (no Django shell injection)
- the same page rendered through the Django SPA shell with `tokens.css` injected

They must look identical. If any color, font, radius, or spacing is different, the `tokens.css` values have drifted from `lovable/src/index.css` — fix them to match exactly. Do not alter `overrides.css` to compensate for wrong `tokens.css` values.

## 13. Under Construction page visual check

The "Under Construction" page served by the `*` catch-all must:

- render the Lovable Navbar and Footer
- use the same background color, text color, and font as other Lovable pages
- not show any error, stack trace, Django debug page, or blank screen
- be reachable by directly navigating to a URL like `/about/` or `/settings/` in a fresh browser session

## 14. Closing standard

Do not close the task until all of these are true:

- artifact verification passes
- live verification passes
- the public root route is healthy after deploy
- the shell is safe for authenticated users
- recent Cloud Run logs show no ongoing `500` requests on the active revision
- no Django HTML template is served for any browser-navigable URL
- `tokens.css` values match `lovable/src/index.css` exactly — visual appearance is unchanged
- `overrides.css` is empty of visual rules (no `font-family`, no `!important` border-radius or shadow overrides)
- the Under Construction page renders correctly for unclaimed URLs and looks visually consistent with the rest of the app
- `frontend_spa/src/App.tsx` page imports verified: all from `@/pages/*`, only `UnderConstructionPage` from `@frontend/pages/*`
- `frontend_spa/src/App.tsx` provider tree verified: `QueryClientProvider`, `DraftProvider`, `TooltipProvider`, both `Toaster`s present
- `frontend/urls.py` parameterised route patterns verified with Django URL resolver
