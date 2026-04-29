# Guardrail Troubleshooting

This file is for recurring guardrail-specific triage patterns. It complements
[RULES.md](../../RULES.md); it does not replace or weaken it.

Use [RULES.md](../../RULES.md) for the actual prompt contract, scope
classification, canonical route questions, verification gates, and close-out
wording.

## 1. Triage Order

Resolve gaps in this order:

1. missing route parity or Django entrypoint
2. missing or incorrect Django endpoint or response shape
3. missing or incorrect seed data or bootstrap command behavior
4. brittle selector or missing visible assertion in the automation
5. true frontend showstopper inside `lovable/`

## 2. Keep Flows Automated When They Are Fixable

- If a flow exists in current source and can be exercised from Django plus the
  built production SPA, keep it in `automated_smoke` or `automated_full`.
- Fix seed strategy or harness isolation before downgrading a stateful flow.
- A route without a meaningful browser-visible assertion is not coverage.
- A mutation without a reload or refetch persistence check is not coverage.

## 3. Common Blocker Patterns

Examples of `blocked_by_lovable_showstopper`:

- UI action is cosmetic-only and never calls the network.
- Required CTA has no stable path to the server resource it is supposed to
  create.
- Frontend swallows errors or shows success regardless of failure in a way
  Django cannot correct.
- The only reliable selector would require changing `lovable/` markup and no
  user-visible alternative exists.

## 4. What To Capture For A Blocked Flow

For each blocked flow, record:

- exact route
- exact user-visible symptom
- why Django-side, build, seed, or harness fixes are
  insufficient
- the minimal browser-facing change needed from Lovable

Then package any surviving Scope 1 blockers using
[RULES.md](../../RULES.md) Section 2b rather than inventing local prompt
wording. Merge related blockers into one prompt when they share a root cause.

## 5. Brand CSS Is Served As HTML During Local E2E Runs

- Symptom:
  the browser audit fails with stylesheet MIME-type errors for
  `/static/frontend-brand/tokens.css` or `/static/frontend-brand/overrides.css`,
  often followed by blank or unstyled pages.
- First checks:
  inspect `tests/e2e/server.py`, the actual env passed to `runserver`, and
  whether you bypassed the harness with `E2E_USE_EXISTING_SERVER=1`.
- Likely cause:
  local Django is not running with the same env assumptions as the guardrail
  harness, especially `DEBUG=true`, so those static-brand URLs fall through to
  the SPA shell instead of returning CSS.
- Likely fix scope:
  Scope 3.

## 6. Storage State Exists But The Session Is Not Actually Valid

- Symptom:
  a test starts from a storage-state file but still behaves as a guest, opens
  the login modal again, or fails an immediate authenticated POST.
- First checks:
  inspect `tests/e2e/auth.py`, `tests/e2e/conftest.py`, the seeded account
  password, and whether `E2E_REFRESH_STORAGE_STATE=1` is needed.
- Likely cause:
  the cached file belongs to the wrong user, the password changed during
  bootstrap, or the session cookie/local-storage pair no longer matches the
  `/frontend-api/session/` response.
- Likely fix scope:
  Scope 3 or test-harness code, not Scope 1, unless the browser login path
  itself is visibly broken.

## 7. Apply-Only Trip Flow Regresses Even Though Trip Detail Still Renders

- Symptom:
  an apply-only trip opens `Book Your Trip` instead of `Apply to Join`, omits
  the expected application questions/state, or fails to show
  `Application Pending` after reload.
- First checks:
  inspect `lovable/src/pages/TripDetail.tsx`,
  `lovable/src/components/ApplicationModal.tsx`, `frontend/views.py`, and the
  current tests in `tests/e2e/test_auth_and_csrf.py` and
  `tests/e2e/test_manage_trip.py`.
- Likely cause:
  CTA routing, modal content, submit success, and pending-state persistence are
  separate moving parts and can drift independently.
- Likely fix scope:
  Scope 3 if the payload/state contract is missing; Scope 1 if the rendered
  modal or CTA behavior is wrong inside `lovable/`.
