# Persistent Harness And CI Rules

This file preserves the original Step 5 and Step 6 requirements while moving
them out of the main operator runbook.

Use this file when implementing or updating the persistent browser guardrail and
the workflow that runs it.

## 1. Harness Location And Preferred Layout

Persistent automation created by this skill belongs in repo-owned paths such as:

- `tests/e2e/`
- `.github/workflows/`
- `pytest.ini` or `[tool.pytest.ini_options]` in `pyproject.toml` if marker configuration is needed

Preferred default layout:

```text
tests/e2e/
  conftest.py
  helpers.py
  server.py
  auth.py
  test_public_smoke.py
  test_auth_and_csrf.py
  test_trip_drafts.py
  test_inbox_and_dm.py
  test_manage_trip.py
  test_profile_and_social.py
  test_experiences.py
```

## 2. Required Implementation Choices

- Use Python `pytest` plus Playwright, not a Node-based browser runner.
- Start Django externally or in a fixture, but always serve the built production artifact through Django.
- Use `artifacts/e2e/` for screenshots, traces, HTML snapshots, request logs, and storage state.
- Keep flow helpers centralized; do not duplicate login, bootstrap, or wait logic across test files.
- If you need markers, define at least `smoke` and `full`.
- If you need a storage-state bootstrap, reuse or adapt the pattern from `skills/webpage-visual-perfection-audit/scripts/create_storage_state.py`.
- Provide explicit helpers for:
  - guest context
  - one authenticated context from a named storage-state file
  - two-user or multi-user concurrent contexts for interaction flows
- Keep signup-flow helpers separate from seeded-login helpers so the suite never accidentally depends on a signup-created account for unrelated tests.

## 3. Test Design Rules

1. Use current runtime routes and visible UI text from the actual source, not guesses.
2. Capture browser `console.error`, `pageerror`, and failed network requests; fail the test on meaningful errors.
3. Assert real user outcomes: visible content, toast text, URL change, DOM state, and persisted backend state after reload.
4. Prefer idempotent operations or disposable seeded data so reruns are stable.
5. Do not assert internal implementation details that users cannot observe unless they are needed to diagnose a production-only failure.
6. For auth flows, explicitly prove that a POST after login works; this is the guardrail against CSRF token rotation bugs.
7. For modal-triggered flows, prove the modal opens from the real UI and not from a synthetic direct function call.
8. If a route is authenticated, the test should cover both the protected unauthenticated path and the authenticated happy path when practical.
9. For multi-user flows, assert the correct actor on each side. Example: user A starts a DM, user B sees the thread or message in a separate authenticated context if the product makes that visible.
10. Signup coverage must verify creation of a fresh account, but the broader suite should continue using seeded reusable accounts unless a test specifically needs a brand-new identity.
11. Do not satisfy a flow with API-level assertions alone if the user journey is browser-visible. The browser path itself must be exercised.

## 4. CI Wiring Rules

Add or update a workflow under `.github/workflows/` for this harness.

Required CI behavior:

- install Python deps from `requirements.txt`
- install skill or test deps needed for Playwright and pytest
- install browser binaries
- build the production frontend
- migrate and seed data
- start Django with `--noreload`
- wait for health
- create storage state if authenticated flows are in the suite
- create or refresh one storage state per seeded user needed by the suite
- run all `automated_smoke` coverage on every PR
- upload `artifacts/e2e/` on failure and preferably on success as well

Recommended shape:

- PR lane: `pytest -m smoke tests/e2e`
- manual or nightly lane: `pytest tests/e2e` or `pytest -m "smoke or full" tests/e2e`
- keep smoke under roughly 15 minutes unless the user explicitly accepts slower CI
- full automation is still required even if the `full` subset does not run on every PR

If the repo has only one browser-automation workflow, do not fork the setup
logic unnecessarily. Reuse patterns from
`.github/workflows/visual-audit-pr-guardrail.yml` where sensible.
