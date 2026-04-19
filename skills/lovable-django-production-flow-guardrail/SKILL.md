---
name: lovable-django-production-flow-guardrail
description: >
  Builds and maintains Tapne's real-browser production-flow guardrail: refresh
  `lovable/` in place, derive the live flow matrix from current source,
  classify every current user journey into smoke/full/showstopper coverage,
  build the production SPA through Django-safe temp workspaces, implement or
  update deterministic Python Playwright + pytest coverage and CI outside
  `skills/`, and prove it locally against Django serving the built artifact.
---

# Lovable -> Django Production Flow Guardrail

Use this file as the operator runbook. The split is structural only; the
original operational contract is preserved across this file and the companion
docs, which are normative parts of the skill:

- [BASELINE.md](./BASELINE.md): key file map and reference baseline tables
- [SETUP.md](./SETUP.md): production build, bootstrap, and auth/session rules
- [HARNESS.md](./HARNESS.md): persistent harness layout, test design, and CI rules
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md): gap protocol, blockers, and hard acceptance gates

This skill is the automation companion to
`skills/lovable-django-production-cutover/SKILL.md`.
Use it when the goal is not just to fix today's cutover, but to leave behind a
repeatable browser guardrail that catches the same class of regressions on the
next Lovable pull.

All persistent flow coverage created by this skill must be:

- real-browser
- Django-served production SPA
- end to end
- fully automated

The `smoke` versus `full` split is only about scheduling and subset size. It is
not a distinction between "partial" and "real" end-to-end tests.

## Absolute Restrictions

**The only allowed in-place change under `lovable/` is `git -C lovable pull --ff-only`.**
After that pull completes, `git -C lovable status` must report a clean working
tree before any further step runs. Do not patch, create, rename, delete,
install, build, or normalize line endings anywhere under `lovable/`.

**Never validate flows against the Lovable dev server.**
All browser checks must run against Django serving
`artifacts/lovable-production-dist/`.

**Do not introduce a second frontend test stack by default.**
Use Python + Playwright + `pytest` in this repo unless the user explicitly asks
for Node Playwright, Cypress, or Vitest browser tests.

**Persistent product guardrails do not live under `skills/`.**
The skill itself lives here; the flow harness it creates belongs in repo-owned
paths such as `tests/e2e/`, `.github/workflows/`, and optionally `pytest.ini`.

**Storage-state JSON, screenshots, traces, and logs are artifacts, not source.**
Write them under `artifacts/` and never commit them.

## Read This First Every Run

Before changing any test harness code, read these files in full:

- [skills/lovable-django-production-cutover/SKILL.md](../../skills/lovable-django-production-cutover/SKILL.md)
- [LOVABLE_CONTEXT.md](../../LOVABLE_CONTEXT.md)
- [lovable/src/App.tsx](../../lovable/src/App.tsx)
- [lovable/src/types/api.ts](../../lovable/src/types/api.ts)
- [lovable/src/types/messaging.ts](../../lovable/src/types/messaging.ts)
- [lovable/src/lib/api.ts](../../lovable/src/lib/api.ts)
- [lovable/src/contexts/AuthContext.tsx](../../lovable/src/contexts/AuthContext.tsx)
- [lovable/src/contexts/DraftContext.tsx](../../lovable/src/contexts/DraftContext.tsx)
- [frontend_spa/src/App.tsx](../../frontend_spa/src/App.tsx)
- [frontend/views.py](../../frontend/views.py)
- [frontend/urls.py](../../frontend/urls.py)
- [infra/build-lovable-production-frontend.ps1](../../infra/build-lovable-production-frontend.ps1)
- [.github/workflows/visual-audit-pr-guardrail.yml](../../.github/workflows/visual-audit-pr-guardrail.yml)
- [skills/webpage-visual-perfection-audit/scripts/create_storage_state.py](../../skills/webpage-visual-perfection-audit/scripts/create_storage_state.py)

Inherit the cutover skill's route, API, runtime-config, and artifact assumptions
first. This skill is allowed to add automation around them, not to contradict
them.

Use [BASELINE.md](./BASELINE.md) only as a reference map after the live source
inventory is regenerated.

