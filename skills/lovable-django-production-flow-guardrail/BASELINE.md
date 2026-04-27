# Baseline Reference Index

This file is reference only. It is not a source of truth for routes, flow
coverage, prompt wording, verification policy, or reporting.

Use [RULES.md](../../RULES.md) for all repo rules. Use
[SKILL.md](./SKILL.md) for the workflow that regenerates the live flow matrix
from source and translates it into persistent guardrail coverage decisions on
every run.

## Core Rule Source

| Concern | Canonical source |
|---|---|
| Pre-flight, `lovable/` restrictions, prompt contract, scope rules, verification, route canon, reporting | [RULES.md](../../RULES.md) |

## Stable File Map

| Purpose | Path |
|---|---|
| Parent cutover contract | `skills/lovable-django-production-cutover/SKILL.md` |
| Guardrail runbook | `skills/lovable-django-production-flow-guardrail/SKILL.md` |
| Lovable route source | `lovable/src/App.tsx` |
| Production route source | `frontend_spa/src/App.tsx` |
| Runtime config + API types | `lovable/src/types/api.ts` |
| Messaging types | `lovable/src/types/messaging.ts` |
| API client + CSRF behavior | `lovable/src/lib/api.ts` |
| Auth flows | `lovable/src/contexts/AuthContext.tsx` |
| Draft flows | `lovable/src/contexts/DraftContext.tsx` |
| Django runtime config + JSON views | `frontend/views.py` |
| Django route map | `frontend/urls.py` |
| Production build script | `infra/build-lovable-production-frontend.ps1` |
| Existing browser workflow reference | `.github/workflows/visual-audit-pr-guardrail.yml` |
| Current committed guardrail coverage | `tests/e2e/` |
| Storage-state helper reference | `skills/webpage-visual-perfection-audit/scripts/create_storage_state.py` |
| Bootstrap command directory | `accounts/management/commands/` and sibling `bootstrap_*` commands |
| Browser artifact root | `artifacts/` |

## Live-Inventory Scan Targets

Run these after the repo pre-flight described in
[RULES.md](../../RULES.md):

```powershell
rg -n 'path="|<Route|createBrowserRouter|children:' lovable/src/App.tsx frontend_spa/src/App.tsx
rg -n 'apiGet|apiPost|apiPatch|apiDelete|cfg\.api\.|cfg\.auth\.|requireAuth\(|navigate\(' lovable/src/pages lovable/src/contexts lovable/src/components
rg -n 'handleSubmit|onSubmit|DropdownMenuItem|Dialog|Modal|toast\.' lovable/src/pages lovable/src/components
rg -n 'useNavigate|useLocation|useParams' lovable/src/contexts lovable/src/pages lovable/src/components
rg -n '@pytest.mark|def test_' tests/e2e -g '*.py'
```

Run the exact `cfg.api.base` audit from [RULES.md](../../RULES.md) Section 5 in
addition to the scans above.

Compare the extracted routes and flows against the currently committed harness
coverage in `tests/e2e/`, not against a dated snapshot in this folder.

## Stable Hotspot Index

| Area | Primary files | Why it matters |
|---|---|---|
| Route parity | `lovable/src/App.tsx`, `frontend_spa/src/App.tsx`, `frontend/urls.py`, `tapne/urls.py` | Planned-vs-deployed route truth comes from live source plus `RULES.md` Section 6 |
| Flow extraction | `lovable/src/pages/**`, `lovable/src/contexts/**`, `lovable/src/components/**` | Entry actions, mutations, and visible success signals live here |
| Runtime-config and API coupling | `lovable/src/types/api.ts`, `lovable/src/lib/api.ts`, `frontend/views.py`, `frontend/urls.py` | Named API keys and direct interpolations can drift independently |
| Messaging and host-management flows | `lovable/src/types/messaging.ts`, trip/detail and message surfaces, Django payload builders/views | These flows often span multiple actors and are easy to under-cover |
| Auth, CSRF, and draft state | `lovable/src/contexts/AuthContext.tsx`, `lovable/src/contexts/DraftContext.tsx`, `lovable/src/lib/api.ts` | Modal login, live auth state, and persisted draft behavior need real-browser proof |
| Current harness inventory | `tests/e2e/`, `.github/workflows/visual-audit-pr-guardrail.yml` | Use existing helpers and workflow shape before adding new surface area |
| Seed data and storage state | `bootstrap_*` commands, storage-state helper script, `artifacts/auth/` | Stable reruns depend on deterministic data and per-user session material |
| Build artifact and Django serving | `infra/build-lovable-production-frontend.ps1`, Django entrypoint/runtime-config views | The guardrail only counts against Django serving the built production SPA |

## What This File Must Not Become

Do not add:

- dated route snapshots
- dated flow snapshots
- exact `cfg.api.base` line-number inventories
- copied verification policy from `RULES.md`
- Lovable prompt templates or wording
- scope decisions derived from stale history instead of current source
