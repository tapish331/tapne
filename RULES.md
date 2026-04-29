# RULES.md — Tapne mandatory session rules

This file is the canonical rules-of-engagement for Tapne (tapnetravel.com). It
is auto-loaded into every Claude Code session via the `@RULES.md` import in
`CLAUDE.md`. These rules supersede anything else in the repository, including
`CLAUDE.md`, skill files, and past session memory — unless the user explicitly
countermands a specific rule in-session.

If any instruction anywhere conflicts with what is written here, obey this file
and flag the conflict to the user. Do not silently drift.

---

## Section 1 — Pre-flight (mandatory before any action)

Before reading, editing, or running anything in this repo, bring both repos to
their latest state and state the result.

```bash
git pull
git -C lovable pull
```

Then report:

```
root HEAD: <sha>  <short message>
lovable HEAD: <sha>  <short message>
```

- If either pull fails, stop immediately and surface the failure to the user.
  Do not attempt any further work.
- Skip this step only when the user's message is a pure read-only question
  that touches no files (e.g. "explain what X does"). The moment the work
  shifts to editing, running commands, or building, run the pre-flight first.

---

## Section 2 — `lovable/` is read-only

**The `lovable/` folder is absolutely off-limits for modification.**

- No write, create, rename, patch, move, or delete under `lovable/` — ever.
- The only permitted operation in `lovable/` is `git pull`.
- Never run a tool (Edit, Write, Bash `mv`/`rm`/`sed`/`cp`-into-lovable, etc.)
  whose target path starts with `lovable/`.

### Exit gate (every session, non-negotiable)

Before closing out any session that touched files, run:

```bash
git -C lovable status --porcelain
```

The output must be empty. If anything is listed:

1. Revert the changes immediately (`git -C lovable checkout -- <path>` is fine
   here — the whole point is that nothing Claude writes in `lovable/` is
   legitimate).
2. Report what was reverted.
3. Treat the original task as failed and explain how the write slipped in.

If Scope-1 behaviour genuinely needs to change, the *only* allowed mechanism
is a single consolidated Lovable prompt — see Section 2b.

---

## Section 2b — The Lovable-prompt contract (the only way to change `lovable/`)

When a session finds one or more showstoppers that truly cannot be solved from
any non-Scope-1 scope, batch **all** of them into a single prompt emitted at
the end of the session. Lovable (not Claude) then performs the edits.

### Rules for the prompt

- **One prompt per session, not one per issue.** Accumulate every Scope-1
  showstopper discovered during the session and emit a single consolidated
  prompt at the end. Never emit multiple Lovable prompts from the same
  session, and never emit one mid-session for something that can wait.
- **Zero cross-scope leakage.** Lovable has no access to the Django backend,
  no access to deployment, and no knowledge of either. The prompt must NOT
  reference any of the following (non-exhaustive):
  - Django, Python, views, URL patterns, URL routes, middleware
  - `frontend-api`, `frontend/urls.py`, `frontend/views.py`
  - `_runtime_config_payload`, runtime-config injection, SPA entrypoint
  - CSRF plumbing, cookie names, `csrf.cookie_name`, `csrf.token`
  - `DjangoJSONEncoder`, snake_case vs camelCase debates
  - Cloud Run, Docker, `infra/**`, build scripts, artifact pipeline
  - `settings.py`, `.env`, feature flags
  - Absolute file paths, or any path outside `lovable/src/`
  - Any scope other than Scope 1
- **Describe behaviour in the rendered browser, not implementation.** Talk
  about what the user sees, what they click, and what should happen next —
  not about hooks, contexts, providers, API calls, or architecture.
- **Use browser-facing vocabulary.** In Lovable prompts, prefer terms like
  `rendered app`, `browser app`, `page`, `screen`, `navigation`, `button`,
  `link`, `modal`, and `destination`. Avoid implementation labels such as
  `frontend`, `client`, `router`, `component`, `hook`, `context`,
  `provider`, and `API layer` unless the distinction is truly unavoidable.