## Use This Skill When

- The task is to add or repair end-to-end browser coverage for Lovable-to-Django production flows.
- A recent Lovable pull changed routes, API keys, auth behavior, modal behavior, or mutation flows and the team wants a regression guardrail.
- CI should fail when a user-visible production flow breaks even though unit tests still pass.
- The change spans Django views, runtime config, `frontend_spa`, or build/CI wiring and needs real-browser proof against the Django-served production bundle.

## Non-Negotiable Rules

1. Extract the current flow inventory from the current source every run. Do not assume the baseline still matches.
2. Route parity comes before automation. If `lovable/src/App.tsx` and `frontend_spa/src/App.tsx` disagree, fix that first.
3. Automate flows against Django + built SPA only: `pwsh -File infra/build-lovable-production-frontend.ps1` must succeed before browser checks.
4. Use deterministic seeded data. Prefer existing `bootstrap_*` commands over brittle UI setup.
5. Every extracted current user flow must land in exactly one bucket:
   - `automated_smoke`
   - `automated_full`
   - `blocked_by_lovable_showstopper`
6. There is no permanent `manual_only` escape hatch. If a flow exists in the current product and can be exercised from Django plus the built SPA, automate it.
7. Every `blocked_by_lovable_showstopper` item requires one concise Lovable prompt or explicit user sign-off. Do not silently leave it uncovered.
8. Console errors, `pageerror`, uncaught router/provider errors, CSRF 403s after login, and failed XHR/fetch calls are test failures even if the page partially renders.
9. Prefer accessible selectors and visible text. Only add test-only hooks outside `lovable/` when absolutely necessary.
10. Do not write permanent regression artifacts into `skills/`; only the skill doc and skill-local support files belong here.
11. No extracted flow is considered covered by unit tests, integration-only tests, API-only tests, or manual checks. Flow coverage in this skill means real-browser end-to-end automation.

## When Invoked, Execute This Exact Sequence

### Step 1 - Refresh `lovable/` In Place And Require A Clean Worktree

Run:

```powershell
git pull
git rev-parse HEAD
git -C lovable pull --ff-only
git -C lovable rev-parse HEAD
git -C lovable status
```

If `git -C lovable status` is not clean after the pull, stop immediately and
report the exact dirty paths. Report the Django repo SHA and the refreshed
`lovable/` SHA before continuing.

Then re-read the files in the `Read This First Every Run` section and write a
short inherited-contract summary covering:

- current SPA routes
- current runtime-config/api-key surface
- current auth model (`AuthContext`, modal or full-page login, CSRF behavior)
- current draft model (`DraftContext`, create/save/publish flow)
- current messaging/manage-trip flows
- existing build/CI patterns already present in the repo

Do not write test code before this summary is grounded in current files.

### Step 2 - Extract The Live Flow Matrix From The Current Frontend

Nothing in this step is pre-answered. Read the actual current files every time.
`BASELINE.md` is reference only.

Read the current route and flow sources in full, then scan with these commands:

```powershell
rg -n 'path="|<Route|createBrowserRouter|children:' lovable/src/App.tsx frontend_spa/src/App.tsx
rg -n 'apiGet|apiPost|apiPatch|apiDelete|cfg\.api\.|cfg\.auth\.|requireAuth\(|navigate\(' lovable/src/pages lovable/src/contexts lovable/src/components
rg -n 'handleSubmit|onSubmit|DropdownMenuItem|Dialog|Modal|toast\.' lovable/src/pages lovable/src/components
rg -n 'useNavigate|useLocation|useParams' lovable/src/contexts lovable/src/pages lovable/src/components
rg -n 'cfg\.api\.base' lovable/src/pages lovable/src/contexts lovable/src/components
```

Produce four fresh tables from the current source:

#### 2a. Route Parity Table

One row per route in `lovable/src/App.tsx`, compared to
`frontend_spa/src/App.tsx`.

Columns:

- route
- Lovable component
- production router component
- parity status (`match`, `missing_in_frontend_spa`, `extra_in_frontend_spa`)

#### 2b. Flow Matrix

