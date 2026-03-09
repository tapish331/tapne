# Visual QA Rubric (Rendered Pages Only)

Use this rubric only on real browser renders and screenshots. Do not infer visual quality from source code.

## Review Method

1. Inspect desktop screenshot at 100% zoom.
2. Inspect desktop screenshot at 200% zoom for subtle misalignment and clipping.
3. Inspect mobile screenshot at 100% zoom.
4. Inspect mobile screenshot at 200% zoom for tap-target and truncation issues.
5. Validate every category below before marking a page complete.
6. Record all defects, including low-severity polish issues.

## Severity Rules

- `Critical`: Prevents task completion, breaks core navigation, unreadable key content, or severe overlap/clipping in critical flows.
- `High`: Major visual break that harms trust, readability, or conversion but does not fully block use.
- `Medium`: Noticeable inconsistency or defect that degrades quality and should be fixed in normal sprint scope.
- `Low`: Minor polish issue visible to users; fix for production-grade finish.

Escalate severity by one level when the same issue appears repeatedly across templates or key journeys.

## Category Checklist

### 1) Layout and Geometry

- Check container widths against intended grid.
- Check left and right edge alignment across stacked sections.
- Check unexpected horizontal scrollbars.
- Check element overlap in headers, cards, sticky bars, and modals.
- Check clipped content at section boundaries.
- Check broken aspect ratios in cards and media blocks.
- Check that decorative layers do not occlude interactive content.

### 2) Spacing and Rhythm

- Check vertical rhythm consistency between sections.
- Check internal spacing consistency in reusable components.
- Check balanced whitespace around headings, buttons, and input controls.
- Check for crowded text or oversized empty gaps.
- Check bottom spacing before footers and sticky elements.

### 3) Typography

- Check font family consistency by role (heading, body, caption, button).
- Check text size hierarchy and heading progression.
- Check line-height readability for body paragraphs.
- Check letter spacing in uppercase labels and buttons.
- Check truncation, unintended wrapping, and orphan words.
- Check baseline alignment for icon-plus-text rows.
- Check legibility on dense backgrounds and gradients.

### 4) Color, Contrast, and Surfaces

- Check text contrast against its immediate background.
- Check disabled states are visibly distinct but still readable.
- Check link color is distinguishable from body text.
- Check border contrast for input fields and cards.
- Check tonal consistency of neutral backgrounds and separators.
- Check hover or active states do not reduce legibility.
- Check gradients and overlays avoid muddy color collisions.

### 5) Components and States

- Check buttons for shape, padding, radius, and text centering consistency.
- Check button label truncation at narrow widths.
- Check inputs for focus ring visibility and border consistency.
- Check dropdowns, toggles, and tabs for active-state clarity.
- Check badges, pills, and chips for padding and vertical centering.
- Check loaders, skeletons, and placeholders for alignment.
- Check modals and drawers for correct backdrop and edge spacing.

### 6) Forms and Validation UI

- Check label-to-input spacing and alignment.
- Check helper text placement and color hierarchy.
- Check error message readability and placement.
- Check success and warning states for visual consistency.
- Check checkbox and radio alignment with labels.
- Check tap/click targets for small controls on mobile.

### 7) Images, Video, and Icons

- Check image crop quality and focal point preservation.
- Check inconsistent corner radius between image containers and masks.
- Check blurry thumbnails due to wrong scaling.
- Check icon stroke weight and visual balance across sets.
- Check icon alignment within buttons and list rows.
- Check fallback states for missing media.

### 8) Responsive Behavior

- Check nav behavior transition desktop to mobile.
- Check section reflow quality at narrow widths.
- Check card stacking and spacing in 2-col to 1-col transitions.
- Check sticky header/footer collisions with content.
- Check floating action buttons do not cover key UI.
- Check long strings and localization expansions.

### 9) Motion and Transition Polish

- Check transition timing consistency between similar actions.
- Check janky shifts during late content load.
- Check motion paths do not cause disorientation.
- Check skeleton-to-content transitions avoid layout jumps.
- Check hover and press feedback appears intentional.

### 10) Navigation and Information Hierarchy

- Check top-level nav emphasis aligns with current page.
- Check breadcrumb spacing and separator alignment.
- Check active links are visually unambiguous.
- Check footer hierarchy and spacing.
- Check CTA prominence relative to surrounding content.

### 11) Empty, Loading, and Error States

- Check empty states are centered and balanced.
- Check loading states preserve final layout geometry.
- Check retry/error blocks are readable and prominent.
- Check state transitions avoid sudden reflow.

### 12) Micro-Polish and Production Finish

- Check 1px border inconsistencies and anti-aliasing artifacts.
- Check corner radius mismatch across neighboring elements.
- Check shadow direction and intensity consistency.
- Check separators align perfectly with content columns.
- Check redundant or accidental decorative elements.
- Check cursor and affordance consistency for interactive UI.

## Defect Logging Rules

1. Log one issue per distinct visual problem pattern.
2. If the same issue appears in multiple places, list all affected pages/components.
3. Add precise evidence by viewport and screenshot path.
4. Explain why it is visually imperfect, not only what is wrong.
5. Provide concrete fix guidance and objective acceptance criteria.

## Page Completion Gate

Mark page complete only when all checks below are true:

- Every category was reviewed for desktop and mobile.
- Every discovered defect was logged with severity.
- At least one screenshot path is linked per defect.
- A fix and acceptance criteria are present per defect.
- Page status is `PASS` only when defect count is zero.
