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
- Lovable currently ships mock and local-only behavior in:
  - [lovable/src/data/mockData.ts](e:/tapne/lovable/src/data/mockData.ts)
  - [lovable/src/contexts/AuthContext.tsx](e:/tapne/lovable/src/contexts/AuthContext.tsx)
  - [lovable/src/contexts/DraftContext.tsx](e:/tapne/lovable/src/contexts/DraftContext.tsx)
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

### 2. Define route ownership

Create a route map with three classes:

- `spa-public`: served by the Lovable build on the main domain
- `django-web`: still rendered directly by Django
- `backend-only`: API, admin, upload, auth endpoints, callbacks, health checks

Default target for this repo:

- Public marketing and discovery routes should move to Lovable
- Django should continue to own `/admin`, backend APIs, uploads/media, and operational endpoints
- Any route still dependent on compiled mock behavior stays off production traffic until replaced

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

Keep frontend control in files outside `lovable/`, for example:

- `static/frontend-brand/tokens.css`
- `static/frontend-brand/overrides.css`
- `static/frontend-brand/runtime-config.js`

For this repo, the preferred production shell is:

- inline `window.__TAPNE_FRONTEND_CONFIG__` in the served HTML
- no hard dependency on `/frontend-runtime.js` for the public page bootstrap

Load them into the shipped frontend shell after the Lovable bundle is built:

- `tokens.css`: brand colors, fonts, radii, shadows, spacing variables
- `overrides.css`: targeted class overrides that cannot be expressed purely through variables
- `runtime-config.js`: API base URL, environment flags, auth/bootstrap config

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
- the built artifact no longer contains banned mock/local-only markers
- the built artifact does not require `/frontend-runtime.js` to boot
- the served root HTML includes inline runtime config
- the root route works for both signed-out and signed-in sessions

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
