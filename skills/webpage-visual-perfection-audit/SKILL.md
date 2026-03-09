---
name: webpage-visual-perfection-audit
description: End-to-end visual QA for real rendered website pages (desktop and mobile), including URL discovery, screenshot capture, and exhaustive per-page defect reporting. Use when Codex must audit what users actually see in the browser (not source code), find all visible UI flaws, enforce pixel-level quality, or produce page-by-page visual bug reports with severity and fixes.
---

# Webpage Visual Perfection Audit

Audit rendered pages exactly as users see them. Capture real browser screenshots first, then verify intent-to-render conformance, then complete exhaustive human visual QA.

## Core Rules

1. Analyze rendered webpages, not source code.
2. Capture desktop and mobile views for every page in scope.
3. Extract visual intent contracts from code before final judging.
4. Use the full rubric in `references/visual-rubric.md`.
5. Report every non-perfect visual issue, even if minor.
6. Set reasoning effort to the highest available mode before judging subtle issues.
7. Provide actionable fixes and acceptance criteria for each issue.
8. Do not mark a page `PASS` while unresolved high-confidence intent violations remain.

## Workflow

### 1. Define scope

Collect:
- `base_url` (required)
- authenticated or public scope
- include/exclude URL patterns
- max pages and crawl depth

If authenticated pages are required, create a Playwright `storage_state` JSON first and pass it to the capture script.

Generate storage state (recommended via env vars so credentials are not written to shell history):

```bash
$env:TAPNE_AUDIT_USERNAME="<admin-username>"
$env:TAPNE_AUDIT_PASSWORD="<admin-password>"
python skills/webpage-visual-perfection-audit/scripts/create_storage_state.py \
  --base-url "http://localhost:8000" \
  --output "artifacts/auth/admin-storage-state.json"
```

Then run capture with that state:

```bash
python skills/webpage-visual-perfection-audit/scripts/crawl_and_capture.py \
  --base-url "http://localhost:8000" \
  --storage-state "artifacts/auth/admin-storage-state.json" \
  --output-dir "artifacts/visual-audit-admin" \
  --max-pages 200 \
  --max-depth 4
```

Never commit storage state files. Treat them as secrets.

### 2. Capture real page renders

Run:

```bash
python skills/webpage-visual-perfection-audit/scripts/crawl_and_capture.py \
  --base-url "https://example.com" \
  --output-dir "artifacts/visual-audit" \
  --max-pages 200 \
  --max-depth 4
```

Optional flags:
- `--sitemap-url` to seed from sitemap XML
- `--seed-url` to force critical entry pages
- `--include-regex` and `--exclude-regex` to constrain scope
- `--storage-state` for authenticated paths
- `--no-mobile` or `--no-desktop` for targeted runs

Install skill-local dependencies once per environment:

```bash
python -m pip install -r skills/webpage-visual-perfection-audit/requirements.txt
python -m playwright install chromium
```

### 3. Extract visual intents (code-aware)

Generate route-level visual contracts from templates/CSS/JS:

```bash
python skills/webpage-visual-perfection-audit/scripts/extract_visual_intents.py \
  --pages-json "artifacts/visual-audit/pages.json" \
  --repo-root "." \
  --output-dir "artifacts/visual-audit" \
  --strict
```

Required outputs:
- `intent_catalog.json`
- `intent_catalog.md`
- `intent_evidence_index.tsv`

Intent records must include:
- `intent_id`
- `route` and `route_url`
- `component_label`
- `intent_type`
- `locator_css`
- `expected_rule`
- `thresholds`
- `breakpoints`
- `interaction_profile`
- `confidence`
- `severity_if_broken`
- `evidence` with `file` and `line`

### 4. Validate intents against real renders

Run browser conformance checks from `intent_catalog.json`:

```bash
python skills/webpage-visual-perfection-audit/scripts/validate_visual_intents.py \
  --base-url "https://example.com" \
  --pages-json "artifacts/visual-audit/pages.json" \
  --intent-catalog "artifacts/visual-audit/intent_catalog.json" \
  --output-dir "artifacts/visual-audit" \
  --storage-state "artifacts/auth/admin-storage-state.json" \
  --strict-high-confidence
```

