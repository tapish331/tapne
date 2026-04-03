# No-Touch Override Build

Use this file when the shipped Lovable app still contains fake logic but source edits inside `lovable/` are forbidden.

## Core idea

Do not patch the original source tree. Replace it at build time.

That means:

- original Lovable files remain untouched
- replacement modules live elsewhere in the repo
- an external build config aliases selected Lovable imports to those replacement modules
- the emitted bundle is already Django-backed before deployment

This is stronger than HTML shell injection and cleaner than broad compiled-bundle surgery.

## Default pattern

1. Audit fake or local-only modules.
2. Build a source override map.
3. Implement replacement modules outside `lovable/`.
4. Use an external Vite config outside `lovable/` with `resolve.alias` entries for the original Lovable paths.
5. Build into `artifacts/lovable-production-dist`.
6. Verify the final artifact no longer contains banned mock/local-only patterns.
7. Only then wire public traffic to the SPA routes.

If `lovable/package-lock.json` is out of sync with `lovable/package.json`, do not repair that by editing tracked files under `lovable/`. Use a disposable install strategy in the external builder so the no-touch rule still holds.

## What to override in this repo

Start with these when applicable:

- `lovable/src/contexts/AuthContext.tsx`
  Replace fake login/signup/profile state with Django session-backed behavior.
- `lovable/src/contexts/DraftContext.tsx`
  Replace `localStorage` drafts with a Django-backed persistence layer that preserves the same external API shape.
- `lovable/src/data/mockData.ts`
  Replace mock catalog exports with live data helpers or bootstrap-backed exports that preserve the expected import surface.
- components that still perform fake writes even after data/context replacement
  Examples in this repo include booking/application flows and host-side application management.
- `lovable/src/App.tsx` (always required for this repo)
  The override at `frontend_spa/src/App.tsx` must:
  1. Import all user-facing pages from `@/pages/*` (the real Lovable source pages) — **never** from `@frontend/pages/*`.
  2. Import only `UnderConstructionPage` from `@frontend/pages/UnderConstructionPage` — this is the sole `@frontend/pages/` import.
  3. Preserve the full provider tree from `lovable/src/App.tsx`: `QueryClientProvider`, `AuthProvider`, `DraftProvider`, `TooltipProvider`, both `Toaster`s.
  4. Use the same route paths as `lovable/src/App.tsx`. The `*` catch-all points to `UnderConstructionPage` instead of `NotFound`. Everything else is identical.
  See `references/override-targets.md` for the exact template.

## Under Construction component requirements

The `UnderConstruction` component provided via the external override must:

1. Import and render Navbar and Footer from existing Lovable components (`@/components/Navbar`, `@/components/Footer`).
2. Use only Tailwind utility classes already in scope from the Lovable build — specifically `bg-background`, `text-foreground`, `text-primary`, `border-border`, `font-sans`, `rounded-lg`, `container`, standard spacing (`py-*`, `px-*`, `gap-*`). Do not add new CSS, inline styles, or non-Lovable class names.
3. Display: a clear heading ("Under Construction" or similar), a short message ("This page is coming soon."), and a home link/button (`/`).
4. Must look visually consistent with the rest of the Lovable app — same Navbar, same Footer, same page structure, same type scale.
5. Must not depend on any auth state or Django data — it must render identically for signed-in and signed-out users.
6. Must not reference any Lovable mock data, localStorage, or fake contexts.

This component is the universal fallback for all Django routes that have no corresponding Lovable page.

## Replacement module rules

Replacement modules should:

- preserve the public export names expected by Lovable imports
- preserve the semantic shape of returned values when reasonable
- route all truth to Django-backed APIs or server bootstrap state
- avoid introducing a second client-side source of truth
- be deterministic enough to validate through browser tests

## When runtime shell injection is still needed

Even with source overrides, keep runtime shell injection for:

- runtime config
- CSRF/bootstrap state
- centralized brand CSS
- environment flags

