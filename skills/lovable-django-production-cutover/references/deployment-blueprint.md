# Deployment Blueprint

Use this blueprint when moving from Django-rendered public pages to a Lovable-fronted production site.

## 1. Build strategy

Do not treat immutable Lovable source files as a reason to give up on real frontend behavior.

Preferred order for this repo:

1. external source-override build
2. shell/runtime injection
3. post-build artifact transforms

The cleanest path is to replace specific fake Lovable modules at build time through an external Vite alias map that points to replacement modules outside `lovable/`.

Do not treat `lovable/` as the deploy artifact location.

Recommended:

```powershell
pwsh -File infra/build-lovable-production-frontend.ps1
```

Why:

- avoids editing or patching files under `lovable/`
- gives you a disposable frontend artifact that can be wrapped, transformed, tested, and copied into the final image
- allows an external override build config to replace fake modules before the final artifact is emitted

## 2. Source-override build pattern

Use this as the default integration pattern when the original Lovable source imports fake contexts, fake data modules, or local-only state.

Mechanics:

- keep `lovable/` source untouched
- create replacement modules outside `lovable/`
- use an external Vite config outside `lovable/`
- alias specific Lovable source paths to replacement modules
- build to an external artifact directory

Good candidates for override in this repo:

- `lovable/src/contexts/AuthContext.tsx`
- `lovable/src/contexts/DraftContext.tsx`
- `lovable/src/data/mockData.ts`
- fake-action components that cannot be made real through data-only overrides

Goal:

- the emitted artifact should already depend on Django-backed logic before any HTML shell injection happens

## 3. Centralized frontend control outside `lovable/`

Keep these in repo-owned paths outside `lovable/`:

- `static/frontend-brand/tokens.css`
- `static/frontend-brand/overrides.css`
- `static/frontend-brand/runtime-config.js`

Recommended roles:

- `tokens.css`
  - CSS variables for colors, radii, fonts — values must be byte-for-byte identical to `lovable/src/index.css`. Purpose is externalised control only, not visual change.
- `overrides.css`
  - must be empty by default. Only add rules when a deliberate visual change is explicitly requested. Never pre-populate during cutover.
- `runtime-config.js`
  - API base URL
  - environment name
  - optional bootstrap JSON pointers
  - optional feature flags

For this repo, prefer inline runtime/bootstrap config in the served HTML shell over a second blocking request to `/frontend-runtime.js`.

Why:

- a failed runtime script fetch can blank-screen the app before React boot
- inline config keeps the bootstrap dependency graph inside the root HTML response
- the live root route becomes easier to verify and harder to partially break

If the runtime payload is assembled from Django-side session or model helpers, serialize it with a Django-safe encoder rather than raw `json.dumps(...)`.

**Visual parity rule**: `tokens.css` loaded into the SPA shell must not change any visible appearance. If the Lovable app looks different with `tokens.css` injected vs without it, the values in `tokens.css` are wrong — fix them to match `lovable/src/index.css` exactly.

## 4. Frontend serving pattern

Recommended production pattern for this repo:

- Django owns backend endpoints, admin, uploads, and operations
- the Lovable build owns **all** browser-navigable URLs — no exceptions
- the real domain serves both

Ownership split:

- `/frontend-api/**`: Django JSON API (consumed by SPA via fetch)
- `/admin/**`: Django
- `/runtime/**`: Django
- `/uploads/**`, `/media/**`: Django or storage/CDN
- `/static/**`: Django static pipeline or storage/CDN
- `/trips/<id>/banner/`, `/trips/api/**`: Django
- **everything else**: SPA shell + assets

There is no class of "Django web page" for browser users. If a URL is not in the backend-only list above, it serves the SPA shell. Django-rendered HTML templates for browser-navigable routes are a cutover blocker — treat them the same as mock data blockers.

## 5. SPA fallback

Production must support deep links and hard refreshes.

One valid pattern:

- Django view serves the compiled Lovable `index.html` for SPA-owned routes
- Django continues to short-circuit known backend routes first

Another valid pattern:

- load balancer or reverse proxy routes backend prefixes to Django handlers
- all other public prefixes serve the SPA entrypoint

## 6. Backend contract expectations

Before cutting traffic to a Lovable-owned route, make sure Django exposes real contracts for:

- session/auth state
- current user/profile
- trips list/detail/create/edit/publish
- blogs list/detail/create/edit
- drafts
- bookings
- trip applications

If the route shows or mutates data in the browser, the backend contract should exist first.

## 7. No-touch Lovable integration patterns

Because source edits under `lovable/` are forbidden, use one of these:

