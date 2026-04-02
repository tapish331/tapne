---
name: lovable-django-visual-parity
description: Render matched pages from the repo's `lovable` app and Django app, compare screenshots at fixed breakpoints, and iteratively patch Django until it matches Lovable as closely as possible. Use when Codex must drive Lovable-to-Django UI parity, restyle Django-only screens in the Lovable design language, or create Django counterparts for Lovable-only pages and modals while keeping visual tokens centralized.
---

# Lovable Django Visual Parity

Treat the `lovable/` app as the visual source of truth and Django as the implementation that must converge toward it. Work from real browser renders, not source inspection alone, and keep shared colors, typography, spacing, radii, shadows, and interaction chrome centralized on the Django side.

## Use This Skill When

- The task is to make a Django page or modal match its Lovable counterpart.
- The task is to restyle a Django-only entity so it still feels native to the Lovable system.
- The task is to create a Django counterpart for a Lovable-only page or modal.
- The files in play include Django templates, `static/css/lovable-parity.css`, `static/js/tapne-ui.js`, `templates/base.html`, Django views/context processors, or `lovable/src/pages` and `lovable/src/components`.

## Non-Negotiable Rules

1. Compare rendered output from both apps before deciding what to change.
2. Modify Django, not Lovable, unless the user explicitly asks to change Lovable.
3. Centralize recurring visual decisions in Django first:
   - `static/css/lovable-parity.css`
   - `templates/base.html`
   - `static/js/tapne-ui.js`
4. Match the same route, viewport, theme, auth state, data shape, modal state, and scroll position before judging parity.
5. Fix layout and composition first, then spacing, then typography/color, then micro-details.
6. When a Django page has no Lovable counterpart, borrow the nearest Lovable archetype from `references/route-parity-map.md`.
7. When a Lovable page or modal has no Django counterpart, create it in Django before polishing it.

## Workflow

### 1. Start both apps

Django:

```powershell
.venv\Scripts\python manage.py runserver 127.0.0.1:8000
```

Lovable:

```powershell
Set-Location lovable
npm install
npm run dev -- --host 127.0.0.1 --port 4173
```

If dependencies for browser capture are missing:

```powershell
python -m pip install -r skills/webpage-visual-perfection-audit/requirements.txt
python -m playwright install chromium
```

### 2. Build the entity-pair plan

Read `references/route-parity-map.md`.

For each requested entity, classify it as one of:

- `shared`: both Lovable and Django exist
- `django-only`: Django exists, Lovable does not
- `lovable-only`: Lovable exists, Django does not

For `shared`, compare directly.

For `django-only`, pick the closest Lovable archetype and match its shell, rhythm, card language, CTA hierarchy, and typography.

For `lovable-only`, create the Django entity and make it visually match the Lovable source.

### 3. Capture real renders

For broad route sweeps, use the existing audit scripts against both apps.

Django example:

```powershell
python skills/webpage-visual-perfection-audit/scripts/crawl_and_capture.py `
  --base-url "http://127.0.0.1:8000" `
  --output-dir "artifacts/parity/django" `
  --max-pages 40 `
  --max-depth 3
```

Lovable example:

```powershell
python skills/webpage-visual-perfection-audit/scripts/crawl_and_capture.py `
  --base-url "http://127.0.0.1:4173" `
  --output-dir "artifacts/parity/lovable" `
  --max-pages 40 `
  --max-depth 3
```

For one page or modal, prefer a focused capture loop instead of a full crawl. If the state is interactive or modal-driven, use the browser directly and trigger the same UI state in both apps before taking screenshots.

### 4. Normalize the comparison state

Before judging differences, align:

- viewport width: default pack `1440, 1024, 768, 390`
- theme: same light/dark state
- auth: same signed-in or signed-out state
- seed data: same trip, blog, user, or mock content where possible
- modal visibility: same open step and same tab/accordion state
- scroll position: same section when comparing long detail pages

If the apps cannot show the exact same data, match structure and visual hierarchy first and note the content mismatch as a comparison constraint.

### 5. Patch Django in the right order

Use this order every time:

1. shared shell and design tokens
2. reusable component classes
3. page template structure
4. modal structure and JS state
5. Django view/context shaping if the wrong data causes false visual drift

Do not scatter the same color, radius, or spacing fix across many templates if it belongs in the centralized parity layer.

### 6. Re-render and iterate

After each substantial patch:

1. reload the Django page
2. re-capture the matching Lovable and Django renders
3. compare the largest remaining deltas
4. patch Django again

Keep iterating until only small residual differences remain.

### 7. Acceptance bar

Aim for parity in:

- page composition and section order
- spacing rhythm and container widths
- type scale, weight, and line length
- color, contrast, and surface hierarchy
- card shape, border radius, and shadow language
- CTA placement and emphasis
- icon size/density
- desktop and mobile breakpoint behavior
- modal sizing, layering, and step flow

Do not stop when the page is merely "close". Stop when the remaining differences are minor, deliberate, and hard to remove without changing the underlying product behavior.

## Repo-Specific Guidance

Use Lovable as the visual source, but keep Django parity control centralized here:

- `static/css/lovable-parity.css`: tokens, shells, cards, section wrappers, parity overrides
- `templates/base.html`: shared header/footer/search/modal chrome
- `static/js/tapne-ui.js`: shared interactive parity behavior

Common Django implementation files that often need parity work:

- `templates/pages/**/*.html`
- `templates/partials/modals/*.html`
- `accounts/views.py`
- `trips/views.py`
- `trips/context_processors.py`

Common Lovable source files that define the target look:

- `lovable/src/pages/*.tsx`
- `lovable/src/components/*.tsx`
- `lovable/src/App.tsx`

## Missing-Counterpart Policy

If Django has a page Lovable does not have:

- choose the nearest Lovable archetype from `references/route-parity-map.md`
- keep the Django page functional
- make it feel like a natural Lovable screen, not a generic fallback

If Lovable has a page or modal Django does not have:

- create the Django entity
- wire it into the existing Django shell and routing
- then iterate visually until it matches the Lovable source

## Reporting

When closing the work, report:

- which entity pairs were compared
- what was changed in Django
- what remains different, if anything
- what was verified in the browser

## Resources

- `references/route-parity-map.md`: repo-specific counterpart map and Lovable archetype selection guide
- `../webpage-visual-perfection-audit/SKILL.md`: screenshot capture and rendered QA workflow
- `../webpage-visual-perfection-audit/references/visual-rubric.md`: detailed visual quality rubric
