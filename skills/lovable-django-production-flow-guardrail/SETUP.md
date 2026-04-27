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

- stage temporary copies of `lovable/` and `frontend_spa/`
- install and build in the temporary workspace
- write the final artifact to `artifacts/lovable-production-dist/`
- leave the checked-out `lovable/` tree untouched
- fail if `git -C lovable status --short` changes across the build

Do not run browser checks until the build succeeds.

## 2. Prepare Deterministic Seed Data

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

## 3. Auth And Multi-User Session Strategy

Manage authenticated state like this:

1. Do not use signup as the primary setup path for the whole suite.
2. Use seeded demo users as the stable base for most authenticated flows.
3. Create one Playwright storage-state file per user/role through the real
   login UI.
4. Use separate browser contexts for multi-user interaction tests.
5. Use signup only as an isolated disposable-flow test.
6. Prefer login reuse after one verified real login path per user.

`bootstrap_accounts` creates canonical demo users and resets their passwords
when asked. Current seeded users are:

- `mei`
- `arun`
- `sahar`

Default password from `bootstrap_accounts` is `TapneDemoPass!123` unless
overridden.

Preferred storage-state examples:

- `artifacts/auth/mei-storage-state.json`
- `artifacts/auth/arun-storage-state.json`
- `artifacts/auth/sahar-storage-state.json`

Never reuse one authenticated context to impersonate multiple users. Open
independent contexts from different storage-state files so DM, follow, booking,
and host/traveler interactions are exercised as true multi-user flows.

## 4. Implementation Rules For Session Material

- If the existing storage-state helper only supports one account, extend it or
  add a thin wrapper outside `lovable/` so multiple users can be created
  deterministically.
- If role distinctions matter, document which seeded user is the host and which
  is the traveler for each automated flow.
- If a flow requires two interacting authenticated users, the test must open at
  least two contexts and verify the interaction from both sides when the UX
  makes both sides visible.
- Storage-state JSON belongs under `artifacts/auth/` and is not source.
