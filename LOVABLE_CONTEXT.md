# Tapne — Lovable Development Context

Attach this file to every Lovable prompt. It gives Lovable the full architecture picture so it never accidentally breaks production.

---

## What Tapne Is

A travel platform where hosts create group trips and travelers join them. Django backend on Cloud Run. Lovable frontend deployed as a static SPA shell served through Django. The live domain is `tapnetravel.com`.

---

## The Dual-Mode System — Read This First

The codebase runs in **two modes without any code changes**:

| Signal | Mode | What happens |
|---|---|---|
| `window.TAPNE_RUNTIME_CONFIG` is **absent** at page load | **Lovable dev** | `src/lib/mode.ts` injects a mock config; `IS_DEV_MODE = true`; all API calls go to `devMock.ts` in-memory |
| `window.TAPNE_RUNTIME_CONFIG` is **present** (Django injects it) | **Production** | `IS_DEV_MODE = false`; all API calls hit real Django endpoints |

This means: **the app works fully in the Lovable editor without a backend**, and automatically switches to real data when deployed. Do not break this.

---

## Four Sacred Files — Never Overwrite or Restructure

These files implement the dual-mode system. If Lovable ever replaces them, the production site will show mock data to real users.

| File | Role |
|---|---|
| `src/main.tsx` | **First import must be `import "@/lib/mode"`** — before React, before App |
| `src/lib/mode.ts` | Detects `window.TAPNE_RUNTIME_CONFIG`; sets `IS_DEV_MODE`; injects dev config |
| `src/lib/devMock.ts` | In-memory API resolver for Lovable dev mode |
| `src/lib/api.ts` | All four API functions (`apiGet/apiPost/apiPatch/apiDelete`) with `IS_DEV_MODE` short-circuit |

Current exact content of `src/main.tsx`:
```tsx
import "@/lib/mode";
import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";

createRoot(document.getElementById("root")!).render(<App />);
```

If you need to touch `main.tsx`, keep `import "@/lib/mode"` as the **very first line**.

---

## API Layer — The Only Way to Fetch Data

All data access must go through **`src/lib/api.ts`**. Never use `fetch()` directly in pages or components.

```typescript
import { apiGet, apiPost, apiPatch, apiDelete } from "@/lib/api";

// GET
const data = await apiGet<MyType>(cfg.api.trips);

// POST / PATCH / DELETE
await apiPost(cfg.api.login, { email, password });
await apiPatch(cfg.api.profile_me, { display_name: "..." });
await apiDelete(`${cfg.api.trip_drafts}${id}/`);
```

The config object is always `window.TAPNE_RUNTIME_CONFIG`. Access it as:
```typescript
const cfg = window.TAPNE_RUNTIME_CONFIG;
```

### Available API endpoints (from `cfg.api.*`)

| Key | Purpose |
|---|---|
| `cfg.api.session` | GET — verify/refresh Django session |
| `cfg.api.login` | POST `{ email, password }` → `{ user: SessionUser }` |
| `cfg.api.signup` | POST `{ first_name, email, password }` → `{ user: SessionUser }` |
| `cfg.api.logout` | POST `{}` |
| `cfg.api.home` | GET → `HomeResponse` (trips, blogs, profiles) |
| `cfg.api.trips` | GET → `TripListResponse`; GET `+ id + "/"` → `TripDetailResponse` |
| `cfg.api.blogs` | GET → `{ blogs: BlogData[] }` |
| `cfg.api.my_trips` | GET → `MyTripsResponse` |
| `cfg.api.trip_drafts` | POST create; PATCH/DELETE `+ id + "/"`; POST `+ id + "/publish/"` |
| `cfg.api.profile_me` | GET/PATCH own profile |
| `cfg.api.hosting_inbox` | GET → `HostingInboxResponse` |
| `cfg.api.bookmarks` | GET bookmarks |
| `cfg.api.activity` | GET activity feed |
| `cfg.api.settings` | GET/PATCH account settings |
| `cfg.api.dm_inbox` | GET DM thread list |

---

## Auth — Use the Hook

Auth state lives in `AuthContext`. Never manage user state manually.

```typescript
import { useAuth } from "@/contexts/AuthContext";

const { user, isAuthenticated, login, signup, logout, updateProfile } = useAuth();
```

- `user` shape: `{ id, username, name, email, bio, location, website, avatar? }`
- `login(email, password)` → `Promise<boolean>`
- `signup(name, email, password)` → `Promise<boolean>`
- `updateProfile(Partial<User>)` — patches Django and updates local state

`AuthContext` already handles session hydration on mount and seeds from `cfg.session` synchronously to avoid flash. Do not re-implement any of this.

---

## Drafts — Use the Hook

Trip drafts live in `DraftContext`. Never use localStorage.

```typescript
import { useDrafts } from "@/contexts/DraftContext";

const { drafts, createDraft, updateDraft, deleteDraft, duplicateDraft, getDraft, publishDraft, loading } = useDrafts();
```

- `createDraft()` → `Promise<number>` (returns new draft id)
- `updateDraft(id, Partial<TripDraft>)` — optimistic update + PATCH to Django
- `deleteDraft(id)` — DELETE from Django
- `duplicateDraft(id)` → `Promise<number>`
- `publishDraft(id)` → `Promise<void>`

