# Override Targets

Use this map when converting the immutable Lovable app into a real Django-backed frontend.

## Primary targets

### `lovable/src/contexts/AuthContext.tsx`

Problem:

- fake login/signup
- in-memory user state
- no Django session truth

Replacement responsibility:

- same external context/provider API
- same user-facing semantics where possible
- all auth reads/writes go through same-origin Django endpoints
- refresh should restore authenticated state from Django session bootstrap, not client memory

### `lovable/src/contexts/DraftContext.tsx`

Problem:

- drafts live in `localStorage`
- publish state is local-only

Replacement responsibility:

- preserve the context API Lovable components expect
- use Django-backed draft rows or equivalent persisted backend storage
- keep an in-memory cache only as a view cache, never as the system of record

### `lovable/src/data/mockData.ts`

Problem:

- trips, blogs, profiles, applications, and related lists are mocked

Replacement responsibility:

- preserve export names required by Lovable imports
- hydrate from server bootstrap JSON or same-origin fetches
- remove mock/demo fallback behavior on production routes

## Secondary targets

### Inline page-local mock literals

Problem:

- some Lovable pages may define `mock*` arrays or objects directly in the page/component file instead of importing them from `mockData.ts`

Replacement responsibility:

- inspect page-local mock literals surfaced by the blocker audit
- replace them through external overrides, live fetches, or bootstrap-backed data
- do not assume fixing `mockData.ts` alone removes all mock catalogs

Current example to watch:

- [lovable/src/pages/Blogs.tsx](e:/tapne/lovable/src/pages/Blogs.tsx)

### `lovable/src/components/BookingModal.tsx`

Problem:

- visual success flow without real persistence

Replacement responsibility:

- replace fake submission logic with same-origin Django mutations
- visible success state must correspond to real backend persistence

### `lovable/src/components/ApplicationModal.tsx`

Problem:

- fake application submission

Replacement responsibility:

- persist application data through Django
- return real status and identifiers

### `lovable/src/components/ApplicationManager.tsx`

Problem:

- mock application rows and component-local status changes

Replacement responsibility:

- list real application data
- approve/reject through Django-backed mutations
- reflect persisted state after refresh

## Route shell target

### `lovable/src/App.tsx`

This is not always a required override, but inspect it when:

- route ownership needs to be changed
- SPA fallback behavior needs stronger control
- route-level data bootstrap needs to happen before component render

If source-level route override is not needed, keep route ownership in Django and inject runtime shell/bootstrap around the existing app.

## Usage rule

Do not override more than needed.

Start with the smallest set of modules that removes:

- fake auth
- fake data
- local-only persistence
- fake mutations

Then verify the final artifact no longer contains the banned patterns for those surfaces.
