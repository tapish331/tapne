# Troubleshooting

This file is for recurring cutover-specific failure patterns. It complements
[RULES.md](../../RULES.md); it does not replace or weaken it.

Use [RULES.md](../../RULES.md) for the actual verification gates, canonical
route rules, scope boundaries, and prompt/reporting contract.

## `cfg.api.base` interpolation drift

- Symptom:
  named API keys look correct, but one or two routes still 404 or hit the wrong
  Django endpoint.
- Where to inspect:
  the exact `cfg.api.base` audit required by
  [RULES.md](../../RULES.md) Section 5, plus the affected page/component and
  `frontend/urls.py`.
- Likely fix scope:
  Scope 3 when the URL mapping or runtime-config coupling is wrong; Scope 1 only
  if the browser behavior itself must change.
- Relevant rules:
  [RULES.md](../../RULES.md) Sections 4, 5, and 6.

## Messaging contract mismatch

- Symptom:
  inbox or thread views partially render, crash on nested message fields, or
  behave differently from the rest of the API audit.
- Where to inspect:
  `lovable/src/types/messaging.ts`, the consuming messages/inbox pages, and the
  Django DM payload builders/views in `frontend/views.py`.
- Likely fix scope:
  Scope 3 when the response shape or integration contract is wrong; Scope 2 only
  if the underlying backend logic is correct but incomplete.
- Relevant rules:
  [RULES.md](../../RULES.md) Sections 4 and 5.

## CSRF fails after modal login

- Symptom:
  GETs work, but POST/PATCH/DELETE calls fail after a successful modal login or
  after auth state changes without a full page reload.
- Where to inspect:
  `lovable/src/lib/api.ts`, current cookie-reading behavior, and the affected
  mutation flow.
- Likely fix scope:
  Scope 1 if the Lovable-side CSRF lookup regressed; Scope 3 only for the
  surrounding integration proof and audit.
- Relevant rules:
  [RULES.md](../../RULES.md) Sections 2b, 4, and 5.

## Router-hook provider crash

- Symptom:
  the shell loads, then the app throws router/provider errors such as
  `useNavigate()` outside router context.
- Where to inspect:
  `frontend_spa/src/App.tsx`, `lovable/src/contexts/DraftContext.tsx`, and any
  provider using `useNavigate`, `useLocation`, or `useParams`.
- Likely fix scope:
  Scope 3.
- Relevant rules:
  [RULES.md](../../RULES.md) Sections 4 and 5.

## Frozen bootstrap auth state

- Symptom:
  pages or contexts behave as though the user is still anonymous or still
  authenticated after the live session state has changed.
- Where to inspect:
  `lovable/src/contexts/AuthContext.tsx`, `lovable/src/contexts/DraftContext.tsx`,
  and any context/page that keys off bootstrap session data instead of live
  `useAuth().isAuthenticated`.
- Likely fix scope:
  Scope 1 if the browser-side behavior depends on stale state; Scope 3 for the
  contract audit around it.
- Relevant rules:
  [RULES.md](../../RULES.md) Sections 2b, 4, and 5.

## Anonymous 401 path crashes UI

- Symptom:
  unauthenticated requests return 401 as expected, but the consuming screen
  still crashes, toasts success, or assumes member-only arrays/objects exist.
- Where to inspect:
  the affected page or context, `_member_only_error()` callers, and any success
  UI shown on an anonymous path.
- Likely fix scope:
  Scope 2 if Django is not returning the correct early member-only error; Scope
  1 if the browser behavior is wrong even though the 401 path is correct; Scope
  3 if the contract between them is mismatched.
- Relevant rules:
  [RULES.md](../../RULES.md) Sections 2b, 4, and 5.

## No-op mutations in modal, DM-start, or host controls

- Symptom:
  a submit, CTA, or host-control action closes UI, navigates, or shows a toast
  without creating or mutating the expected server-side state.
- Where to inspect:
  affected Lovable page/component handlers, API call sites, and the mapped
  Django endpoint/view.
- Likely fix scope:
  Scope 1 when the visible browser behavior never makes the required request;
  Scope 3 when the request exists but is wired to the wrong route or shape; Scope
  2 when backend behavior is missing behind a correct contract.
- Relevant rules:
  [RULES.md](../../RULES.md) Sections 2b, 4, 5, and 6.

## Backend-owned route shadowed by the SPA

- Symptom:
  a backend-owned URL renders the SPA shell or loses its expected backend
  response.
- Where to inspect:
  `frontend/urls.py`, `tapne/urls.py`, and the backend-only route list in
  [RULES.md](../../RULES.md) Section 6.
- Likely fix scope:
  Scope 3.
- Relevant rules:
  [RULES.md](../../RULES.md) Sections 4, 5, and 6.
