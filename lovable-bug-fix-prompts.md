# Lovable Bug Fix Prompts
Send each section below as a separate Lovable prompt, in order.

---

## Prompt 1 — Fix Save Draft + Publish (Bugs 1 & 2)

In `src/contexts/DraftContext.tsx` the initial draft load checks `cfg?.session?.authenticated` once at mount. This is the frozen bootstrap value — if the user logs in mid-session the check never re-runs, so their drafts never load. Also, the `publishDraft` function does not navigate after success nor handle errors, so the Publish button stays greyed-out forever.

Make these four changes:

**1. Replace the one-shot auth check with a dynamic subscription.**
Import `useAuth` from `@/contexts/AuthContext`. Read `const { isAuthenticated } = useAuth()` inside the component. Change the draft-loading `useEffect` dependency array from `[]` to `[isAuthenticated]` and replace `if (!cfg?.session?.authenticated)` with `if (!isAuthenticated)`. This makes the draft list refresh automatically when the user logs in.

**2. Guard `createDraft()` against unauthenticated calls.**
At the top of `createDraft`, before calling `apiPost`, check `const { isAuthenticated } = useAuth()` (or read it from a ref). If `!isAuthenticated`, return `0` immediately without throwing, so `CreateTrip.tsx` sees a falsy id and shows the auth prompt instead of an unhandled rejection.

**3. Fix `publishDraft` to await the save, then navigate.**
`DraftContext.publishDraft` should accept an optional `currentFormData` parameter that it PATCHes to the draft endpoint before firing the publish POST — this avoids the race condition where the last unsaved fields haven't reached the server yet. After the publish POST succeeds, navigate to `/my-trips` using `useNavigate` from `react-router-dom` and remove the just-published draft from local state.

**4. Surface publish errors.**
Wrap the `apiPost` in `publishDraft` in a try/catch. On error, throw a new `Error` with `err?.message || "Could not publish trip"` so that `CreateTrip.tsx` can catch it, clear the loading spinner, and show a `toast.error(...)` to the user.

Also fix the `MyTripsResponse` interface in `src/types/api.ts` — the `tab_counts` keys the server actually returns are `drafts`, `published`, and `past` (not `created`, `joined`, `past`):
```ts
tab_counts: { drafts: number; published: number; past: number };
```

---

## Prompt 2 — Fix Notification Clicks (Bug 3)

In `src/components/Navbar.tsx`, the notification `DropdownMenuItem` elements inside the notifications dropdown have no `onClick` handlers — clicking them does nothing.

Make these changes:

1. Import `useNavigate` from `react-router-dom` at the top of the file.
2. Call `const navigate = useNavigate()` inside the `Navbar` component.
3. For each notification `DropdownMenuItem`, add `onClick={() => navigate("/activity")}` so clicking any notification takes the user to the activity feed where they can see details.
4. At the bottom of the notifications dropdown (after the list of items), add a final `DropdownMenuItem` with text "View all activity" that also calls `navigate("/activity")` and is styled with a slightly muted appearance to distinguish it as a footer link.
5. If there are no notifications, the empty-state message should also render a "Go to activity" link with the same navigation.

---

## Prompt 3 — Fix Review Submission (Bug 4)

In `src/components/ReviewModal.tsx`, `handleSubmit` only shows a success toast and closes the modal — it never calls the backend.

The Django API endpoint is: `POST /frontend-api/trips/{tripId}/reviews/`
Request body: `{ rating: number, body: string, headline?: string }`
Response on success: `{ ok: true, outcome: "created" | "updated", review: { id, rating, headline, body, author, created_at } }`
Response on error: `{ ok: false, error: string }`

Make these changes:

**1. Add `trip_reviews` and `dm_start` to `src/types/api.ts`** — update the `TapneRuntimeConfig.api` interface:
```ts
api: {
  // ... existing keys ...
  trip_reviews: string;
  dm_start: string;
};
```

**2. Add the same keys to `src/lib/mode.ts`** `DEV_RUNTIME_CONFIG.api`:
```ts
trip_reviews: "/__devmock__/trips/",
dm_start: "/__devmock__/dm/start/",
```

**3. Update `ReviewModal`** — add a required `tripId: number` prop and an optional `onReviewSubmitted?: () => void` callback prop. In `handleSubmit`:
- Import `apiPost` from `@/lib/api`
- Set a `loading` state to `true`
- Call `apiPost<{ ok: boolean; error?: string }>(\`${cfg.api.trip_reviews}${tripId}/reviews/\`, { rating, body: loved, headline: "" })` where `cfg = window.TAPNE_RUNTIME_CONFIG`
- On success (`ok === true`): show the existing `toast.success("Thanks for sharing your experience ❤️")`, close the modal, reset the form, and call `onReviewSubmitted?.()`
- On error: show `toast.error(data.error || "Could not submit review. Please try again.")` and keep the modal open
- Always set `loading` to `false` in a finally block
- Disable the submit button while `loading` is true

**4. In `src/pages/TripDetail.tsx`**, find where `ReviewModal` is used and pass:
- `tripId={trip.id}`
- `onReviewSubmitted={() => { /* refetch trip detail */ fetchTrip(); }}` (or whatever the local data-fetch function is called)

---

## Prompt 4 — Fix "Ask a Question" (Bug 5)

In `src/pages/TripDetail.tsx`, the "Ask a Question" button in the "Meet your hosts" section currently just navigates to `/inbox` without telling the server to open a DM thread with the host. The user arrives at a blank inbox with no conversation pre-selected.

The Django API endpoint is: `POST /frontend-api/dm/start/`
Request body: `{ host_username: string }`
Response on success: `{ ok: true, thread_id: number }`
Response on error: `{ ok: false, error: string }`

Make these changes:

**1. Import `apiPost`** from `@/lib/api` at the top of `TripDetail.tsx` if not already imported.

**2. Replace the "Ask a Question" button's click handler** with an async function that:
- Calls `requireAuth` and returns early if the user is not authenticated (same auth-gate pattern used for join/bookmark in TripDetail)
- Sets a local `askingQuestion` loading state to `true`
- Gets `host_username` from `trip.host_username` (this field is already present in `TripData`)
- POSTs to `window.TAPNE_RUNTIME_CONFIG.api.dm_start` with body `{ host_username }`
- On success: navigates to `/inbox?thread=${thread_id}` so the inbox page can auto-open that conversation
- On error: calls `toast.error(data.error || "Could not start conversation. Please try again.")`
- Always sets `askingQuestion` to `false` in finally
- Disables the "Ask a Question" button while `askingQuestion` is true and shows a small loading spinner

**3. In `src/pages/Inbox.tsx`**, read the `thread` query parameter on mount:
```ts
const [searchParams] = useSearchParams();
const requestedThreadId = Number(searchParams.get("thread") || 0);
```
If `requestedThreadId > 0` and the thread list has loaded, auto-select that thread (set it as the active thread) so the user immediately sees the conversation with the host instead of a blank inbox.
