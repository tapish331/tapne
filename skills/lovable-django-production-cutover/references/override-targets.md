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

**Required override** for this repo. Lives at `frontend_spa/src/App.tsx`.

**Before writing or modifying this file, read `lovable/src/App.tsx` in full.**

The replacement `App.tsx` has two responsibilities:

1. Swap the `*` catch-all from `NotFound` to `UnderConstructionPage`.
2. Preserve everything else from `lovable/src/App.tsx` without deviation.

**Critical rules — each one caused a production regression when violated:**

**Pages must come from `@/pages/*` (Lovable source), not `@frontend/pages/*`:**

```tsx
// CORRECT — imports the real Lovable page with full UI
import Index from "@/pages/Index";
import TripDetail from "@/pages/TripDetail";
// ... all other pages from @/pages/*

// CORRECT — the only @frontend import for a page
import UnderConstructionPage from "@frontend/pages/UnderConstructionPage";

// WRONG — importing a custom stripped-down replacement instead of the Lovable page
// import HomePage from "@frontend/pages/HomePage";   // ← strips out carousels, fonts, tabs
// import TripDetailPage from "@frontend/pages/TripDetailPage"; // ← strips out tabs, full UI
```

**Provider tree must match `lovable/src/App.tsx` exactly:**

```tsx
// Current providers in lovable/src/App.tsx (verify on every update):
<QueryClientProvider client={queryClient}>
  <AuthProvider>
    <DraftProvider>
      <TooltipProvider>
        <Toaster />       {/* @/components/ui/toaster */}
        <Sonner />        {/* @/components/ui/sonner */}
        <RouterProvider router={router} />
      </TooltipProvider>
    </DraftProvider>
  </AuthProvider>
</QueryClientProvider>
```

Dropping any provider causes silent failures: missing `QueryClientProvider` → all `useQuery` calls crash; missing `DraftProvider` → CreateTrip/MyTrips crash; missing `TooltipProvider` → tooltip components crash.

**Route list must match `lovable/src/App.tsx` exactly:**

```tsx
const router = createBrowserRouter([
  { path: "/",            element: <Index /> },
  { path: "/trips",       element: <BrowseTrips /> },
  { path: "/trips/:id",   element: <TripDetail /> },
  { path: "/create-trip", element: <CreateTrip /> },
  { path: "/my-trips",    element: <MyTrips /> },
  { path: "/blogs",       element: <Blogs /> },
  { path: "/login",       element: <Login /> },
  { path: "/signup",      element: <SignUp /> },
  { path: "/profile",     element: <Profile /> },
  { path: "*",            element: <UnderConstructionPage /> },  // ← only change
]);
```

The `UnderConstructionPage` component must:
- Use `FrontendNavbar` (from `@frontend/components/FrontendNavbar`) and `Footer` (from `@/components/Footer`).
- Use only Tailwind tokens from the Lovable build: `bg-background`, `text-foreground`, `text-primary`, `text-muted-foreground`.
- Show an "Under Construction" heading, a short message, and a "Go Home" button linking to `/`.
- Render identically for signed-in and signed-out users — no auth dependency.

### `static/frontend-brand/tokens.css` (not a Lovable override, but a required cutover artifact)

This file must contain CSS variable declarations that are byte-for-byte equivalent to `lovable/src/index.css` `:root` and `.dark` blocks. It must not introduce any new variable or change any value. Its only purpose is to make the same variables controllable from outside `lovable/` for future changes.

Structure:
```css
/* Auto-generated from lovable/src/index.css — do not deviate from source values */
:root {
  /* paste :root block verbatim from lovable/src/index.css */
}
.dark {
  /* paste .dark block verbatim from lovable/src/index.css */
}
body {
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
}
```

### `static/frontend-brand/overrides.css` (not a Lovable override, but a required cutover artifact)

This file must be present but empty by default. Only populate it when a deliberate visual change is explicitly requested. Never populate it as part of the standard cutover workflow.

## Django route cutover targets (not Lovable source overrides, but required cutover work)

These are Django view changes needed to stop Django templates from being served for browser-navigable URLs.

### `frontend/urls.py` — explicit SPA shell patterns (critical)

**This is the primary mechanism for intercepting Django HTML routes.** The global catch-all in `tapne/urls.py` is a safety net only — it cannot intercept routes that are already matched by app-specific `urls.py` files included before it.

The `frontend` app is included at the top of `tapne/urls.py` (`path("", include("frontend.urls"))`), which means `frontend/urls.py` patterns are matched first. Every Django HTML route must have an explicit pattern here pointing to `frontend_entrypoint_view`.