- **Completeness over forced brevity.** The prompt must include every
  non-negotiable user-visible requirement needed for Lovable to complete the
  job in one pass. If the task involves multiple states or views, spell out
  the default state, visible modes, tabs, or intents, filters, sort choices,
  pagination/count rules, click-through outcomes, preserved query state,
  empty states, and any desktop/mobile placement rules that materially affect
  behaviour. Do not omit a required behaviour just to stay terse.
- **First-prompt sufficiency is the default.** Treat the first Lovable prompt
  for a page or flow as an acceptance-spec intended to close the Scope-1 work
  in one pass. Do not send a prompt while material browser-visible ambiguity
  remains on the core flow. If the visible contract is not yet explicit enough
  to make follow-up prompts rare, keep analysing and expand the first prompt
  instead of planning to iterate.
- **Entry-path uniformity means state uniformity, not just route cleanup.** If
  the task involves unifying navigation, browse entry, or equivalent user
  intents, the prompt must cover all visible entry surfaces that can express
  that intent — including nav items, CTAs, shortcuts, content cards, tiles,
  rows, and result cards — and must define the required landing state, not
  just the route path. Where uniformity matters, spell out the canonical
  browser-visible landing state, including query state, selected mode, tab, or
  intent, active chips or pills, and filter cues that the user should see on
  arrival.
- **Name the reference flow when exact equivalence matters.** If a prompt
  requires two or more entry paths to land in the same experience, identify
  the authoritative reference flow and explicitly list the browser-visible
  arrival-state fields that must match it. Where relevant, name the exact
  fields rather than relying on phrases like "same behavior" or "same state" —
  for example route/query state, selected mode, tab, or intent, visible search
  text, default sort or ranking state, active chips or pills, filter cues,
  counts, and framing text.
- **Follow-up prompts must restate retained behaviour on coupled flows.** If
  a follow-up Lovable prompt touches a multi-state or tightly coupled page,
  flow, or surface, restate the full retained behavioural contract — not just
  the newly observed delta symptoms — unless the required change is truly
  isolated to one element or one state.
- **Follow-up prompts are the exception, not the workflow.** Needing a
  follow-up prompt on the same page or flow should be rare and treated as a
  prompt-quality miss unless new facts only became knowable after real browser
  verification. Before emitting any follow-up prompt, assume the burden is on
  the prompt writer to show why the first prompt could not reasonably have
  carried the missing requirement.
- **Functional strictness, visual freedom.** The prompt must be strict about
  browser-visible requirements and loose about aesthetic execution. State the
  hard constraints clearly, but do not micromanage pixels, spacing,
  typography, or animation unless the user explicitly requires it. Unless the
  user says otherwise, prompts should leave room for Lovable to maximize
  beauty, clarity, distinctiveness, traffic growth, and retention within the
  stated behavioural constraints.
- **Showstopper test — all three must be true to include an item:**
  1. The required behaviour exists (or should exist) in the rendered
     app in the browser — not just in mock or dev-only code.
  2. It cannot be served by any change in Scopes 2–6.
  3. Its absence causes a visible, user-facing failure on a production route.
- **Mandatory structure** (single block; prefer ≤ 300 words, but allow up to
  550 when needed to preserve functional completeness for a single page or
  flow overhaul):

  ```
  CONTEXT: <one paragraph describing what the user sees today in the browser,
    across all batched items>
  PROBLEM:
    1. <one line per distinct visible symptom>
    2. ...
  REQUIRED CHANGE:
    1. <concrete browser-visible change, matching PROBLEM item 1>
    2. ...
  SUCCESS CRITERIA:
    1. <observable pass/fail checks Lovable must satisfy in the browser>
    2. ...
  DO NOT CHANGE:
    - <list Lovable behaviours/components that must remain untouched to
      prevent regression>
  ```

- **Pre-send self-review gate.** Before surfacing the prompt to the user,
  scan it for these forbidden tokens: `django`, `python`, `frontend-api`,
  `frontend/urls`, `frontend/views`, `csrf`, `runtime
  config`, `cloud run`, `docker`, `settings.py`, `.env`, and any absolute
  path starting with `/`. If any match — rewrite until clean.
