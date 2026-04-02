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

## 9. Closing standard

Do not close the task until all of these are true:

- artifact verification passes
- live verification passes
- the public root route is healthy after deploy
- the shell is safe for authenticated users
- recent Cloud Run logs show no ongoing `500` requests on the active revision