One row per user journey or mutation entry point currently present in the UI.

Columns:

- flow id
- actor (`guest`, `member`, `host`, `traveler`)
- entry route
- entry UI action
- API calls used
- required auth state
- required seeded data
- visible success signal
- reload persistence check
- current coverage status (`missing`, `partial`, `covered`)

#### 2c. Auth-Sensitive And CSRF-Sensitive Flows

One row per flow that changes behavior after login or depends on auth hydration.

Mandatory rows to inspect if present in current source:

- login page submit
- login modal submit
- any flow using `requireAuth(...)`
- draft create/save/publish
- DM start from trip detail or profile
- inbox send message
- follow/unfollow
- bookmark/unbookmark
- manage-trip mutations
- any POST/PATCH/DELETE immediately after modal login

#### 2d. Data/Setup Map

One row per extracted flow candidate.

Columns:

- flow id
- bootstrap command(s) that provide data
- extra setup required beyond bootstrap
- data owner app (`accounts`, `trips`, `social`, `enrollment`, `interactions`, etc.)
- whether the flow is safe for PR smoke (`yes`, `no`)
- automation status target (`automated_smoke`, `automated_full`, `blocked_pending_analysis`)

After the tables, write a diff summary:

```text
NEW routes vs baseline:
NEW flows vs baseline:
NEW auth-sensitive flows vs baseline:
REMOVED from baseline:
```

If all diffs are none, say so explicitly.

### Step 3 - Decide What Becomes Smoke Or Full

Classify every current flow into exactly one tier:

- `automated_smoke`: fully automated real-browser end-to-end coverage that must run on every PR and prove the core production shell still works
- `automated_full`: fully automated real-browser end-to-end coverage that is also required, even if it only runs locally and optionally in `workflow_dispatch` or nightly
- `blocked_by_lovable_showstopper`: impossible to automate correctly from Django and `frontend_spa` alone

Important:

- `automated_smoke` and `automated_full` are both fully automated end-to-end tests.
- The only difference is execution cadence and suite size.
- The complete requirement is the union of both buckets: every extracted flow must be covered by one of them unless it is a genuine Lovable-only blocker.

Minimum required `automated_smoke` coverage when the corresponding UI exists
today:

1. Guest opens `/` and sees non-blank rendered content with no page crash.
2. Guest opens one list or detail content route (`/trips`, `/trips/:id`, `/experiences`, `/blogs`, etc.) and sees real data.
3. Auth flow succeeds in the browser and the post-login session state is visible in UI.
4. A POST after modal or page login succeeds, specifically to catch stale-CSRF regressions.
5. One draft or trip mutation flow succeeds and persists across reload.
6. One inbox or host-management flow succeeds and persists across reload.

Minimum required `automated_full` coverage when the corresponding UI exists
today:

- profile view and follow/unfollow
- bookmark add/remove
- DM start from a non-inbox surface and land on the correct thread
- inbox send message
- manage-trip decision/removal/cancel/message variants
- blog/experience create/edit/delete routes
- any new flow introduced by the source diff in Step 2

Decision rules:

- A new route without a meaningful assertion is not coverage. Add a visible assertion.
- A mutation without a reload persistence check is not coverage. Re-open the page or refetch and confirm the change held.
- If a flow can only succeed with mock data or a hardcoded frontend placeholder, it is not `automated`; it is `blocked_by_lovable_showstopper`.
- If the test would mutate shared demo data in a way that makes reruns flaky, fix the seed/setup strategy instead of downgrading coverage.
- If a flow is destructive or stateful, isolate or reseed the data and still automate it.
- Every extracted flow must end Step 3 as either automated or blocked by a Lovable-only showstopper.

### Step 4 - Build The Production Artifact And Prepare Deterministic State

Follow [SETUP.md](./SETUP.md) exactly. That file preserves the original Step 4
and Step 4b requirements:

- build from temporary copies, not from a mutating in-place workspace
- fail if `git -C lovable status --short` changes across the build
- seed deterministic data with the smallest complete bootstrap set, or the canonical chain when needed
- extend bootstrap commands before falling back to ad hoc seed helpers
- use seeded demo users for most authenticated flows
- create one storage-state file per user/role through the real login UI
- use separate contexts for multi-user flows
- keep signup isolated as its own flow instead of the suite's root dependency

