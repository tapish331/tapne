# RULES_LOVABLE.md — Tapne mandatory Lovable session rules

This file is the canonical rules-of-engagement for Lovable work on Tapne
(tapnetravel.com). It is meant to be attached when Lovable is asked to change
frontend behavior. These rules supersede earlier prompt context and generic
assumptions unless the user explicitly overrides a specific rule in-session.

If any instruction in a prompt conflicts with what is written here, obey this
file and say so in the response. Do not silently drift.

This file contains rules, not problem inventories. The canonical route map is a
rule. Any list of current illegal routes, stale links, or exact route renames
belongs in the task prompt, not in this file.

---

## Section 1 — Pre-flight (mandatory before any action)

Before changing anything, first restate the task in browser-visible terms and
identify the specific screens, routes, and user actions involved.

- Start from the canonical route map in Section 4, not from legacy links that
  may still appear in the prompt.
- If the requested behavior already belongs to an existing canonical page,
  update that page instead of inventing a new route or duplicate flow.
- If the prompt mentions backend files, deployment, runtime plumbing, or
  environment details, ignore those implementation details and translate the
  ask into rendered browser behavior only.

If the task is route cleanup, use the canonical route map in Section 4 and the
task prompt's problem statement to decide what must change.

---

## Section 2 — Lovable scope boundary

Lovable owns the rendered frontend only. It should work on what users see and
click in the browser.

### Lovable may own

- Page layout, copy, hierarchy, and visual presentation
- Client-side navigation and route-to-page wiring
- CTA targets, back buttons, redirects, empty states, and success states
- Modal flows, client-side auth gating, and on-page interaction behavior
- Reusing existing pages for the correct user intent

### Lovable may NOT own

- Backend implementation details
- Deployment, infrastructure, or environment setup
- New server concepts or new data contracts invented from scratch
- Standalone login, signup, or unauthorized pages
- Duplicate browse hubs or route aliases outside the canonical map
- Placeholder or under-construction routes on production page flows

If a prompt mixes frontend goals with non-frontend implementation detail,
Lovable should solve the visible frontend goal and ignore the cross-scope
implementation noise.

---

## Section 2b — Prompt interpretation contract

When working from a user prompt:

- Prefer fixing the existing page flow over inventing a new one.
- Prefer renaming a retired route to an existing canonical route over adding a
  new page.
- Prefer updating all affected visible navigation surfaces in one pass.
- Describe intended changes in terms of what the user clicks, what opens now,
  and what should open instead.
- Preserve the current product structure unless the user explicitly asks for a
  redesign.
- Do not reintroduce retired paths after removing them.

If one task mentions multiple visible route problems, solve them as one
coherent navigation cleanup rather than as isolated one-off edits.

---

## Section 3 — Frontend product ownership

The SPA owns what the user sees.

### Core product truths

- Guests can browse public surfaces, but protected actions should open the
  shared auth modal.
- Members can create, manage, message, bookmark, review, and edit from the
  existing canonical surfaces.
- Search is the browsing hub for trips, stories, and users.
- The dashboard is the management hub for member-owned surfaces.
- Public profile viewing and profile editing are separate destinations.

### Retired patterns (do not reintroduce)

- Standalone `/login` page
- Standalone `/signup` page
- Standalone `/unauthorized` page
- A trips-only browse hub separate from the canonical search flow
- A stories-only browse hub separate from the canonical search flow
- A self-profile page separate from public profile + profile edit
- Duplicate management hubs outside the dashboard

### Invariants

- Protected actions open the shared auth modal.
- Existing canonical pages should absorb overlapping legacy flows.
- Navigation should not send the same user intent to multiple standalone
  destinations.

---

## Section 4 — Planned page audit

Two standing cleanup rules apply to all Lovable route work:

1. Use only the canonical route map below.
2. Remove visible navigation drift away from the canonical route map.

### Canonical route map (authoritative — no other SPA routes are permitted)

| Route | Visibility | Description |
|---|---|---|
| `/` | public | Homepage |
| `/search` | public | Global search (trips, stories, users) |
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
- Join and review actions are attached to trip detail, not separate standalone pages.

### Source of truth

- **Canonical routes** are the table above. That list is exhaustive — no route
  outside it is valid.
- **Task-specific invalid routes** belong in the task prompt, not in this file.
- **Allowed replacements** must come from the canonical route map above.

### Drift rules

- A route outside the canonical route map is invalid unless the user explicitly
  changes the rules.
- If the task prompt identifies a non-canonical route that overlaps with an
  existing canonical page, rename the visible flow to that canonical page
  rather than inventing a new destination.
- If the same user intent appears under two standalone routes, keep the
  canonical route and remove the duplicate path from visible navigation.
- If a CTA, shortcut, empty state, or success redirect lands on a
  non-canonical destination, rename it to the correct canonical destination
  rather than inventing a new intermediate flow.
- No route outside the canonical route map should be introduced unless the
  user explicitly changes the rules.

---

## Section 5 — Operating rules

### Navigation consistency

When route cleanup touches one navigation surface, update every equivalent
visible surface in the same session:

- Desktop navbar
- Mobile navbar
- Footer
- Hero CTAs
- Section CTAs
- Dropdown shortcuts
- Empty states
- Cancel buttons
- Back buttons
- Save redirects
- Delete-success redirects
- Success toasts with follow-up navigation

The same user intent should land on the same canonical destination across all
of these surfaces.

### Auth and access

- Protected actions should open the shared auth modal, not a standalone auth page.
- Guest attempts to perform member-only actions should stay in-context and open auth.
- Preview remains on the create/edit route with `?mode=preview`.

### Page-role invariants

- `/search` is the browse and discovery surface.
- `/users/:profileId` is the public profile surface.
- `/profile/edit` is the edit-profile surface.
- `/messages` is the inbox and chat surface.
- `/dashboard/*` is the management hub for member-owned surfaces.
- `/404` is the explicit not-found page.

### Change discipline

- Keep existing layouts and components where possible.
- Do not redesign unrelated pages during route cleanup.
- Do not add dead-end placeholders to production paths.
- Do not introduce a second page for a job that an existing canonical page
  already performs.

---

## Section 6 — Quality gate

A Lovable task is not done until all of the following are true:

1. Every non-canonical route named in the task has been removed from visible
   in-app navigation.
2. Every renamed flow now lands on a canonical destination.
3. Equivalent actions land on the same destination across desktop, mobile,
   footer, dropdown, CTA, and redirect variants.
4. Protected flows still open the shared auth modal correctly.
5. Unrelated canonical routes remain intact.
6. No extra standalone routes were introduced outside the canonical map.

If a task changed navigation, the response must explicitly name:

- The task-specific non-canonical routes removed
- The canonical routes now used
- The visible surfaces updated together
- The behaviors intentionally preserved

---

## Section 7 — Response contract

At the end of the task, report:

1. What changed in browser-visible terms
2. Which task-specific routes were renamed to canonical routes
3. Which screens or navigation surfaces were updated
4. What was intentionally left unchanged to avoid regression
5. Explicit confirmation that no extra standalone routes were added

If no route cleanup was needed, say so directly instead of implying hidden
changes.
