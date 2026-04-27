---
name: lovable-django-production-flow-guardrail
description: >
  Build and maintain Tapne's Lovable-to-Django production browser guardrail by
  regenerating a live flow matrix from current source, classifying flows into
  automated_smoke, automated_full, or blocked_by_lovable_showstopper, wiring
  deterministic Python Playwright plus pytest coverage and CI outside
  `skills/`, and proving it against Django serving the built production SPA.
  Use when adding or repairing persistent real-browser regression coverage for
  Tapne production flows after Lovable, Django, frontend_spa, auth,
  runtime-config, or CI changes governed by RULES.md.
---

# Lovable -> Django Production Flow Guardrail

[RULES.md](../../RULES.md) is the canonical rules document for this repo. If any
instruction here conflicts with it, follow `RULES.md` and treat this skill as
stale.

This skill is the automation companion to
`skills/lovable-django-production-cutover/SKILL.md`. Use the cutover workflow
to rebuild live route, API, runtime-config, and integration truth from current
source first; use this skill to turn that truth into persistent production
browser guardrails.

Companion docs:

- [BASELINE.md](./BASELINE.md): stable file map, scan targets, and hotspot index
- [SETUP.md](./SETUP.md): production build, bootstrap, and auth/session mechanics
- [HARNESS.md](./HARNESS.md): persistent harness structure, test design, and CI shape
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md): guardrail-specific triage order and blocker patterns

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

### 1. Classify the work and run the repo contract

- Classify the task with [RULES.md](../../RULES.md) Section 4 before touching
  files.
- This skill usually operates in Scope 3, with optional Scope 2 or 4
  follow-through when the live flow audit exposes backend or deployment gaps.
- Run the exact repo pre-flight and start-of-task reporting from
  [RULES.md](../../RULES.md) Sections 1 and 7.
- Do not define alternate pre-flight, prompt wording, route canon,
  verification gates, or close-out wording in this skill.

### 2. Inherit the live cutover contract from current source

Before planning or editing persistent harness code, read these files in full:

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

Then write a short inherited-contract summary covering:

- current SPA routes
- current runtime-config/api-key surface
- current auth model (`AuthContext`, modal or full-page login, CSRF behavior)
- current draft model (`DraftContext`, create/save/publish flow)
- current messaging and host-management flows
- existing build/CI patterns already present in the repo

Use [BASELINE.md](./BASELINE.md) only as a stable index after the live
inventory is regenerated.

### 3. Extract the live flow matrix

Nothing in this step is pre-answered. Read the actual current files every run.

Read the current route and flow sources in full, then run these scans:

```powershell
rg -n 'path="|<Route|createBrowserRouter|children:' lovable/src/App.tsx frontend_spa/src/App.tsx
rg -n 'apiGet|apiPost|apiPatch|apiDelete|cfg\.api\.|cfg\.auth\.|requireAuth\(|navigate\(' lovable/src/pages lovable/src/contexts lovable/src/components
rg -n 'handleSubmit|onSubmit|DropdownMenuItem|Dialog|Modal|toast\.' lovable/src/pages lovable/src/components
rg -n 'useNavigate|useLocation|useParams' lovable/src/contexts lovable/src/pages lovable/src/components
rg -n '@pytest.mark|def test_' tests/e2e -g '*.py'
```

Also run the exact `cfg.api.base` audit required by
[RULES.md](../../RULES.md) Section 5.

Produce four fresh tables from current source:

#### 3a. Route Parity Table

One row per route in `lovable/src/App.tsx`, compared to
`frontend_spa/src/App.tsx`.

Columns:

- route
- Lovable component
- production router component
- parity status (`match`, `missing_in_frontend_spa`, `extra_in_frontend_spa`)

#### 3b. Flow Matrix

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

#### 3c. Auth-Sensitive And CSRF-Sensitive Flows

One row per flow that changes behavior after login or depends on auth
hydration.

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

#### 3d. Data/Setup Map

One row per extracted flow candidate.

Columns:

- flow id
- bootstrap command(s) that provide data
- extra setup required beyond bootstrap
- data owner app (`accounts`, `trips`, `social`, `enrollment`, `interactions`, etc.)
- whether the flow is safe for PR smoke (`yes`, `no`)
- automation status target (`automated_smoke`, `automated_full`, `blocked_pending_analysis`)

After the tables, write a working diff summary against the currently committed
harness coverage:

```text
NEW routes vs current harness:
NEW flows vs current harness:
NEW auth-sensitive flows vs current harness:
REMOVED from current harness:
```

If the repo has no prior guardrail coverage for a category, say so explicitly.

### 4. Classify flows into smoke, full, or blocked

Every extracted current flow must land in exactly one bucket:

- `automated_smoke`: fully automated real-browser end-to-end coverage that
  runs on every PR and proves the core production shell still works
- `automated_full`: fully automated real-browser end-to-end coverage that also
  remains available locally and optionally in manual or scheduled CI
- `blocked_by_lovable_showstopper`: impossible to automate correctly from
  Django and `frontend_spa` alone

Important:

- `automated_smoke` and `automated_full` are both real-browser end-to-end
  coverage.
- The only difference is execution cadence and suite size.
- If a flow exists in the current product and can be exercised from Django plus
  the built production SPA, automate it.

Minimum required `automated_smoke` coverage when the corresponding UI exists in
the current canonical route map:

1. Guest opens `/` and sees non-blank rendered content with no page crash.
2. Guest opens one public content route from current source, such as `/search`,
   `/trips/:tripId`, or `/stories/:storyId`, and sees real data.
3. Auth flow succeeds in the browser and the post-login session state is
   visible in UI.
4. A POST after modal or page login succeeds, specifically to catch stale-CSRF
   regressions.
5. One private create/edit flow from current source, such as `/trips/new`,
   `/trips/:tripId/edit`, `/stories/new`, `/stories/:storyId/edit`, or
   `/profile/edit`, succeeds and persists across reload.
6. One message, social, or host-management flow from current source, such as
   `/messages`, a trip-detail CTA, or `/dashboard/*`, succeeds and persists
   across reload.

Minimum required `automated_full` coverage when the corresponding UI exists in
current source:

- `/users/:profileId` follow/unfollow
- bookmark add/remove from the current detail or bookmarks surface
- DM start from a non-message surface and land on the correct `/messages`
  thread
- inbox send message in `/messages`
- host-management decision/removal/cancel/message variants exposed by current
  source
- story create/edit/delete flows when current source exposes them
- any new flow introduced by the Step 3 source diff

Decision rules:

- A route without a meaningful browser-visible assertion is not coverage.
- A mutation without a reload or refetch persistence check is not coverage.
- If a flow can only succeed with mock data or a hardcoded frontend
  placeholder, it is `blocked_by_lovable_showstopper`.
- If the test would mutate shared demo data in a way that makes reruns flaky,
  fix the seed/setup strategy instead of downgrading coverage.
- If a flow is destructive or stateful, isolate or reseed the data and still
  automate it.
- Package any surviving Scope 1 blockers using
  [RULES.md](../../RULES.md) Section 2b rather than inventing local prompt
  wording.

### 5. Build the production artifact and deterministic state

Follow [SETUP.md](./SETUP.md) exactly. That file covers:

- temporary-workspace builds instead of in-place `lovable/` mutation
- deterministic bootstrap strategy
- seeded-user and storage-state conventions
- multi-user context rules
- signup isolation

At minimum, run:

```powershell
pwsh -File infra/build-lovable-production-frontend.ps1
```

### 6. Implement or update the persistent harness

Follow [HARNESS.md](./HARNESS.md) exactly. Persistent automation created by this
skill belongs in repo-owned paths such as `tests/e2e/`,
`.github/workflows/`, and optionally `pytest.ini`.

The harness must preserve these guardrail-specific invariants:

- Python `pytest` plus Playwright, not a Node-based browser runner
- Django serves the built production artifact during test execution
- `artifacts/e2e/` holds traces, screenshots, HTML snapshots, request logs,
  and similar outputs
- flow helpers stay centralized rather than duplicated across tests
- guest, named-auth, and multi-user context helpers are explicit
- signup-flow helpers remain separate from seeded-login helpers

### 7. Wire the guardrail into CI

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

### 8. Run the mandatory local proof

After implementing or updating the harness, run the relevant local suite
against Django serving the built artifact.

Minimum proof commands:

```powershell
pwsh -File infra/build-lovable-production-frontend.ps1
python manage.py migrate --noinput
# run the smallest complete bootstrap set for the classified smoke suite,
# or the canonical chain from SETUP.md when that is simpler
python manage.py runserver 127.0.0.1:8000 --noreload
pytest -m smoke tests/e2e
```

If auth flows are covered, also generate or refresh the required storage-state
files under `artifacts/auth/` as part of the proof. If multi-user flows are
covered, generate one per participating user.

Do not declare the task done until all of the following are true:

- production build exits 0
- Django serves the built artifact
- smoke suite passes locally
- the shared helpers prove the full browser gate from
  [RULES.md](../../RULES.md) Section 5
- at least one authenticated POST after login succeeds
- at least one reload persistence assertion passes

### 9. Resolve gaps and blockers in the right order

Use [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) for the guardrail-specific
triage order.

For every failing automated flow, first make the best Django-side,
`frontend_spa`, build, seed, or harness correction available outside
`lovable/`. Only escalate to a Lovable prompt when the failure is genuinely
trapped inside `lovable/`.

Use these canonical sources for the final decision:

- [RULES.md](../../RULES.md) Section 2b for prompt structure and wording
- [RULES.md](../../RULES.md) Sections 4 through 6 for scope, route, and
  verification decisions

### 10. Close out through the repo contract

- Use the exact end-of-task reporting contract in
  [RULES.md](../../RULES.md) Section 7.
- Run the `lovable/` exit gate from [RULES.md](../../RULES.md) Section 2 before
  considering the session done.
- If no Scope 1 showstopper remains, use the exact no-prompt line from
  [RULES.md](../../RULES.md) Section 2b.
