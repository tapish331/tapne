# Visual Audit Report Schema

Use this schema for the final output so every page is auditable and comparable.

## Required Top-Level Sections

1. `Audit Scope`
2. `Severity Summary`
3. `Category Summary`
4. `Page-by-Page Findings`
5. `Priority Fix Plan`
6. `Regression Watchlist`

## Audit Scope

Required fields:

- `base_url`
- `run_timestamp_utc`
- `page_count`
- `viewports_reviewed`
- `authenticated_scope` (`yes` or `no`)
- `include_patterns`
- `exclude_patterns`

## Severity Summary

Required fields:

- `critical_count`
- `high_count`
- `medium_count`
- `low_count`
- `pages_with_critical`

## Category Summary

Provide one line per category:

- `category_name`
- `issue_count`
- `affected_pages`
- `most_common_pattern`

## Page-by-Page Findings

Create one block per page in crawl order.

### Page Header

Required fields:

- `page_index`
- `url`
- `title`
- `crawl_status`
- `desktop_screenshot_path` (or `MISSING`)
- `mobile_screenshot_path` (or `MISSING`)
- `page_status` (`PASS` or `FAIL`)
- `defect_count`

### Defect Item Schema

For each defect, include all fields:

- `issue_id`: stable ID like `P003-ISSUE-02`
- `severity`: `Critical|High|Medium|Low`
- `category`: `Layout|Spacing|Typography|Color|Component|Media|Responsive|Motion|Polish`
- `viewport`: `desktop|mobile|both`
- `location`: concise location hint (section/component)
- `evidence`: screenshot path plus precise area description
- `current_behavior`: what is visually happening
- `expected_quality_bar`: what a polished result should look like
- `impact`: user-facing impact
- `recommended_fix`: concrete implementation direction
- `acceptance_criteria`: objective post-fix check

## Priority Fix Plan

Sort by priority:

1. Critical issues
2. High issues
3. Medium issues
4. Low issues

Each plan item must contain:

- `issue_id`
- `owner_suggestion` (role/team, if inferable)
- `estimated_effort` (`S|M|L`)
- `risk_if_unfixed`

## Regression Watchlist

List recurring patterns that require guardrails:

- `pattern_name`
- `affected_templates_or_routes`
- `suggested_prevention` (lint rule, design token, visual regression test, component refactor)

## Output Discipline

1. Do not collapse multiple pages into one combined finding block.
2. Do not omit low-severity issues if visible.
3. Do not mark `PASS` if any defect exists.
4. Do not use vague fix guidance such as "improve spacing."
5. Do include precise evidence and actionable next steps for every issue.