- **Plain text only — pastable directly into Lovable.** The prompt is
  meant to be copy-pasted verbatim. Emit it as raw text: no markdown
  blockquotes (no leading `>`), no code fences, no bold/italic, no
  headings, no link syntax. Keep the CONTEXT / PROBLEM / REQUIRED CHANGE /
  SUCCESS CRITERIA / DO NOT CHANGE structure and the numbered lists, but as
  plain text.
- **No prompt = no problem.** If no true Scope-1 showstopper was found, end
  the session with the explicit line
  *"No Lovable prompt needed — all gaps resolved from Scopes 2–6."*
  Never fabricate a prompt to look thorough.

---

## Section 3 — Django is strictly backend

Django owns logic, data, and plumbing. It does NOT own what the user sees.

### Django may own

- JSON API endpoints (`/frontend-api/*`)
- SPA entrypoint shells that inject `window.TAPNE_RUNTIME_CONFIG`
- Auth / session plumbing, CSRF issuance, OAuth callback handling
- Models, migrations, payload builders, management commands, admin
- Health, runtime status, sitemap, robots, site-verification files
- Search backend, uploads backend, storage abstraction

### Django may NOT own

- User-facing visual layout or design tokens
- Client-side interactivity (JS behaviour end users see)
- Page-level HTML intended to be rendered to end users on production routes
- Any CSS, JS, or template that duplicates a Lovable component

### Retired (do not reintroduce)

The following legacy Django-frontend artifacts were retired in the SPA
cutover. They must not be reintroduced — any visual or UX gap is a Scope 1
(Lovable prompt) concern, not a Django template concern:

- `static/css/lovable-parity.css`, `static/css/tapne.css`
- `static/js/tapne-ui.js`, `static/js/trip-form-builders.js`
- `templates/pages/**`
- `templates/partials/**`
- `templates/base.html`, `templates/404.html`
- `LOVABLE_FRONTEND_ENABLED` toggle (and the `else:` fallback branch it
  used to gate in `tapne/urls.py`)
- Django-rendered page views in `accounts/trips/blogs/feed/social/
  enrollment/interactions/reviews/activity/settings_app/search` (views
  that called `render(request, "pages/...html")`)
- Django auth form pages (`/accounts/login/`, `/accounts/signup/`,
  `/accounts/logout/`) — auth is Lovable-modal + `/frontend-api/auth/*` only

If a task would "normally" touch any of these, stop and re-classify as
Scope 1 (Lovable prompt) or Scope 3 (integration fix).

### Invariants

- **All frontend entities originate in `lovable/`.** If a visual or UX gap
  exists, the fix path is a Lovable prompt — never a Django template.
- Production always serves the SPA. There is no Django-rendered fallback;
  Django owns APIs, admin, OAuth, and file-serving only.

---

## Section 4 — The six scopes (categorize before acting)

Every requested change, bug report, or feature MUST be classified into
**exactly one** of the six scopes before any file is touched. Announce the
classification in the first line of your reply so the user can redirect.

| # | Scope | Allowed paths / responsibilities |
|---|---|---|
| 1 | **Lovable frontend** | `lovable/**` — read-only; only change via a Lovable prompt (Section 2b) |
| 2 | **Django backend** | `*/models.py`, `*/views.py` (non-SPA), `*/urls.py` (non-SPA), `*/forms.py`, `*/admin.py`, `*/management/**`, payload builders, JSON endpoints in `frontend/views.py`, API routes in `frontend/urls.py`, migrations |
| 3 | **Frontend–backend integration** | SPA entrypoint + runtime-config injection in `frontend/views.py`, SPA shell routes in `frontend/urls.py`, `lovable/src/types/*.ts` contracts (read-only — diff only), `_runtime_config_payload()`, CSRF plumbing, response-shape alignment |
| 4 | **Deployment** | `infra/**`, `Dockerfile*`, `docker-compose*.yml`, Cloud Run YAML, build scripts, artifact pipeline, deploy workflow |
| 5 | **Config** | `.env*`, `tapne/settings.py` flags, feature toggles, secret wiring, `.claude/settings*.json`, Django `manage.py` plumbing |
| 6 | **Auxiliary** | `skills/**`, `RULES.md`, `CLAUDE.md`, `README*`, docs, memory, comments-only edits |

### Rules for categorization