Required outputs:
- `intent_conformance.json`
- `intent_violations.md`
- `conformance_screenshots/`

PR guardrail rule:
- In CI for pull requests, run Stage 3 + Stage 4 for homepage plus shared shells.
- Always enable `--strict-high-confidence` so any `High|Critical` + `confidence>=0.90` failure exits non-zero.

Validation matrix:
- Widths: `1440, 1280, 1024, 900, 768, 600, 390` (or per-intent override)
- At least desktop + mobile profile
- Interaction profile per intent (`none`, `scroll_x`, `drag_x`, `click_controls`, `resize_stepdown`)

### 5. Audit each page individually (rubric pass)

For each page in `pages.json`:
1. Open desktop screenshot.
2. Open mobile screenshot.
3. Open Stage 4 intent violations for that page.
4. Apply every rubric section in `references/visual-rubric.md`.
5. Record all defects in the schema from `references/report-schema.md`.
6. Mark page `PASS` only when zero defects remain.

Do not skip pages, even if templates look similar.

### 6. Produce final report

Deliver:
- Executive summary (counts by severity and category)
- Page-by-page findings in strict schema
- Intent conformance summary (pass/fail/skipped by intent type)
- Prioritized fix plan (critical/high first)
- Visual regression watchlist for recurring patterns

### 7. Homepage visual regression snapshots

Capture fixed homepage breakpoints (`1440, 1024, 768, 600, 390`) for baseline or PR comparison:

```bash
python skills/webpage-visual-perfection-audit/scripts/capture_homepage_snapshots.py \
  --base-url "http://localhost:8000" \
  --route "/" \
  --output-dir "artifacts/visual-audit/homepage-snapshots" \
  --baseline-dir "skills/webpage-visual-perfection-audit/snapshots/homepage" \
  --compare \
  --max-diff-ratio 0.03
```

Notes:
- Baseline files are stored at `skills/webpage-visual-perfection-audit/snapshots/homepage/home-w<width>.png`.
- Keep snapshot comparison non-blocking by default; rely on Stage 4 strict gate for blocking regressions.

## Stage 3 Acceptance Criteria

1. Every crawled page with `crawl_status=ok` has at least two intents.
2. Every intent has at least one source evidence entry with `file` and `line`.
3. All intent records validate against the required schema fields.
4. Intent IDs are stable across reruns for the same route/component/type.
5. Home route includes explicit intents for carousel behavior, overlap prevention, card size balance, breakpoint stacking, and CTA uniqueness.

## Stage 4 Acceptance Criteria

1. All high-confidence intents (`confidence >= 0.90`) are evaluated across declared breakpoints.
2. Every failed intent contains measured metrics and a screenshot path.
3. High-confidence `High|Critical` failures force page status `FAIL`.
4. Final report cannot mark a page `PASS` with unresolved Stage 4 high-confidence `High|Critical` failures.
5. Seeded regression pack (carousel break, overlap, duplicate CTA, oversized cards, bad stacking) is detected by Stage 4 checks.

## Report Quality Bar

Fail the audit if any of these are missing:
- Evidence link to exact screenshot path for each issue
- Clear reason why current rendering is not visually perfect
- Concrete fix guidance (CSS/layout/content/state level)
- Acceptance criteria that is testable after fix

## Skill Resources

- `scripts/create_storage_state.py`: perform login and save authenticated Playwright storage state.
- `scripts/crawl_and_capture.py`: discover routes and capture screenshots for desktop/mobile.
- `scripts/extract_visual_intents.py`: Stage 3 code-aware intent extraction.
- `scripts/validate_visual_intents.py`: Stage 4 intent-vs-render conformance validation.
- `scripts/capture_homepage_snapshots.py`: fixed-breakpoint homepage snapshot capture + optional baseline comparison.
- `references/visual-rubric.md`: exhaustive visual QA checklist and severity rules.
- `references/report-schema.md`: strict page-by-page reporting contract.
