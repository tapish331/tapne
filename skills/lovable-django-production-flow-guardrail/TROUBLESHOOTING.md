# Gap Protocol And Acceptance Gates

This file preserves the original Step 8 and checklist requirements while moving
them out of the main operator runbook.

Use this file whenever the harness fails, coverage cannot yet be classified, or
you need to decide whether a problem is Django-fixable or a true Lovable
showstopper.

## 1. Gap Handling Protocol

Resolve gaps in this order:

1. missing route parity or Django entrypoint
2. missing or incorrect Django endpoint or response shape
3. missing or incorrect seed data or bootstrap command behavior
4. brittle selector or missing visible assertion in the automation
5. true frontend showstopper inside `lovable/`

For every failing automated flow, first make the best Django-side,
`frontend_spa`, build, seed, or harness correction available outside
`lovable/`. Only write a Lovable prompt when the failure is genuinely trapped
inside `lovable/` and cannot be corrected from Django, `frontend_spa`, build
config, seed/setup, or test harness code.

Examples of `blocked_by_lovable_showstopper`:

- UI action is cosmetic-only and never calls the network
- required CTA has no stable path to the server resource it is supposed to create
- frontend swallows errors or shows success regardless of failure in a way Django cannot correct
- the only reliable selector would require changing `lovable/` markup and no user-visible alternative exists

Every blocked item must name:

- exact route
- exact user-visible symptom
- why Django/test-side fixes are insufficient
- the minimal Lovable prompt required

If multiple blocked failures share the same root cause, merge them into one best
Lovable prompt. The default output target is a single best prompt, not one
prompt per failing test.

## 2. Acceptance Gates

Any failure in the following checklists is a stop condition.

### Checklist A - Production-Only Execution

- [ ] No test points at the Lovable dev server
- [ ] All flows run against Django at `http://127.0.0.1:8000` or equivalent
- [ ] `artifacts/lovable-production-dist/index.html` exists before browser tests start

### Checklist B - Flow Coverage Completeness

- [ ] Every extracted flow from Step 2 is classified
- [ ] Every `automated_smoke` flow is automated
- [ ] Every `automated_full` flow is automated
- [ ] No extracted flow is left uncovered except genuine Lovable-only blockers
- [ ] Every automated flow is verified through a real browser end-to-end path

### Checklist C - Auth And CSRF

- [ ] Modal or page login is covered by real browser interaction
- [ ] A POST, PATCH, or DELETE after login succeeds in the same browser session
- [ ] No 403 or 401 mismatch is hidden by optimistic UI
- [ ] Signup is covered as its own isolated flow, not as the global auth setup for the suite
- [ ] Multi-user flows use separate authenticated contexts, not one reused session

### Checklist D - Browser Stability

- [ ] No `pageerror`
- [ ] No unhandled `console.error`
- [ ] No router/provider crash such as `useNavigate() may be used only in the context of a <Router> component`
- [ ] No failed XHR or fetch that the test ignores

### Checklist E - Persistence Assertions

- [ ] Every mutation flow verifies a visible postcondition
- [ ] At least one reload or refetch proves the mutation persisted
- [ ] Tests are rerunnable without manual database cleanup

### Checklist F - CI Readiness

- [ ] Workflow installs all needed deps from a clean checkout
- [ ] Workflow seeds deterministic data
- [ ] Workflow uploads browser artifacts
- [ ] PR lane runs only the intended smoke subset
- [ ] Full lane remains available locally or via manual dispatch