**Required patterns when `LOVABLE_FRONTEND_ENABLED=True`:**

```python
if settings.LOVABLE_FRONTEND_ENABLED:
    urlpatterns.extend([
        # Root
        path("", views.frontend_entrypoint_view),

        # Trips — all template-rendering paths including parameterised ones
        path("trips", views.frontend_entrypoint_view),
        path("trips/", views.frontend_entrypoint_view),
        path("trips/create/", views.frontend_entrypoint_view),
        path("trips/mine/", views.frontend_entrypoint_view),
        re_path(r"^trips/(?P<trip_id>\d+)/?$", views.frontend_entrypoint_view),
        re_path(r"^trips/(?P<trip_id>\d+)/edit/?$", views.frontend_entrypoint_view),
        re_path(r"^trips/(?P<trip_id>\d+)/delete/?$", views.frontend_entrypoint_view),

        # Blogs
        path("blogs", views.frontend_entrypoint_view),
        path("blogs/", views.frontend_entrypoint_view),
        path("blogs/create/", views.frontend_entrypoint_view),
        re_path(r"^blogs/(?P<slug>(?!create$)[-a-zA-Z0-9_]+)/?$", views.frontend_entrypoint_view),
        re_path(r"^blogs/(?P<slug>[-a-zA-Z0-9_]+)/edit/?$", views.frontend_entrypoint_view),

        # Accounts — must come before accounts/urls.py is matched
        path("accounts/login/", views.frontend_entrypoint_view),
        path("accounts/signup/", views.frontend_entrypoint_view),
        path("accounts/me/", views.frontend_entrypoint_view),
        path("accounts/me/edit/", views.frontend_entrypoint_view),

        # SPA auth routes
        path("login", views.frontend_entrypoint_view),
        path("login/", views.frontend_entrypoint_view),
        path("signup", views.frontend_entrypoint_view),
        path("signup/", views.frontend_entrypoint_view),
        path("profile", views.frontend_entrypoint_view),
        path("profile/", views.frontend_entrypoint_view),
        path("create-trip", views.frontend_entrypoint_view),
        path("create-trip/", views.frontend_entrypoint_view),
        path("my-trips", views.frontend_entrypoint_view),
        path("my-trips/", views.frontend_entrypoint_view),

        # Other Django HTML pages → SPA (Under Construction)
        path("search/", views.frontend_entrypoint_view),
        path("activity/", views.frontend_entrypoint_view),
        path("settings/", views.frontend_entrypoint_view),
        path("settings/appearance/", views.frontend_entrypoint_view),
        path("social/bookmarks/", views.frontend_entrypoint_view),
        path("interactions/dm/", views.frontend_entrypoint_view),
        re_path(r"^interactions/dm/(?P<thread_id>\d+)/?$", views.frontend_entrypoint_view),
        path("enroll/hosting/inbox/", views.frontend_entrypoint_view),
        re_path(r"^u/(?P<username>[^/]+)/?$", views.frontend_entrypoint_view),
    ])
```

**Verification command** — run after every edit to `frontend/urls.py`:

```bash
python -c "
import os; os.environ['DJANGO_SETTINGS_MODULE']='tapne.settings'
os.environ['LOVABLE_FRONTEND_ENABLED']='true'
os.environ['TAPNE_ENABLE_DEMO_DATA']='false'
import django; django.setup()
from django.urls import resolve
must_be_spa = [
    '/trips/42/edit/', '/trips/create/', '/trips/mine/',
    '/accounts/login/', '/accounts/me/', '/blogs/my-post/',
    '/settings/', '/u/someuser/', '/interactions/dm/5/',
]
for url in must_be_spa:
    fn = resolve(url).func.__name__
    ok = fn == 'frontend_entrypoint_view'
    print('[OK]' if ok else '[FAIL]', url, '->', fn)
"
```

### Pattern B — global catch-all in `tapne/urls.py` (safety net only)

Add at the very bottom of `tapne/urls.py`, after all other includes:

```python
if settings.LOVABLE_FRONTEND_ENABLED:
    from frontend.views import frontend_entrypoint_view
    urlpatterns += [re_path(r"^.*$", frontend_entrypoint_view, name="spa-catchall")]
```

This catches any URL that slipped past explicit patterns. It is **not** a substitute for the explicit patterns in `frontend/urls.py`. Both are required.

## Usage rule

Do not override more than needed.

Start with the smallest set of modules that removes:

- fake auth
- fake data
- local-only persistence
- fake mutations
- Django template rendering for browser-navigable URLs

Then verify the final artifact no longer contains the banned patterns for those surfaces, and that no Django template is still being served to a browser user.
