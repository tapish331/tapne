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
- why Django-side, `frontend_spa`, build, seed, or harness fixes are
  insufficient
- the minimal browser-facing change needed from Lovable

Then package any surviving Scope 1 blockers using
[RULES.md](../../RULES.md) Section 2b rather than inventing local prompt
wording. Merge related blockers into one prompt when they share a root cause.