- If a request spans two scopes, split it into two classified sub-tasks
  **before touching any file**. Each sub-task is announced and executed
  independently.
- Only Scope 1 is read-only. Every other scope is editable, under the
  per-scope rules in Section 5.
- When in doubt between Scope 2 and Scope 3: if the change is the JSON shape
  or the plumbing that couples Django output to Lovable expectations, it's
  Scope 3. Pure business logic / DB behaviour is Scope 2.

---

## Section 5 — Per-scope operating rules (distilled from skill files)

### Scope 3 — Integration invariants

- **snake_case everywhere.** No camelCase conversion, ever.
- Every `JsonResponse` uses `DjangoJSONEncoder`. Never raw `json.dumps`.
- For every TypeScript interface the frontend consumes: verify every
  required field appears in the Django return dict with the exact snake_case
  name, including the shape of every array element. Walk the interface
  field-by-field; don't shortcut.
- Run `grep -rn "cfg\.api\.base" lovable/src/pages lovable/src/contexts
  lovable/src/components --include="*.ts" --include="*.tsx"` every session.
  These interpolated URLs bypass the `TapneRuntimeConfig.api` audit and have
  burned production before.
- Messaging / DM shapes live in `lovable/src/types/messaging.ts`, not
  `api.ts`. Do not skip it.
- `csrfHeaders()` in `lovable/src/lib/api.ts` must read the CSRF value live
  from `document.cookie` (via `c.csrf.cookie_name`), falling back to
  `c.csrf.token` only when the cookie row is absent. If Lovable regresses
  this — Lovable prompt, not a Django workaround.
- Any React context calling `useNavigate` / `useLocation` / `useParams` must
  be rendered **inside** `RootLayout`, never wrapping `<RouterProvider>`.
  Applies in particular to `DraftProvider`.
- Do not reintroduce a second SPA source tree or alias-based production
  override layer. `lovable/` is the sole frontend source of truth; Scope 3 may
  only adapt Django runtime/config contracts to match it.
- Auth-data loads in contexts must depend on a live `useAuth().isAuthenticated`,
  not the frozen `cfg.session.authenticated` bootstrap snapshot.

### Scope 4 — Deployment invariants

- `infra/build-lovable-production-frontend.ps1` runs **before** the Docker
  image is built. Never ship a stale `artifacts/lovable-production-dist/`.
- Cloud Run smoke paths override to `-SmokeCssPath /` +
  `-SmokeJsPath /sitemap.xml`. The old Django-template defaults 404 after
  the SPA cutover.
- Secrets required for every deploy: `GOOGLE_CLIENT_ID`,
  `GOOGLE_CLIENT_SECRET`, `BASE_URL` (derived from `CANONICAL_HOST`).
- Backend-only URLs must never be shadowed by the SPA catch-all in
  `tapne/urls.py`: `/admin/`, `/health/`, `/runtime/`, `/uploads/`,
  `/search/`, `/accounts/login/`, `/accounts/signup/`, `/sitemap.xml`,
  `/robots.txt`, `/u/<username>/`, `/assets/...`, `/google*.html`.

### Scope 2 — Backend invariants

- New API endpoints ship in `frontend/views.py` + `frontend/urls.py`.
- Responses are built via typed payload builders (`build_*_payload_for_*`)
  and `TypedDict` shapes. Views do not hand-roll context dicts.
- Demo fallbacks live under `feed/models.py` typed demo payloads. No
  hardcoded fake data inside view bodies.
- Authenticated-only views return `_member_only_error()` (401) before any
  DB access when `request.user` is anonymous.
- `?verbose=1` / header `X-Tapne-Verbose: 1` enables detailed ranking logs.

### Scope 5 & 6 — Config / Auxiliary

- Never commit secrets. `.env*`, Playwright storage-state JSONs, and
  service-account keys are secrets.
- Skill edits (Scope 6) never bypass these rules — a skill that tells
  Claude to edit `lovable/` is wrong; update the skill to conform before
  running it.

### Verification gate (applies to Scopes 2, 3, 4)

HTTP 200 + injected runtime config is **not enough** to close a task. For
every changed route:

