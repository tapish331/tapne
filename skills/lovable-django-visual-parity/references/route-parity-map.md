# Route Parity Map

Use this file to decide whether a Django entity should be compared directly, styled after a Lovable archetype, or created from scratch.

## Shared Entities

- Home:
  Lovable `/`
  Django `/`

- Trips list:
  Lovable `/trips`
  Django `/trips/`

- Trip detail:
  Lovable `/trips/:id`
  Django `/trips/<int:trip_id>/`

- Trip create/edit:
  Lovable `/create-trip`
  Django `/trips/create/` and `/trips/<int:trip_id>/edit/`

- My trips:
  Lovable `/my-trips`
  Django `/trips/mine/`

- Blogs list:
  Lovable `/blogs`
  Django `/blogs/`

- Profile surfaces:
  Lovable `/profile`
  Django `/accounts/me/`, `/accounts/me/edit/`, `/u/<username>/`

- Auth:
  Lovable `/login` and `/signup`
  Django auth modal flow driven from `/accounts/login/` and `/accounts/signup/`

- 404:
  Lovable catch-all `*`
  Django `404.html`

## Django-Only Entities And Their Lovable Archetypes

- Search:
  Django `/search/`
  Borrow Lovable home search shell plus trips-list result layout

- Blog detail:
  Django `/blogs/<slug>/`
  Borrow Lovable blog-card language plus trip-detail content rhythm

- Blog create/edit:
  Django `/blogs/create/`, `/blogs/<slug>/edit/`
  Borrow Lovable create-trip editor cards, sticky progress framing, and form density

- Bookmarks:
  Django `/social/bookmarks/`
  Borrow Lovable my-trips and profile card grids

- DM inbox:
  Django `/interactions/dm/`
  Borrow Lovable navbar/menu card language and profile/settings shells

- DM thread:
  Django `/interactions/dm/<int:thread_id>/`
  Borrow Lovable card shells, detail-page spacing, and compact form treatment

- Settings:
  Django `/settings/`
  Borrow Lovable profile editing and tab/card treatment

- Hosting inbox:
  Django `/enroll/hosting/inbox/`
  Borrow Lovable application manager and my-trips management patterns

- Activity:
  Django `/activity/`
  Borrow Lovable navbar notification styling and feed-card rhythm

- Reviews list:
  Django `/reviews/<slug:target_type>/<str:target_id>/`
  Borrow Lovable trip-detail side sections and card lists

- Legal/info pages:
  Django `/about/`, `/how-it-works/`, `/safety/`, `/contact/`, `/terms/`, `/privacy/`
  Borrow Lovable hero plus centered content-card compositions

## Lovable-Only Entities To Create In Django

- Create trip modal:
  Lovable `CreateTripModal`
  Django counterpart should launch draft creation / resume flow

- Booking modal:
  Lovable `BookingModal`
  Django counterpart belongs on trip detail

- Application modal:
  Lovable `ApplicationModal`
  Django counterpart belongs on trip detail for gated trips

- Embedded application manager:
  Lovable `ApplicationManager`
  Django can keep the standalone hosting inbox, but should also support a Lovable-style embedded review surface when parity work calls for it

## Centralized Django Control Points

- `static/css/lovable-parity.css`
- `templates/base.html`
- `static/js/tapne-ui.js`

Use those first for recurring tokens and shared chrome. Only fall back to per-template overrides when the difference is truly page-specific.
