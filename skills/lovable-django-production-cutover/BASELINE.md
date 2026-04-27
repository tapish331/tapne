# Baseline Reference Index

This file is reference only. It is not a source of truth for routes, API keys,
endpoint inventories, prompt wording, or verification policy.

Use [RULES.md](../../RULES.md) for all repo rules. Use [SKILL.md](./SKILL.md)
for the cutover workflow that regenerates the live contract from source on every
run.

## Core Rule Source

| Concern | Canonical source |
|---|---|
| Pre-flight, `lovable/` restrictions, prompt contract, scope rules, verification, route canon, reporting | [RULES.md](../../RULES.md) |

## Stable File Map

| Purpose | Path |
|---|---|
| Canonical repo rules | `RULES.md` |
| Lovable route source | `lovable/src/App.tsx` |
| Lovable API/runtime-config types | `lovable/src/types/api.ts` |
| Lovable messaging types | `lovable/src/types/messaging.ts` |
| Lovable API client + CSRF handling | `lovable/src/lib/api.ts` |
| Lovable dev-mode switch | `lovable/src/lib/mode.ts` |
| Lovable mock request handler | `lovable/src/lib/devMock.ts` |
| Lovable mock fixtures | `lovable/src/data/mockData.ts` |
| Lovable auth state source | `lovable/src/contexts/AuthContext.tsx` |
| Lovable draft state source | `lovable/src/contexts/DraftContext.tsx` |
| Production route source | `frontend_spa/src/App.tsx` |
| Production API client | `frontend_spa/src/lib/api.ts` |
| Production Vite alias config | `frontend_spa/vite.production.config.ts` |
| Django SPA/API URL map | `frontend/urls.py` |
| Django runtime-config + API views | `frontend/views.py` |
| Root URL ownership | `tapne/urls.py` |
| Production SPA build script | `infra/build-lovable-production-frontend.ps1` |
| Cloud Run workflow entrypoint | `infra/run-cloud-run-workflow.ps1` |
| Cloud Run deploy helper | `infra/deploy-cloud-run.ps1` |

## Live-Inventory Scan Targets

Run these every cutover session after the repo pre-flight described in
[RULES.md](../../RULES.md):

```powershell
rg -n 'from "@/types/' lovable/src/pages lovable/src/contexts lovable/src/components -g '*.ts' -g '*.tsx'
rg -n 'apiGet|apiPost|apiPatch|apiDelete|cfg\.api\.|cfg\.auth\.' lovable/src/pages lovable/src/contexts lovable/src/components -g '*.ts' -g '*.tsx'
rg -n 'path="|<Route|createBrowserRouter|children:' lovable/src/App.tsx frontend_spa/src/App.tsx
rg -n 'resolveMockRequest|__devmock__|mockData' lovable/src/lib/devMock.ts lovable/src/data/mockData.ts
```

Run the exact `cfg.api.base` audit from [RULES.md](../../RULES.md) Section 5 in
addition to the scans above.

## Stable Hotspot Index

| Area | Primary files | Why it matters |
|---|---|---|
| Canonical route audit | `lovable/src/App.tsx`, `frontend_spa/src/App.tsx`, `frontend/urls.py`, `tapne/urls.py` | Route truth comes from live source plus `RULES.md` Section 6 |
| Runtime-config coverage | `lovable/src/types/api.ts`, `frontend/views.py` | Every consumed key must exist in `_runtime_config_payload()["api"]` |
| API call inventory | `lovable/src/pages/**`, `lovable/src/contexts/**`, `lovable/src/components/**`, `frontend/urls.py`, `frontend/views.py` | Named keys and direct URL interpolations can drift independently |
| Messaging contracts | `lovable/src/types/messaging.ts`, `frontend/views.py` | DM shapes are easy to miss if only `api.ts` is audited |
| Mock replacement | `lovable/src/lib/devMock.ts`, `lovable/src/data/mockData.ts`, Django API endpoints | Production cutover is incomplete if important behavior still exists only in mocks |
| Auth state and modal flows | `lovable/src/contexts/AuthContext.tsx`, `lovable/src/contexts/DraftContext.tsx`, auth-sensitive pages | Bootstrap auth and live auth can diverge |
| CSRF behavior | `lovable/src/lib/api.ts`, Django auth/session flow | POST/PATCH/DELETE often fail after modal login if cookie lookup regresses |
| Router-hook providers | `frontend_spa/src/App.tsx`, `lovable/src/contexts/DraftContext.tsx` | Misplaced providers can crash the app before render |
| Deployment workflow | `infra/build-lovable-production-frontend.ps1`, `infra/run-cloud-run-workflow.ps1`, `infra/deploy-cloud-run.ps1` | Scope 4 must build fresh SPA artifacts before image creation |

## What This File Must Not Become

Do not add:

- dated route snapshots
- dated API-key or endpoint tables
- dated SPA-entrypoint inventories
- prompt templates
- verification policy copied from `RULES.md`
- historical route lore that can drift into false instructions
