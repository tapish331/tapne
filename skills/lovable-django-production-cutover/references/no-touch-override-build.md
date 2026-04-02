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

## Practical repo policy

In this repo, "no edits under `lovable/`" does not mean "no frontend logic changes".

It means:

- frontend logic changes must happen through external overrides, runtime injection, or deterministic artifact transforms

That policy removes the old limitation entirely.
