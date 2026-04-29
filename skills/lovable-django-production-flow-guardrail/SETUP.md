# Build, Seed, And Auth Setup

Use [RULES.md](../../RULES.md) for repo-wide policy: pre-flight,
`lovable/` restrictions, scope decisions, verification gates, and close-out.
Use this file only for guardrail-specific build, seed, and auth/session
mechanics.

## 1. Build The Production Artifact First

Run:

```powershell
pwsh -File infra/build-lovable-production-frontend.ps1
```

The build script must:

- stage a temporary copy of `lovable/`
- install and build in the temporary workspace
- write the final artifact to `artifacts/lovable-production-dist/`
- leave the checked-out `lovable/` tree untouched
- build only from `lovable/`, not from any shadow SPA overlay
- fail if `git -C lovable status --short` changes across the build

Do not run browser checks until the build succeeds.

If `Test-Path frontend_spa` returns `True` or
`rg -n 'frontend_spa|@frontend/' -S` finds a live build reference, fix that
first. The guardrail only counts when Django serves an artifact sourced solely
from `lovable/`.

The shell equivalent is:

```bash
bash infra/build-lovable-production-frontend.sh
```

## 2. Use The Harness-Managed Django Server Environment

Current guardrail proof should normally rely on `tests/e2e/server.py`, not on
ad hoc local `runserver` commands.

That helper currently forces the environment needed for stable local browser
audits, including:

- `DEBUG=true`
- `LOVABLE_FRONTEND_ENABLED=true`
- `LOVABLE_FRONTEND_REQUIRE_LIVE_DATA=true`
- `TAPNE_ENABLE_DEMO_DATA=false`
- deterministic local DB and allowed-host defaults

Those defaults matter because local browser audits will otherwise regress on
problems like `/static/frontend-brand/*.css` being served as SPA HTML instead of
CSS. Only bypass the harness-managed server when you are intentionally
reproducing an existing-server issue.

## 3. Prepare Deterministic Seed Data

Use existing bootstrap commands as the primary source of deterministic data.
Prefer the smallest complete set that satisfies the classified flow suite, but
the canonical all-up seed chain is:

```powershell
python manage.py migrate --noinput
python manage.py bootstrap_accounts --verbose
python manage.py bootstrap_feed --verbose --create-missing-members
python manage.py bootstrap_search --verbose --create-missing-member
python manage.py bootstrap_trips --verbose --create-missing-hosts
python manage.py bootstrap_blogs --verbose --create-missing-authors
python manage.py bootstrap_social --verbose --create-missing-members
python manage.py bootstrap_enrollment --verbose --create-missing-members
python manage.py bootstrap_interactions --verbose --create-missing-members
python manage.py bootstrap_reviews --verbose --create-missing-members
python manage.py bootstrap_activity --verbose --create-missing-members
python manage.py bootstrap_settings --verbose --create-missing-members
python manage.py bootstrap_media --verbose --create-missing-members --create-missing-targets
python manage.py bootstrap_runtime --verbose --create-missing-members
```

If a needed flow still lacks seed data after the canonical chain:

1. first extend or correct the relevant Django bootstrap command
2. only if that is inappropriate, add a narrowly scoped test seed helper
   outside `lovable/`

Do not hide missing seed coverage inside the test body with ad hoc DB writes
unless the flow genuinely requires ephemeral test-only records.

## 4. Auth And Multi-User Session Strategy

Manage authenticated state like this:

1. Do not use signup as the primary setup path for the whole suite.
2. Use seeded demo users as the stable base for most authenticated flows.
3. Create one Playwright storage-state file per user/role through the real
   login UI, using `tests/e2e/auth.py` as the default helper.
4. Use separate browser contexts for multi-user interaction tests.
5. Use signup only as an isolated disposable-flow test.
6. Prefer login reuse after one verified real login path per user.
7. Prefer the current navbar modal login path; do not rely on retired `/login`
   or `/signup` routes for setup.

`bootstrap_accounts` creates canonical demo users and resets their passwords
when asked. Current seeded users are:

- `mei`
- `arun`
- `sahar`

Default password from `bootstrap_accounts` is `TapneDemoPass!123` unless
overridden.

Preferred storage-state examples:

- `artifacts/auth/mei.storage-state.json`
- `artifacts/auth/arun.storage-state.json`
- `artifacts/auth/sahar.storage-state.json`

Set `E2E_REFRESH_STORAGE_STATE=1` when you need to force regeneration. Without
that flag, `tests/e2e/auth.py` should reuse an existing valid session file.

Never reuse one authenticated context to impersonate multiple users. Open
independent contexts from different storage-state files so DM, follow, booking,
and host/traveler interactions are exercised as true multi-user flows.

## 5. Implementation Rules For Session Material

- Prefer extending `tests/e2e/auth.py` before adding a second storage-state
  mechanism. Reach for
  `skills/webpage-visual-perfection-audit/scripts/create_storage_state.py` only
  when you explicitly need a separate CLI path outside the guardrail harness.
- If role distinctions matter, document which seeded user is the host and which
  is the traveler for each automated flow.
- If a flow requires two interacting authenticated users, the test must open at
  least two contexts and verify the interaction from both sides when the UX
  makes both sides visible.
- Storage-state JSON belongs under `artifacts/auth/` and is not source.