### Pattern A: external source-override build

- build Lovable with an external config
- alias known fake modules to replacement modules outside `lovable/`
- emit the final artifact outside the source tree

Use this first. It is the strongest option because it replaces fake logic before it becomes a shipped bundle.

### Pattern B: external build + wrapper shell

- build Lovable outside the source tree
- serve the generated HTML through a Django wrapper template or server-side response
- inject brand CSS and runtime config

### Pattern C: external build + post-build transform

- build Lovable outside the source tree
- patch generated HTML or JS bundles in the external artifact
- use deterministic scripts for repeatable transforms

### Pattern D: external build + runtime shim

- inject a small runtime script before app bootstrap
- expose same-origin backend config and bootstrap state
- use this only if the behavior is reliable and testable end-to-end

Do not jump straight to Pattern C or D if Pattern A can solve the problem more cleanly.

## 8. Infra touchpoints

The current deployment path is Django-first. Expect to update:

- [infra/Dockerfile.web](e:/tapne/infra/Dockerfile.web)
- [infra/run-cloud-run-workflow.ps1](e:/tapne/infra/run-cloud-run-workflow.ps1)
- supporting deploy scripts under [infra](e:/tapne/infra)
- possibly Django static or template serving settings in [tapne/settings.py](e:/tapne/tapne/settings.py)

Operational constraints for this repo:

- deployment scripts are run from Windows PowerShell environments, not only PowerShell 7
- avoid `ConvertFrom-Json -Depth` in shared scripts unless you wrap it in a compatibility helper
- validate boolean and switch forwarding across orchestrator scripts
- if the immutable Lovable lockfile is out of sync, do not "fix" it by editing `lovable/`; use a disposable package install strategy in the external builder instead

## 9. Acceptance checks before production rollout

- build reproducibly creates a deployable frontend artifact outside `lovable/`
- artifact is included in the deployed service or static hosting path
- SPA fallback works for direct browser loads
- same-origin backend APIs respond correctly in the browser
- no production route shows mock data
- auth survives refresh
- writes persist
- centralized brand files override frontend appearance without editing Lovable source
- `tokens.css` values are identical to `lovable/src/index.css` — visual appearance does not change when tokens.css is loaded
- `overrides.css` is empty (no unsolicited visual overrides injected)
- final artifact passes a banned-pattern scan for known mock/local-only signatures
- the root HTML serves inline runtime config and does not depend on `/frontend-runtime.js`
- signed-in shell rendering is covered by a regression test
- post-deploy verification includes `/`, not just health/static endpoints
- no Django HTML template is being served for any browser-navigable URL
- the SPA catch-all is active and renders an "Under Construction" page that visually matches the rest of the app
- all Django URLs that had HTML templates now either redirect to the SPA equivalent or fall through to the SPA shell

## 10. Failure modes to catch early

- deployed site still serves Django templates for public routes you expected to cut over
- Lovable route loads but shows mock/demo records
- log in works visually but is still fake
- create/edit flows “succeed” in the UI without backend persistence
- refresh on `/trips/...` or `/blogs/...` returns 404 or Django fallback content
- build pipeline silently writes to `lovable/dist` and someone patches files there by hand
- the build still contains `localStorage`, `mockData`, or fake auth patterns because override aliasing never actually took effect
- `/` returns `500` only for signed-in users because the server-rendered runtime payload contains non-JSON-safe Django values
- the artifact looks clean but the live shell still fails because runtime/bootstrap injection was never verified against the deployed domain
- **pages look completely wrong (wrong font, no carousel, no tabs)** — caused by `frontend_spa/src/App.tsx` importing `@frontend/pages/*` custom replacements instead of `@/pages/*` Lovable source pages. Always read `lovable/src/App.tsx` first and import pages from `@/pages/*`.
- **React state / data-fetching broken across all pages** — caused by the override `App.tsx` dropping providers (`QueryClientProvider`, `DraftProvider`, etc.) that exist in `lovable/src/App.tsx`. Mirror the provider tree exactly.
- **parameterised Django routes (`/trips/<id>/edit/`, `/u/<username>/`, etc.) render old Django templates** — caused by missing explicit `re_path` patterns in `frontend/urls.py`. The global `tapne/urls.py` catch-all does not intercept paths that are already claimed by app-specific `urls.py` files included earlier.
- **visual differences between standalone Lovable and production** (different fonts, shapes, shadows) — caused by `overrides.css` containing visual CSS rules (`font-family`, `border-radius !important`, `box-shadow !important`). `overrides.css` must be empty of visual rules by default.