At minimum, run:

```powershell
pwsh -File infra/build-lovable-production-frontend.ps1
```

### Step 5 - Implement Or Update The Persistent Harness

Follow [HARNESS.md](./HARNESS.md) exactly. Persistent automation created by this
skill belongs in repo-owned paths such as `tests/e2e/`, `.github/workflows/`,
and `pytest.ini`.

The harness must preserve these invariants:

- Python `pytest` plus Playwright, not a Node-based browser runner
- Django serves the built production artifact during test execution
- `artifacts/e2e/` holds traces, screenshots, HTML snapshots, request logs, and similar outputs
- flow helpers stay centralized rather than duplicated across tests
- guest, named-auth, and multi-user context helpers are explicit
- signup-flow helpers remain separate from seeded-login helpers

### Step 6 - Wire The Guardrail Into CI

Follow the CI rules in [HARNESS.md](./HARNESS.md). The resulting workflow under
`.github/workflows/` must:

- install Python and browser-test dependencies from a clean checkout
- install browser binaries
- build the production frontend
- migrate and seed data
- start Django with `--noreload`
- wait for health
- create or refresh the needed storage-state files
- run all `automated_smoke` coverage on every PR
- upload `artifacts/e2e/` on failure and preferably on success as well

If the repo already has one browser-automation workflow, reuse its setup logic
where sensible instead of forking it.

### Step 7 - Local Proof Run Is Mandatory

After implementing or updating the harness, run the relevant local suite against
Django serving the built artifact.

Minimum proof commands:

```powershell
pwsh -File infra/build-lovable-production-frontend.ps1
python manage.py migrate --noinput
python manage.py bootstrap_accounts --verbose
python manage.py bootstrap_trips --verbose --create-missing-hosts
python manage.py bootstrap_blogs --verbose --create-missing-authors
python manage.py bootstrap_social --verbose --create-missing-members
python manage.py bootstrap_enrollment --verbose --create-missing-members
python manage.py bootstrap_interactions --verbose --create-missing-members
python manage.py runserver 127.0.0.1:8000 --noreload
pytest -m smoke tests/e2e
```

If auth flows are covered, also generate or refresh a storage-state file under
`artifacts/auth/` as part of the proof. If multi-user flows are covered,
generate one per participating user.

Do not declare the task done if any of these are unverified:

- production build exits 0
- Django serves the built artifact
- smoke suite passes locally
- browser console/pageerror gate is clean
- at least one authenticated POST after login succeeds
- at least one reload persistence assertion passes

### Step 8 - Resolve Gaps And Blockers In The Right Order

Use [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) as the hard stop/gate document.
Resolve failures in this order:

1. missing route parity or Django entrypoint
2. missing or incorrect Django endpoint or response shape
3. missing or incorrect seed data or bootstrap behavior
4. brittle selector or missing visible assertion in the automation
5. true frontend showstopper inside `lovable/`

For every failing automated flow, first make the best Django-side,
`frontend_spa`, build, seed, or harness correction available outside
`lovable/`. Only write a Lovable prompt when the failure is genuinely trapped
inside `lovable/` and cannot be corrected from Django, `frontend_spa`, build
config, seed/setup, or test harness code.

Every blocked item must name:

- exact route
- exact user-visible symptom
- why Django/test-side fixes are insufficient
- the minimal Lovable prompt required

If multiple blocked failures share the same root cause, merge them into one best
Lovable prompt. The default output target is a single best prompt, not one
prompt per failing test.

## Reporting When Done

Report:

1. Django repo SHA and `lovable/` SHA after pull
2. route and flow diff summary from Step 2
3. final flow classification (`automated_smoke`, `automated_full`, `blocked_by_lovable_showstopper`)
4. files created or updated for the harness and CI
5. production build result
6. local proof commands run and whether they passed
7. browser artifact location
8. Lovable prompt text if one was required, or `No Lovable prompt needed`
