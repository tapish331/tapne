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

## 2. Current Lovable production blockers

### Auth is fake

- [lovable/src/contexts/AuthContext.tsx](e:/tapne/lovable/src/contexts/AuthContext.tsx)

Current behavior:

- login waits, then logs in the first mock user
- signup creates an in-memory user only
- profile edits only mutate local React state

Production implication:

- Lovable cannot be used as-is for real auth or profile state.

### Drafts are local-only

- [lovable/src/contexts/DraftContext.tsx](e:/tapne/lovable/src/contexts/DraftContext.tsx)

Current behavior:

- drafts are read from and written to `localStorage`
- publish only changes local draft state

Production implication:

- create-trip and my-trips draft behavior is not a real backend flow.

### Core catalogs and detail pages read mock data

- [lovable/src/data/mockData.ts](e:/tapne/lovable/src/data/mockData.ts)
- imports across:
  - [lovable/src/pages/Index.tsx](e:/tapne/lovable/src/pages/Index.tsx)
  - [lovable/src/pages/BrowseTrips.tsx](e:/tapne/lovable/src/pages/BrowseTrips.tsx)
  - [lovable/src/pages/TripDetail.tsx](e:/tapne/lovable/src/pages/TripDetail.tsx)
  - [lovable/src/pages/MyTrips.tsx](e:/tapne/lovable/src/pages/MyTrips.tsx)
  - [lovable/src/pages/Profile.tsx](e:/tapne/lovable/src/pages/Profile.tsx)
  - [lovable/src/components/TripCard.tsx](e:/tapne/lovable/src/components/TripCard.tsx)
  - [lovable/src/components/BookingModal.tsx](e:/tapne/lovable/src/components/BookingModal.tsx)
  - [lovable/src/components/ApplicationModal.tsx](e:/tapne/lovable/src/components/ApplicationModal.tsx)
  - [lovable/src/components/ApplicationManager.tsx](e:/tapne/lovable/src/components/ApplicationManager.tsx)

Production implication:

- home, trips, trip detail, profile, booking, and application flows are not yet real.

### Route shell is frontend-only

- [lovable/src/App.tsx](e:/tapne/lovable/src/App.tsx)

Current behavior:

- BrowserRouter owns public routes entirely inside the SPA
- no built-in integration with Django route ownership or backend state bootstrap

Production implication:

- deployment needs a proper SPA fallback and route split strategy.

## 3. Good news for cutover

### Theme variables already exist

- [lovable/src/index.css](e:/tapne/lovable/src/index.css)

This means centralized external control is feasible through injected CSS variables and override styles without editing source files under `lovable/`.

### The app can be built independently

- [lovable/package.json](e:/tapne/lovable/package.json)

This enables:

- external build outputs
- post-build transforms outside `lovable/`
- separate packaging and deploy integration

## 4. What “production and actual” means in this repo

For this cutover, a route is not production-ready unless:

- the frontend route is served from the real domain
- reads are backed by Django data
- writes hit Django endpoints and persist
- auth is real
- reload/deep-link behavior works
- there is no reliance on in-memory or local-only state for the system of record

## 5. Cutover mindset

Do not ask “can the Lovable page be shown?” Ask:

- is the route browser-accessible on the real domain?
- is all displayed data real?
- do actions persist?
- is the frontend shell controllable outside `lovable/`?
- can the route survive a hard refresh and a new browser session?

## 6. Important upgrade to the strategy

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

## 7. Operational blind spots to avoid repeating

These are not Lovable source blockers, but they are real cutover blockers if left unchecked:

- a deploy can pass health/static smoke checks while `/` still fails
- a shell can work for signed-out users and `500` for signed-in users if inline runtime JSON is not serialized safely
- an artifact can look correct while the live domain still fails because runtime/bootstrap injection was not verified after deploy
- PowerShell deploy scripts can fail in Windows environments if they assume `ConvertFrom-Json -Depth` support or fragile switch forwarding

Treat these as part of production readiness, not postscript cleanup.