1. Start the Django server.
2. If `lovable/` was pulled or changed in the session, rebuild
   `artifacts/lovable-production-dist` from the checked-out Lovable source
   before browser verification. Do not assume a `git -C lovable pull`
   changes what Django serves until the production artifact is rebuilt.
3. Open the route in a real browser via Playwright (or equivalent).
4. Wait for hydration / network-idle.
5. Confirm all of the following:
   - `#root` contains rendered content (not blank).
   - Zero `pageerror` events during initial render.
   - Zero `console.error` messages during initial render.
   - The JS bundle is served with a JavaScript MIME type
     (`text/javascript` / `application/javascript`), never `text/plain`.
6. If any check fails, the task is not done.

---

## Section 6 — Planned-vs-deployed page audit

Two standing cleanup rules run on every substantive session.

### Canonical route map (authoritative — no other SPA routes are permitted)

| Route | Visibility | Description |
|---|---|---|
| `/` | public | Homepage |
| `/search` | public | Global search (trips, destinations, stories, users) |
| `/trips/:tripId` | public | Trip detail |
| `/trips/new` | private | Create trip (supports `?mode=preview`) |
| `/trips/:tripId/edit` | private | Edit trip (supports `?mode=preview`) |
| `/stories/:storyId` | public | Story detail |
| `/stories/new` | private | Create story (supports `?mode=preview`) |
| `/stories/:storyId/edit` | private | Edit story (supports `?mode=preview`) |
| `/users/:profileId` | public | User profile |
| `/profile/edit` | private | Edit own profile (supports `?mode=preview`) |
| `/bookmarks` | private | Saved items |
| `/messages` | private | Inbox and chat |
| `/notifications` | private | Notification centre |
| `/settings` | private | Account settings |
| `/dashboard` | private | Dashboard overview |
| `/dashboard/trips` | private | Trip management hub |
| `/dashboard/stories` | private | Story management hub |
| `/dashboard/reviews` | private | Review management hub |
| `/dashboard/subscriptions` | private | Subscription management hub |
| `/404` | system | Not found page |

**Invariants for this map:**
- Auth is modal-only — no `/login` or `/signup` routes exist or should ever be added.
- Preview is not a separate route; it uses `?mode=preview` on the create/edit routes.
- Unauthorized access opens the auth modal; there is no `/unauthorized` route.
- Join and review actions are modals triggered from `/trips/:tripId`, not separate routes.

### Source of truth

- **Canonical routes** are the table above. That list is exhaustive — no route outside it
  is valid.
- **Planned routes** are verified against `lovable/src/App.tsx`; every route in the
  canonical map must have a matching `<Route>` there.
- **Deployed SPA-served routes** come from `frontend/urls.py` +
  `tapne/urls.py` (SPA entrypoint URLs → `frontend_entrypoint_view`).

### Drift rules

- A route that exists in `frontend/urls.py` as an SPA entrypoint but does **not** appear
  in the canonical route map above → **orphan**; remove it in a Scope-3 cleanup.
- A route in the canonical map above that has no matching SPA entrypoint in
  `frontend/urls.py` → **missing**; add the entrypoint in Scope 3 the same session.
- A route that exists in both but points at a stale component name → fix in Scope 3.

### Backend-only routes (never SPA)

`/admin/`, `/health/`, `/runtime/`, `/uploads/`, `/search/`,
`/accounts/login/`, `/accounts/signup/`, `/sitemap.xml`, `/robots.txt`,
`/u/<username>/`, `/assets/...`, `/google*.html`. If one of these ever
resolves into the SPA shell, that is a bug.

---

## Section 7 — Reporting contract

### Start of every non-trivial task (≥ 1 file edit)

First line of the reply, literally:

```
Scope: <1-6 name>
Pre-flight: root <sha>, lovable <sha>
```

### End of every task

Report:

1. What changed (file paths, under their scope).
2. Output of `git status --short` for the root repo.
3. Output of `git -C lovable status --porcelain` — **must be empty**.
4. Verification evidence (which routes were opened, what the browser showed).
5. Either the consolidated Lovable prompt (Section 2b) or the explicit line
   *"No Lovable prompt needed — all gaps resolved from Scopes 2–6."*

If step 3 is non-empty, revert the Lovable changes, mark the task failed,
and describe how the write happened.