Do not make runtime shell injection carry business-critical replacement logic if a source override can do it more explicitly.

## When post-build transforms are still needed

Use post-build transforms only for:

- final `index.html` injection
- asset URL adjustments
- deterministic residual fixes that cannot be handled through aliasing

If a behavior can be replaced at the module level, prefer that over patching minified bundle code.

## Evidence standard

A route is not cutover-ready until you can show:

- the fake source module is overridden externally
- the built artifact is free of banned mock/local-only markers for that surface
- browser behavior writes through Django and survives refresh

## Dual-mode system

The Lovable source now contains a dual-mode architecture that lets it run fully in the Lovable editor without Django, and automatically switch to real Django API calls when deployed.

This is a special case of the no-touch rule: the four dual-mode files (`mode.ts`, `devMock.ts`, `api.ts`, `main.tsx`) live inside `lovable/src/` but were added via a Lovable prompt, not by editing the files directly. They follow the same rule: if Lovable overwrites them, re-apply via prompt — never hand-edit under `lovable/`.

### What the dual-mode files do

| File | Role |
|---|---|
| `lovable/src/main.tsx` | First import is `import "@/lib/mode"` — must run before any React component |
| `lovable/src/lib/mode.ts` | Detects `window.TAPNE_RUNTIME_CONFIG` presence. If absent (dev), injects a mock config with `/__devmock__/*` API URLs and sets `IS_DEV_MODE = true`. If present (Django), does nothing — `IS_DEV_MODE = false`. |
| `lovable/src/lib/devMock.ts` | In-memory mock API resolver. Handles session, auth, home, trips list, trip detail, blogs, my-trips, draft CRUD, and profile. Converts `mockData.ts` types to the Django API response shapes expected by each page. |
| `lovable/src/lib/api.ts` | Wraps all four API functions (`apiGet`, `apiPost`, `apiPatch`, `apiDelete`) with an `if (IS_DEV_MODE)` early return that calls `resolveMockRequest`. Django mode paths are unchanged. |

### Production build requirement: devMock stub

`devMock.ts` imports `lovable/src/data/mockData.ts`. If the production bundle includes `devMock.ts`, it also includes all mock trip/user data — inflating the bundle by ~50 KB and causing the artifact checker to fail on the `"mockData"` banned marker.

Fix: alias `@/lib/devMock` to `frontend_spa/src/lib/devMockStub.ts` in the production Vite config.

In `frontend_spa/vite.production.config.ts`, the `resolve.alias` block must contain:
```typescript
"@/lib/devMock": path.resolve(__dirname, "src/lib/devMockStub.ts"),
```
(before the `"@"` alias so the longer key takes precedence)

The stub file (`frontend_spa/src/lib/devMockStub.ts`) exports a no-op `resolveMockRequest`. The production bundle then contains neither `devMock.ts` nor `mockData.ts`.

### Re-applying dual-mode after a Lovable submodule pull

If Lovable overwrites any of the four files, re-apply by giving Lovable this prompt:

> The files `src/lib/mode.ts`, `src/lib/devMock.ts`, `src/lib/api.ts`, and `src/main.tsx` have been overwritten by a Lovable update. Please restore the dual-mode architecture exactly as specified in the previous session. The complete specification is in `skills/lovable-django-production-cutover/references/no-touch-override-build.md` and the last dual-mode prompt.

Alternatively, apply the changes manually by copying the working versions from git history:
```bash
cd lovable
git show <last-good-sha>:src/lib/mode.ts > src/lib/mode.ts
git show <last-good-sha>:src/lib/devMock.ts > src/lib/devMock.ts
git show <last-good-sha>:src/lib/api.ts > src/lib/api.ts
git show <last-good-sha>:src/main.tsx > src/main.tsx
```

## Practical repo policy

In this repo, "no edits under `lovable/`" does not mean "no frontend logic changes".

It means:

- frontend logic changes must happen through external overrides, runtime injection, or deterministic artifact transforms

That policy removes the old limitation entirely.