`TripDraft` shape: `{ id, title, destination, category, summary, startDate, endDate, status ("draft"|"published"), formData: { totalPrice, totalSeats, highlights, itinerary, includedItems, ... } }`

---

## Design System

All styling must use **Tailwind utility classes already in scope**. Do not add custom CSS, inline styles, or new class names.

CSS variables (set by `src/index.css` and injected by Django):

| Token | Use for |
|---|---|
| `bg-background` / `text-foreground` | Page background and primary text |
| `bg-card` / `text-card-foreground` | Card surfaces |
| `text-primary` / `bg-primary` | Brand teal (`hsl(174 55% 42%)`) |
| `text-muted-foreground` | Secondary/caption text |
| `border-border` | All borders |
| `bg-accent` / `text-accent-foreground` | Subtle highlights |
| `text-destructive` | Error/destructive actions |

Font: `Inter` via `font-sans`. Border radius base: `0.625rem` (`rounded-lg`).

Use `container`, `py-*`, `px-*`, `gap-*`, `rounded-lg`, `font-sans` — all safe.

---

## Current Pages and Routes

| Route | Component | Data source |
|---|---|---|
| `/` | `pages/Index.tsx` | `GET cfg.api.home` |
| `/trips` | `pages/BrowseTrips.tsx` | `GET cfg.api.trips` |
| `/trips/:id` | `pages/TripDetail.tsx` | `GET cfg.api.trips + "/" + id + "/"` |
| `/create-trip` | `pages/CreateTrip.tsx` | `useDrafts()` |
| `/my-trips` | `pages/MyTrips.tsx` | `useDrafts()` + `GET cfg.api.my_trips` |
| `/blogs` | `pages/Blogs.tsx` | `GET cfg.api.blogs` |
| `/login` | `pages/Login.tsx` | `useAuth().login()` |
| `/signup` | `pages/SignUp.tsx` | `useAuth().signup()` |
| `/profile` | `pages/Profile.tsx` | `useAuth().user` + `useAuth().updateProfile()` |
| `*` | `pages/NotFound.tsx` | (none) |

---

## TypeScript Types (from `src/types/api.ts`)

Key types — use these, do not invent parallel shapes:

```typescript
TapneRuntimeConfig   // window.TAPNE_RUNTIME_CONFIG shape
SessionUser          // { id, username, email, display_name, bio, location, website, profile_url, created_trips, joined_trips }
TripData             // Full trip shape (all fields optional except id, title)
TripListResponse     // { trips: TripData[] }
TripDetailResponse   // { trip, can_manage_trip, mode, similar_trips? }
MyTripsResponse      // { trips, active_tab, tab_counts }
HomeResponse         // { trips, blogs, profiles }
BlogData             // { slug, title, excerpt?, body?, author_username?, ... }
ProfileData          // { username, display_name, bio, location, website, created_trips, joined_trips }
EnrollmentRequestData // join request shape
HostingInboxResponse // { requests: EnrollmentRequestData[], counts }
```

---

## Extending devMock.ts for New Pages

When you add a new page that calls a new API endpoint, add the mock handler to `src/lib/devMock.ts` inside `resolveMockRequest`. Pattern:

```typescript
// inside resolveMockRequest(method, url, body):
if (method === "GET" && path === "/your-new-endpoint/") {
  return { yourData: [] };
}
```

Also add the new endpoint key to:
1. `TapneRuntimeConfig.api` in `src/types/api.ts`
2. `DEV_RUNTIME_CONFIG.api` in `src/lib/mode.ts` (with `/__devmock__/your-new-endpoint/` URL)

---

## Hard Rules — Never Violate These

1. **`import "@/lib/mode"` must be the first line of `src/main.tsx`.**
2. **Never import from `src/data/mockData.ts` in pages or components.** It is only used inside `devMock.ts`.
3. **Never use `localStorage` for app state.** Auth and drafts are in context backed by Django.
4. **Never use `users[0]` or hardcode a user.** `useAuth()` is the only source of user state.
5. **Never use `BrowserRouter` from react-router-dom in `src/App.tsx`.** The external production build overrides App.tsx with `createBrowserRouter`. Lovable's `App.tsx` may keep `BrowserRouter` for its own dev routing — do not change the router setup without being explicitly asked.
6. **Never call `fetch()` directly** — always use `apiGet/apiPost/apiPatch/apiDelete`.
7. **Never add a second `window.TAPNE_RUNTIME_CONFIG` assignment** anywhere except `src/lib/mode.ts`.
8. **Do not add CSS files or `<style>` blocks.** Use only Tailwind classes.
9. **Do not add `setTimeout`/`setInterval`-based fake loading delays** in pages. Use real loading states from API calls.

---

## When Builds Fail After a Lovable Update

If the production build breaks after pulling a Lovable update, check these files first (in order):

1. `src/main.tsx` — is `import "@/lib/mode"` still the first line?
2. `src/lib/mode.ts` — does `IS_DEV_MODE` still check `window.TAPNE_RUNTIME_CONFIG`?
3. `src/lib/api.ts` — do all four functions still have `if (IS_DEV_MODE) return resolveMockRequest(...)` as first line?
4. `src/lib/devMock.ts` — is `resolveMockRequest` still exported?

If any of these were overwritten, restore them from the last good git commit in the `lovable/` submodule.
