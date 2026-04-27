---
name: lovable-django-production-cutover
description: >
  Run Tapne's Lovable-to-Django production cutover workflow by deriving the live
  route, API, runtime-config, and mock contract from source, mapping each
  dependency to Django and frontend_spa, fixing non-Lovable integration gaps,
  and producing one consolidated Lovable prompt only for true Scope 1
  showstoppers. Use when working on Tapne cutovers, SPA/Django contract audits,
  or related deployment follow-through governed by RULES.md.
---

# Lovable to Django Production Cutover

[RULES.md](../../RULES.md) is the canonical rules document for this repo. If any
instruction here conflicts with it, follow `RULES.md` and treat this skill as
stale. This skill is a cutover workflow, not a second rules source.

Companion docs:

- [BASELINE.md](./BASELINE.md): stable file map, scan targets, and hotspot index
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md): recurring cutover-specific failure patterns
- [DEPLOY.md](./DEPLOY.md): repo-specific Scope 4 workflow mechanics

## Rule Anchors

| Concern | Canonical source |
|---|---|
| Pre-flight | [RULES.md](../../RULES.md) Section 1 |
| `lovable/` read-only + exit gate | [RULES.md](../../RULES.md) Section 2 |
| Lovable prompt contract | [RULES.md](../../RULES.md) Section 2b |
| Scope classification | [RULES.md](../../RULES.md) Section 4 |
| Scope 2/3/4 invariants + verification gate | [RULES.md](../../RULES.md) Section 5 |
| Canonical route audit | [RULES.md](../../RULES.md) Section 6 |
| Start/end reporting | [RULES.md](../../RULES.md) Section 7 |

Do not restate or override those sections here. Use them directly during the
run.

## Execution Sequence

### 1. Classify the work first

- Classify the task with [RULES.md](../../RULES.md) Section 4 before touching
  files.
- If the request spans multiple scopes, split it before editing anything.
- This skill usually operates in Scope 3, with optional Scope 4 follow-through
  when deployment is part of the same task.

### 2. Run the exact repo pre-flight

- Use [RULES.md](../../RULES.md) Section 1 exactly as written.
- Report the pre-flight and start-of-task header using
  [RULES.md](../../RULES.md) Section 7.
- Do not define an alternate pre-flight in this skill.

### 3. Rebuild the live contract from source

Read these files in full before deciding what is missing:

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
- [frontend/urls.py](../../frontend/urls.py)
- [frontend/views.py](../../frontend/views.py)
- [tapne/urls.py](../../tapne/urls.py)

Then run these live-inventory scans:

```powershell
rg -n 'from "@/types/' lovable/src/pages lovable/src/contexts lovable/src/components -g '*.ts' -g '*.tsx'
rg -n 'apiGet|apiPost|apiPatch|apiDelete|cfg\.api\.|cfg\.auth\.' lovable/src/pages lovable/src/contexts lovable/src/components -g '*.ts' -g '*.tsx'
rg -n 'path="|<Route|createBrowserRouter|children:' lovable/src/App.tsx frontend_spa/src/App.tsx
rg -n 'resolveMockRequest|__devmock__|mockData' lovable/src/lib/devMock.ts lovable/src/data/mockData.ts
```

Also run the exact `cfg.api.base` audit required by
[RULES.md](../../RULES.md) Section 5.

Any extra `@/types/*` file discovered by the scan becomes part of the live
contract and must be read before proceeding.

### 4. Derive the live inventory

Produce a fresh inventory from current source only:

- canonical route audit:
  compare [RULES.md](../../RULES.md) Section 6 against `lovable/src/App.tsx`,
  `frontend_spa/src/App.tsx`, `frontend/urls.py`, and `tapne/urls.py`
- runtime-config API surface:
  every `TapneRuntimeConfig.api` key plus where the frontend uses it
- direct API call inventory:
  named `cfg.api.*` calls plus `cfg.api.base` interpolations
- Django URL/view inventory:
  actual URL patterns and owning views in `frontend/urls.py` and
  `frontend/views.py`
- mock inventory:
  request patterns and shape-bearing fixtures in `devMock.ts` and
  `mockData.ts`

Treat the live source plus [RULES.md](../../RULES.md) Section 6 as route truth.
Do not reintroduce or preserve a route merely because it appears in stale
history or older snapshots.

### 5. Map every dependency to Django or `frontend_spa`

For each route, API call, runtime-config key, and mock dependency:

1. Resolve the concrete frontend expectation from live source.
2. Check it against the canonical route map in
   [RULES.md](../../RULES.md) Section 6.
3. Find the matching Django URL/view or `frontend_spa` production mapping.
4. If it is valid and present, mark it confirmed.
5. If it is missing, stale, or mismatched, fix it in the correct non-Lovable
   scope.

During this pass, pay special attention to:

- `cfg.api.base` interpolations that bypass named API-key audits
- `messaging.ts` shapes, not just `api.ts`
- auth-sensitive contexts and pages that depend on live auth state
- CSRF behavior after modal login
- providers or contexts using router hooks
- mock-only behavior that still lacks a Django-backed equivalent

Use [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) for recurring failure patterns,
not as an alternate rules document.

### 6. Verify using the canonical gates

- Apply [RULES.md](../../RULES.md) Section 5 for response-shape audits,
  integration invariants, and browser verification.
- Use [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) only to narrow likely causes
  when a gate fails.
- Do not invent a weaker acceptance path based on HTTP 200, shell presence, or
  partial rendering.

### 7. Decide whether a Lovable prompt is needed

- Use [RULES.md](../../RULES.md) Section 2b exactly as written.
- Emit one consolidated prompt only for true Scope 1 showstoppers.
- If no Scope 1 showstopper remains, use the exact no-prompt line from
  [RULES.md](../../RULES.md) Section 2b.

### 8. Handle deployment only when the task includes Scope 4

- If deployment is part of the task, follow [DEPLOY.md](./DEPLOY.md) for the
  repo-specific workflow mechanics.
- The deployment rules, invariants, and reporting still come from
  [RULES.md](../../RULES.md) Sections 5 and 7.

### 9. Close out using the repo contract

- Use the exact end-of-task reporting contract in
  [RULES.md](../../RULES.md) Section 7.
- Run the `lovable/` exit gate from [RULES.md](../../RULES.md) Section 2 before
  considering the session done.
