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
| Deployed SPA shell route map | `frontend/urls.py` |
| Root URL ownership | `tapne/urls.py` |
| Runtime config + API types | `lovable/src/types/api.ts` |
| Messaging types | `lovable/src/types/messaging.ts` |
| API client + CSRF behavior | `lovable/src/lib/api.ts` |
| Auth flows | `lovable/src/contexts/AuthContext.tsx` |
| Draft flows | `lovable/src/contexts/DraftContext.tsx` |
| Django runtime config + JSON views | `frontend/views.py` |
| Django route map | `frontend/urls.py` |
| Production build script | `infra/build-lovable-production-frontend.ps1` |
| Production build script (shell) | `infra/build-lovable-production-frontend.sh` |
| Container build path | `infra/Dockerfile.web` |
| Primary guardrail workflow | `.github/workflows/production-flow-guardrail.yml` |
| Secondary browser workflow reference | `.github/workflows/visual-audit-pr-guardrail.yml` |
| Current committed guardrail coverage | `tests/e2e/` |
| E2E session + server bootstrap | `tests/e2e/conftest.py`, `tests/e2e/server.py` |
| E2E auth/session helpers | `tests/e2e/auth.py` |
| E2E shared audit/data helpers | `tests/e2e/helpers.py`, `tests/e2e/data.py`, `tests/e2e/types.py` |
| Guardrail test dependencies | `tests/e2e/requirements.txt` |
| Pytest marker config | `pytest.ini` |
| External storage-state helper reference | `skills/webpage-visual-perfection-audit/scripts/create_storage_state.py` |
| Bootstrap command directory | `accounts/management/commands/` and sibling `bootstrap_*` commands |
| Browser artifact root | `artifacts/` |

## Live-Inventory Scan Targets

Run these after the repo pre-flight described in
[RULES.md](../../RULES.md):

```powershell
rg -n 'path="|<Route|createBrowserRouter|children:' lovable/src/App.tsx
rg -n 'apiGet|apiPost|apiPatch|apiDelete|cfg\.api\.|cfg\.auth\.|requireAuth\(|navigate\(' lovable/src/pages lovable/src/contexts lovable/src/components
rg -n 'handleSubmit|onSubmit|DropdownMenuItem|Dialog|Modal|toast\.' lovable/src/pages lovable/src/components
rg -n 'useNavigate|useLocation|useParams' lovable/src/contexts lovable/src/pages lovable/src/components
rg -n '@pytest.mark|def test_' tests/e2e -g '*.py'
Test-Path frontend_spa
rg -n 'frontend_spa|@frontend/' -S
```

Run the exact `cfg.api.base` audit from [RULES.md](../../RULES.md) Section 5 in
addition to the scans above.

Compare the extracted routes and flows against the currently committed harness
coverage in `tests/e2e/`, not against a dated snapshot in this folder.

## Stable Hotspot Index

| Area | Primary files | Why it matters |
|---|---|---|
| Route parity | `lovable/src/App.tsx`, `frontend/urls.py`, `tapne/urls.py` | Planned-vs-deployed route truth comes from live source plus `RULES.md` Section 6 |
| Frontend truth + build path | repo root, `lovable/`, build scripts, `infra/Dockerfile.web` | The guardrail is only valid if the built SPA comes solely from `lovable/` with no shadow SPA layer |
| Flow extraction | `lovable/src/pages/**`, `lovable/src/contexts/**`, `lovable/src/components/**` | Entry actions, mutations, and visible success signals live here |
| Runtime-config and API coupling | `lovable/src/types/api.ts`, `lovable/src/lib/api.ts`, `frontend/views.py`, `frontend/urls.py` | Named API keys and direct interpolations can drift independently |
| Harness bootstrap env | `tests/e2e/conftest.py`, `tests/e2e/server.py`, `pytest.ini` | Local and CI proof depends on deterministic server env, artifact checks, and marker wiring |
| Auth storage state | `tests/e2e/auth.py`, `artifacts/auth/`, bootstrap account commands | Real modal login, per-user session files, and storage-state refresh rules must stay aligned |
| Trip application flows | `lovable/src/pages/TripDetail.tsx`, `lovable/src/components/ApplicationModal.tsx`, `frontend/views.py`, `tests/e2e/test_auth_and_csrf.py`, `tests/e2e/test_manage_trip.py` | Apply-vs-book CTA routing, pending-state persistence, and host decisions regress independently |
| Messaging and host-management flows | `lovable/src/types/messaging.ts`, trip/detail and message surfaces, Django payload builders/views | These flows often span multiple actors and are easy to under-cover |
| Auth, CSRF, and draft state | `lovable/src/contexts/AuthContext.tsx`, `lovable/src/contexts/DraftContext.tsx`, `lovable/src/lib/api.ts` | Modal login, live auth state, and persisted draft behavior need real-browser proof |
| Current harness inventory | `tests/e2e/`, `.github/workflows/production-flow-guardrail.yml`, `.github/workflows/visual-audit-pr-guardrail.yml` | Use the existing helpers and primary guardrail workflow before adding new surface area |
| Seed data and storage state | `bootstrap_*` commands, storage-state helper script, `artifacts/auth/` | Stable reruns depend on deterministic data and per-user session material |
| Build artifact and Django serving | `infra/build-lovable-production-frontend.ps1`, `infra/build-lovable-production-frontend.sh`, `tests/e2e/server.py`, Django entrypoint/runtime-config views | The guardrail only counts against Django serving the built production SPA |

## What This File Must Not Become

Do not add:

- dated route snapshots
- dated flow snapshots
- exact `cfg.api.base` line-number inventories
- copied verification policy from `RULES.md`
- Lovable prompt templates or wording
- historical `frontend_spa` file maps or alias lore
- scope decisions derived from stale history instead of current source
