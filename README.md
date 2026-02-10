---

## The tapne platform in one sentence

**tapne ([www.tapne.com](http://www.tapne.com))** is a social marketplace where people **host trips, write blogs, and build audiences**, and others **discover, follow, join, bookmark, and interact**, with different access for **guests** vs **members**.

---

# 1) Two user states

## Guest (not logged in)

Guests can **browse** but cannot **do actions**.

### Guest can view

* **Home**: top **trips + users + blogs** by overall website traffic (not personalized)
* **Search**: default to most searched trips/users/blogs (not personalized)
* **Trip details**: *limited* view (can read, but cannot join/comment/review/bookmark)
* **User profile**: *limited* view (can read, but cannot follow/DM/bookmark)
* **Blog details**: *full blog content* (but cannot comment/review/bookmark)

### Guest cannot do

* join trip
* follow user
* bookmark anything
* comment/reply
* DM
* review
* create/edit trips/blogs/profile
* activity/settings

If they try any action, they are shown the shared **auth modal** (login/signup).

---

## Member (logged in)

Members can browse **and** do actions.

### Member can view

* **Home**: content from **people they follow** + recommended content from **like-minded** users
* **Search**: default to what **like-minded users** search most, then shows results when they search
* **Trip details**: full view
* **User profile**: full view
* **Blog details**: full view

### Member can do

* request to join trips
* approve/deny join requests on trips they host
* follow users
* bookmark trips/users/blogs
* comment/reply (on trips/blogs)
* DM users
* review trips/blogs/hosts
* CRUD:

  * create/edit/delete trips
  * create/edit/delete blogs
  * edit profile
* view **Activity**
* edit **Settings**

---

# 2) How Django code is organized (normal folders vs Django apps)

## Normal folders (not Django apps)

These are shared assets:

* `templates/`
  Shared HTML scaffold used across apps. Current shared structure:

  ```text
  templates/
    base.html
    partials/
      cards/
        trip_card.html
        user_card.html
        blog_card.html
      modals/
        login_prompt_modal.html
    pages/
      home.html
      search.html
      trips/
        list.html
        detail.html
        form.html
        mine.html
      blogs/
        list.html
        detail.html
      users/
        profile.html
      activity/
        index.html
      settings/
        index.html
      enrollment/
        hosting_inbox.html
      accounts/
        me.html
        me_edit.html
  ```

  Conventions:
  * all pages extend `base.html`
  * shared cards/modals live under `templates/partials/`
  * guest-only blocked actions use `.js-guest-action` and `data-action-label`
  * auth is modal-only UI: no standalone `login.html` / `signup.html` templates
  * auth modal state is URL-driven with query keys: `auth`, `auth_reason`, `auth_error`, `auth_next`
* `static/`
  Shared CSS/JS scaffold:

  ```text
  static/
    css/
      tapne.css
    js/
      tapne-ui.js
  ```

  Conventions:
  * always reference files via `{% load static %}` + `{% static '...' %}`
  * frontend guest/member behavior toggles are in `static/js/tapne-ui.js`
  * visual system tokens/layout live in `static/css/tapne.css`
* `infra/`
  Docker config (Postgres, MinIO/Redis).
* `tapne/` (inner folder)
  Django project configuration: `settings.py`, top `urls.py`, etc.

## Django apps (made with `startapp`)

These are feature modules:

* `accounts` (modal auth endpoints, logout, profile view/edit, public profiles)
* `feed` (implemented home logic: guest trending vs member personalized, plus member feed preference seed tooling)
* `search` (search defaults + results)
* `trips` (trip list/detail + CRUD + member mine hub + trip seed tooling)
* `blogs` (blog list/detail + blog CRUD)
* `social` (follow + bookmark)
* `enrollment` (join requests + approvals)
* `interactions` (comments/replies + DMs)
* `reviews` (reviews)
* `activity` (member activity page)
* `settings_app` (member settings)

---

# 3) URL map (what pages exist and where they live)

## Project wiring: `tapne/urls.py`

This file just “connects” apps to URL prefixes.

---

## Home (feed app)

* `GET /`

  * Guest: top traffic trips/users/blogs
  * Member: follows + like-minded recommendations

### Current `feed` implementation contract

* project routing:
  * `tapne/urls.py` delegates root path (`/`) to `feed/urls.py`
  * `feed/urls.py` maps `path("", views.home, name="home")`
* view:
  * `feed/views.py::home` builds home context via `build_home_payload_for_user(...)`
  * context keys used by template: `trips`, `profiles`, `blogs`, `feed_mode`, `feed_reason`
* template behavior:
  * `templates/pages/home.html` shows “Guest home” vs “Member home” copy
  * `feed_reason` + `feed_mode` are rendered for runtime visibility/debug
* data and ranking:
  * `feed/models.py` defines typed demo catalog payloads for trips/users/blogs
  * guest mode (`guest-trending`) ranks by global popularity fields:
    * trips: `traffic_score`
    * users: `followers_count`
    * blogs: `reads`
  * member mode (`member-personalized`) boosts:
    * creators in `MemberFeedPreference.followed_usernames`
    * content matching `MemberFeedPreference.interest_keywords`
  * if no preference row exists, member mode still works via inferred fallback interests
* persistence:
  * `MemberFeedPreference` model stores one row per user (`OneToOneField`)
  * JSON lists are normalized to lowercase on save
* admin:
  * `feed/admin.py` registers `MemberFeedPreference` with counts/search/read-only timestamps
* tests:
  * `feed/tests.py` covers guest/member ranking expectations, verbose logging path, and bootstrap command behavior

### Feed verbose behavior

`feed` prints server-side debug lines prefixed with `[feed][verbose]` when verbose mode is enabled by any of:

* `?verbose=1` on request URL
* `verbose=1` in POST body
* `X-Tapne-Verbose: 1` request header

### Feed seed/bootstrap command

`feed` includes `bootstrap_feed` for seeding member personalization preferences used by home ranking.

```powershell
# Seed/update feed preferences for existing demo users with verbose logs
python manage.py bootstrap_feed --verbose

# Also create missing demo users before seeding preferences
python manage.py bootstrap_feed --verbose --create-missing-members
```

---

## Search (search app)

* `GET /search/`

  * Guest default: globally most searched trips/users/blogs
  * Member default: most searched by like-minded users
* `GET /search/?q=...&type=all|trips|users|blogs`

  * shows results

### Current `search` implementation contract

* project routing:
  * `tapne/urls.py` delegates `/search/` to `search/urls.py`
  * `search/urls.py` maps `path("", views.search_page, name="search")`
* view:
  * `search/views.py::search_page` builds search context via `build_search_payload_for_user(...)`
  * context keys used by template: `trips`, `profiles`, `blogs`, `search_mode`, `search_reason`, `search_query`, `active_type`, `has_query`
* template behavior:
  * `templates/pages/search.html` shows guest/member default copy
  * renders runtime ranking reason and mode (`search_reason`, `search_mode`) for visibility/debug
  * section titles switch between default state (`Top searched ...`) vs query state (`... results`)
* data and ranking:
  * typed demo catalog inputs come from `feed.models` for trips/users/blogs
  * guest mode (`guest-most-searched`) ranks by global search-demand signals
  * member mode (`member-like-minded`) boosts:
    * creators in `MemberFeedPreference.followed_usernames`
    * content matching `MemberFeedPreference.interest_keywords`
  * if no preference row exists, member mode still works via inferred fallback interests
* query behavior (`q` provided):
  * `type=users` and `type=all` include live account matches from `AUTH_USER_MODEL` + `AccountProfile`
  * `type=trips`/`type=blogs` and `type=all` include live trip/blog rows when models are present:
    * attempts to resolve `trips.Trip` and `blogs.Blog`
    * if those models are not available yet, search gracefully falls back to demo trip/blog results
  * dedupe strategy prefers live rows over demo placeholders on key collisions (`id`, `username`, `slug`)
* tests:
  * `search/tests.py` covers guest/member defaults, query type filtering, live-query merge behavior, verbose logging path, and bootstrap command behavior

### Search verbose behavior

`search` prints server-side debug lines prefixed with `[search][verbose]` when verbose mode is enabled by any of:

* `?verbose=1` on request URL
* `verbose=1` in POST body
* `X-Tapne-Verbose: 1` request header

### Search seed/bootstrap command

`search` includes `bootstrap_search` for previewing/validating guest/member search payload behavior.

```powershell
# Preview guest + member search payloads with verbose logs
python manage.py bootstrap_search --verbose

# Preview with a query and type filter
python manage.py bootstrap_search --verbose --query tapne --type users

# Create a missing member first, then preview member search payload
python manage.py bootstrap_search --verbose --member-username tapne --create-missing-member
```

---

## Auth + Profiles (accounts app)

**Auth**

* navbar shows one auth entry button: **Log in** (opens shared auth modal)
* shared modal lives in `templates/partials/modals/login_prompt_modal.html`
* `GET /accounts/signup/` and `GET /accounts/login/` are modal entry routes:
  * they redirect back to a safe origin with URL state (`?auth=signup` or `?auth=login`)
* `POST /accounts/signup/` creates user + profile and logs the user in
* `POST /accounts/login/` authenticates and logs the user in
* `POST /accounts/logout/`
* success/cancel behavior:
  * after successful login/signup, redirect to `next` (default: origin page)
  * closing modal keeps user on the same origin page (auth query keys are cleaned)
  * invalid submissions reopen the same modal mode with field + non-field errors visible

**My profile (member-only CRUD)**

* `GET /accounts/me/`
* `GET /accounts/me/edit/` + `POST /accounts/me/edit/`

**Public profile**

* `GET /u/<username>/`

  * Guest: limited profile
  * Member: full profile + follow/DM/bookmark

**Validation and security rules (`accounts`)**

* username:
  * validated by Django username validators
  * uniqueness is enforced **case-insensitively** on signup
* email:
  * normalized/validated with `email-validator`
  * uniqueness is enforced **case-insensitively**
* password:
  * must pass Django validators:
    * similarity check against user attributes
    * minimum length = `12`
    * common password blocked
    * numeric-only password blocked
  * must also pass custom complexity validator:
    * at least one uppercase letter
    * at least one lowercase letter
    * at least one digit
    * at least one symbol
    * no whitespace
* password confirmation (`password1`/`password2`) must match

**Modal behavior for protected actions**

* guest action buttons (`.js-guest-action`) open the same auth modal in login mode
* when action requires auth, modal shows contextual note: `Please log in to continue.`
* user can switch inline between login and signup via modal link (no full-page auth navigation)

---

## Trips (trips app)

**Browse**

* `GET /trips/`
* `GET /trips/<trip_id>/`

  * Guest: limited details
  * Member: full details + actions

**CRUD (member-only)**

* `GET/POST /trips/create/`
* `GET/POST /trips/<trip_id>/edit/`
* `POST /trips/<trip_id>/delete/`

**My Trips hub (member-only)**

* `GET /trips/mine/` (tabs: upcoming/hosting/past/saved)
* tab is URL-driven: `?tab=upcoming|hosting|past|saved`

### Current `trips` implementation contract

* project routing:
  * `tapne/urls.py` delegates `/trips/` to `trips/urls.py`
  * `trips/urls.py` maps:
    * `path("", views.trip_list_view, name="list")`
    * `path("create/", views.trip_create_view, name="create")`
    * `path("mine/", views.trip_mine_view, name="mine")`
    * `path("<int:trip_id>/", views.trip_detail_view, name="detail")`
    * `path("<int:trip_id>/edit/", views.trip_edit_view, name="edit")`
    * `path("<int:trip_id>/delete/", views.trip_delete_view, name="delete")`
* views and context:
  * `trips/views.py::trip_list_view` uses `build_trip_list_payload_for_user(...)`
  * list template context keys: `trips`, `trip_mode`, `trip_reason`, `trip_source`
  * `trips/views.py::trip_detail_view` uses `build_trip_detail_payload_for_user(...)`
  * detail template context keys: `trip`, `trip_detail_mode`, `trip_detail_reason`, `trip_detail_source`, `can_manage_trip`
  * `trips/views.py::trip_mine_view` uses `build_my_trips_payload_for_member(...)`
  * mine template context keys: `mine_trips`, `active_tab`, `tab_counts`, `mine_mode`, `mine_reason`
  * create/edit views use `TripForm` and render `templates/pages/trips/form.html`
* data and ranking:
  * live list mode reads published rows from `trips.Trip` (`is_published=True`)
  * guest list ranking (`guest-trending-live`/`guest-trending-demo`) sorts by `traffic_score`, then title
  * member list ranking (`member-like-minded-live`/`member-like-minded-demo`) boosts:
    * creators from `MemberFeedPreference.followed_usernames`
    * content matching `MemberFeedPreference.interest_keywords`
  * if no preference row exists, member list still works via inferred fallback interests
  * if no live `Trip` rows exist, list falls back to `feed.models` demo trip catalog
  * detail route can return source `live-db`, `demo-fallback`, or `synthetic-fallback`
  * guest detail mode is intentionally limited; member detail mode is full
* persistence (`Trip` model):
  * owner relation: `host -> AUTH_USER_MODEL` (`ForeignKey`)
  * content fields: `title`, `summary`, `description`, `destination`
  * scheduling fields: `starts_at`, `ends_at` (validation enforces `ends_at >= starts_at`)
  * ranking/visibility fields: `traffic_score`, `is_published`
  * ops fields: `created_at`, `updated_at`, indexed for host/time and published/time queries
* auth and ownership:
  * member-only: create/edit/delete/mine routes enforce `@login_required`
  * ownership: edit/delete routes resolve `Trip` by `pk` + `host=request.user`
  * detail allows unpublished rows only for the owning host
* tests:
  * `trips/tests.py` covers guest/member browse modes, CRUD auth/ownership, mine tab segmentation, verbose path, and bootstrap command behavior

### Trips verbose behavior

`trips` prints server-side debug lines prefixed with `[trips][verbose]` when verbose mode is enabled by any of:

* `?verbose=1` on request URL
* `verbose=1` in POST body
* `X-Tapne-Verbose: 1` request header

### Trips seed/bootstrap command

`trips` includes `bootstrap_trips` for creating/updating demo trip rows used by list/detail/search integration.

```powershell
# Seed trip rows and create missing demo hosts, with verbose logs
python manage.py bootstrap_trips --verbose --create-missing-hosts

# Seed only when hosts already exist (missing hosts are skipped)
python manage.py bootstrap_trips --verbose
```

---

## Blogs (blogs app)

**Browse**

* `GET /blogs/`
* `GET /blogs/<slug>/`

  * Guest: full blog content; member-only actions open the shared auth modal
  * Member: full blog content + action buttons enabled

**CRUD (member-only)**

* `GET/POST /blogs/create/`
* `GET/POST /blogs/<slug>/edit/`
* `POST /blogs/<slug>/delete/`

### Current `blogs` implementation contract

* project routing:
  * `tapne/urls.py` delegates `/blogs/` to `blogs/urls.py`
  * `blogs/urls.py` maps:
    * `path("", views.blog_list_view, name="list")`
    * `path("create/", views.blog_create_view, name="create")`
    * `path("<slug:slug>/", views.blog_detail_view, name="detail")`
    * `path("<slug:slug>/edit/", views.blog_edit_view, name="edit")`
    * `path("<slug:slug>/delete/", views.blog_delete_view, name="delete")`
* views and context:
  * `blogs/views.py::blog_list_view` uses `build_blog_list_payload_for_user(...)`
  * list template context keys: `blogs`, `blog_mode`, `blog_reason`, `blog_source`
  * `blogs/views.py::blog_detail_view` uses `build_blog_detail_payload_for_user(...)`
  * detail template context keys: `blog`, `blog_detail_mode`, `blog_detail_reason`, `blog_detail_source`, `can_manage_blog`
  * create/edit views use `BlogForm` and render `templates/pages/blogs/form.html` with `form_mode`, `page_title`, and submit labels
* template behavior:
  * `templates/pages/blogs/list.html` renders runtime ranking metadata (`blog_reason`, `blog_mode`, `blog_source`) and shows `Create blog` for members
  * `templates/pages/blogs/detail.html` renders detail metadata and conditionally shows owner-only `Edit blog` / `Delete blog` controls when `can_manage_blog=True`
* data and ranking:
  * live list mode reads published rows from `blogs.Blog` (`is_published=True`)
  * guest list ranking (`guest-most-read-live`/`guest-most-read-demo`) sorts by `reads`, then title
  * member list ranking (`member-like-minded-live`/`member-like-minded-demo`) boosts:
    * authors from `MemberFeedPreference.followed_usernames`
    * content matching `MemberFeedPreference.interest_keywords`
  * if no preference row exists, member list still works via inferred fallback interests
  * if no live `Blog` rows exist, list falls back to `feed.models` demo blog catalog
  * detail route can return source `live-db`, `demo-fallback`, or `synthetic-fallback`
  * guest detail mode is full-content (actions disabled in UI), member detail mode is full-content plus actions
* persistence (`Blog` model):
  * owner relation: `author -> AUTH_USER_MODEL` (`ForeignKey`)
  * content fields: `slug`, `title`, `excerpt`, `body`
  * ranking/visibility fields: `reads`, `reviews_count`, `is_published`
  * ops fields: `created_at`, `updated_at`, indexed for author/time, published/time, and read-ranking queries
* form and slug behavior (`BlogForm`):
  * editable fields: `title`, `slug` (optional), `excerpt`, `body`, `is_published`
  * when `slug` is blank, it auto-generates from title (`slugify`) and resolves collisions with numeric suffixes
  * when `slug` is provided, it is normalized and uniqueness-validated case-insensitively
* auth and ownership:
  * member-only: create/edit/delete routes enforce `@login_required`
  * ownership: edit/delete routes resolve `Blog` by `slug` + `author=request.user`
  * detail allows unpublished rows only for the owning author
* search integration:
  * `search` query flows can merge live blog rows from `blogs.Blog` when available
  * unpublished blog rows are excluded from search results to prevent draft leakage
* tests:
  * `blogs/tests.py` covers guest/member browse modes, publish visibility, CRUD auth/ownership, verbose path, and bootstrap command behavior
  * `search/tests.py` includes regression coverage for excluding unpublished live blogs from query results

### Blogs verbose behavior

`blogs` prints server-side debug lines prefixed with `[blogs][verbose]` when verbose mode is enabled by any of:

* `?verbose=1` on request URL
* `verbose=1` in POST body
* `X-Tapne-Verbose: 1` request header

### Blogs seed/bootstrap command

`blogs` includes `bootstrap_blogs` for creating/updating demo blog rows used by list/detail/search integration.

```powershell
# Seed blog rows and create missing demo authors, with verbose logs
python manage.py bootstrap_blogs --verbose --create-missing-authors

# Seed only when authors already exist (missing authors are skipped)
python manage.py bootstrap_blogs --verbose

# Customize password for any newly created demo authors
python manage.py bootstrap_blogs --verbose --create-missing-authors --demo-password "TapneDemoPass!123"
```

---

## Follow + Bookmarks (social app) (member-only actions)

* `POST /social/follow/<username>/`
* `POST /social/unfollow/<username>/`
* `POST /social/bookmark/` (type=trip|user|blog, id=...)
* `POST /social/unbookmark/`
* `GET /social/bookmarks/` (member saved items)

### Current `social` implementation contract

* project routing:
  * `tapne/urls.py` delegates `/social/` to `social/urls.py`
  * `social/urls.py` maps:
    * `path("follow/<slug:username>/", views.follow_user_view, name="follow")`
    * `path("unfollow/<slug:username>/", views.unfollow_user_view, name="unfollow")`
    * `path("bookmark/", views.bookmark_view, name="bookmark")`
    * `path("unbookmark/", views.unbookmark_view, name="unbookmark")`
    * `path("bookmarks/", views.bookmarks_view, name="bookmarks")`
* views and auth behavior:
  * follow/unfollow/bookmark/unbookmark are `POST` and enforce `@login_required`
  * bookmarks page is `GET` and enforces `@login_required`
  * redirects use safe same-origin `next` resolution (posted `next`, then safe referer, then fallback)
  * follow endpoint blocks self-follow attempts and keeps flow idempotent (`get_or_create`)
  * follow/unfollow actions sync `feed.MemberFeedPreference.followed_usernames` so home/search personalization reflects social graph changes immediately
* persistence:
  * `social.models.FollowRelation`
    * directed edge: `follower -> following`
    * uniqueness: one row per `(follower, following)`
    * integrity rule: self-follow is blocked at DB level (`CheckConstraint`)
    * indexed for inbound/outbound follow queries
  * `social.models.Bookmark`
    * one row per `(member, target_type, target_key)`
    * supported target types: `trip`, `user`, `blog`
    * canonical key strategy:
      * `trip`: numeric trip id as string
      * `user`: lowercase username
      * `blog`: lowercase slug
    * stores `target_label` + `target_url` snapshots to keep bookmark rows readable even if source rows change
* bookmark target resolution:
  * `trip` bookmarks resolve against live `trips.Trip`
  * `user` bookmarks resolve against live `AUTH_USER_MODEL`
  * `blog` bookmarks resolve against live `blogs.Blog`
  * invalid or missing targets are rejected on create, and unbookmark accepts canonical fallback normalization for delete paths
* template integration:
  * member action forms now post to social endpoints from:
    * `templates/partials/cards/trip_card.html`
    * `templates/partials/cards/blog_card.html`
    * `templates/partials/cards/user_card.html`
    * `templates/pages/trips/detail.html`
    * `templates/pages/blogs/detail.html`
    * `templates/pages/users/profile.html`
  * member top nav links to `/social/bookmarks/`
  * bookmarks page template: `templates/pages/social/bookmarks.html`
* trips integration:
  * `trips` saved tab (`/trips/mine/?tab=saved`) is now sourced from `social.Bookmark` trip targets
  * `tab_counts.saved` reflects live saved-trip bookmark count
* admin:
  * `social/admin.py` registers `FollowRelation` and `Bookmark` with list filters/search/autocomplete/read-only timestamps
* tests:
  * `social/tests.py` covers auth gating, follow/unfollow behavior, preference sync, bookmark create/delete/idempotency, bookmarks payload rendering, verbose logging, and bootstrap command behavior
  * `trips/tests.py` includes regression coverage for saved-tab bookmark integration

### Social verbose behavior

`social` prints server-side debug lines prefixed with `[social][verbose]` when verbose mode is enabled by any of:

* `?verbose=1` on request URL
* `verbose=1` in POST body
* `X-Tapne-Verbose: 1` request header

### Social seed/bootstrap command

`social` includes `bootstrap_social` for seeding follow graph rows and bookmark rows used by profile actions, bookmarks page, and saved-trip integration.

```powershell
# Seed social follows + bookmarks with verbose logs
python manage.py bootstrap_social --verbose --create-missing-members

# Run in existing-member mode (missing members are skipped)
python manage.py bootstrap_social --verbose
```

Recommended seed order when starting from an empty DB:

```powershell
python manage.py bootstrap_accounts --verbose
python manage.py bootstrap_trips --verbose --create-missing-hosts
python manage.py bootstrap_blogs --verbose --create-missing-authors
python manage.py bootstrap_social --verbose --create-missing-members
python manage.py bootstrap_interactions --verbose --create-missing-members
python manage.py bootstrap_reviews --verbose --create-missing-members
python manage.py bootstrap_enrollment --verbose --create-missing-members
```

If trip/blog catalog rows are missing, `bootstrap_social` still seeds follow and user-bookmark rows and logs skipped trip/blog bookmark seeds in verbose mode.
If trip/blog catalog rows are missing, `bootstrap_interactions` skips those comment seeds and still seeds any resolvable DM rows, with verbose skip logs.
If trip/blog catalog rows are missing, `bootstrap_reviews` still seeds reviews that can be resolved via demo fallback targets and logs any unresolved seeds in verbose mode.
If trip rows are missing, `bootstrap_enrollment` skips those enrollment seeds and logs each skip in verbose mode.

---

## Join requests (enrollment app) (member-only actions)

* `POST /enroll/trips/<trip_id>/request/`
* `GET /enroll/hosting/inbox/` (host sees requests)
* `POST /enroll/requests/<request_id>/approve/`
* `POST /enroll/requests/<request_id>/deny/`

### Current `enrollment` implementation contract

* project routing:
  * `tapne/urls.py` delegates `/enroll/` to `enrollment/urls.py`
  * `enrollment/urls.py` maps:
    * `path("trips/<int:trip_id>/request/", views.trip_request_view, name="trip-request")`
    * `path("hosting/inbox/", views.hosting_inbox_view, name="hosting-inbox")`
    * `path("requests/<int:request_id>/approve/", views.approve_request_view, name="approve")`
    * `path("requests/<int:request_id>/deny/", views.deny_request_view, name="deny")`
* views and auth behavior:
  * join request endpoint is `POST` and enforces `@login_required`
  * hosting inbox endpoint is `GET` and enforces `@login_required`
  * host review endpoints (approve/deny) are `POST` and owner-scoped by `trip__host=request.user`
  * redirects use safe same-origin `next` resolution (posted `next`, then safe referer, then fallback)
  * helper contract:
    * `submit_join_request(...)` manages idempotent create/reopen behavior
    * `apply_enrollment_decision(...)` applies host decisions with reviewer metadata
  * join request creation blocks:
    * missing trips
    * unpublished trips
    * host self-requests
  * join request flow is idempotent by `(trip, requester)`:
    * first request creates `pending`
    * repeated pending request does not duplicate rows
    * approved request remains approved
    * denied request is reopened back to pending on re-submit
  * hosting inbox filter contract:
    * `GET /enroll/hosting/inbox/?status=pending|approved|denied|all`
    * unsupported status values safely normalize to `pending`
* persistence:
  * `enrollment.models.EnrollmentRequest`
    * one row per `(trip, requester)` (`UniqueConstraint`)
    * statuses: `pending`, `approved`, `denied`
    * lifecycle: `pending -> approved|denied` (host decision)
    * optional requester note: `message` (`max_length=500`)
    * review metadata: `reviewed_by`, `reviewed_at`
    * indexed for host inbox and requester status queries
* payload and inbox behavior:
  * `build_hosting_inbox_payload_for_member(...)` powers host inbox rendering
  * supported inbox filters: `pending`, `approved`, `denied`, `all`
  * payload includes per-status counts and newest-first request rows
  * host inbox template context keys:
    * `hosting_requests`, `hosting_counts`, `hosting_inbox_mode`, `hosting_inbox_reason`, `active_status`
* template integration:
  * member trip actions post to enrollment endpoint from:
    * `templates/partials/cards/trip_card.html`
    * `templates/pages/trips/detail.html`
  * host entrypoints link to inbox from:
    * `templates/base.html` member nav
    * `templates/pages/trips/mine.html`
    * host branch in `templates/pages/trips/detail.html`
    * host branch in `templates/partials/cards/trip_card.html` (shows `Hosting inbox` instead of self-request action)
  * host inbox page template: `templates/pages/enrollment/hosting_inbox.html`
* admin:
  * `enrollment/admin.py` registers `EnrollmentRequest` with filters/search/autocomplete/read-only timestamps
* tests:
  * `enrollment/tests.py` covers auth gating, idempotent join-request behavior, host ownership for decisions, inbox filtering, verbose logging, and bootstrap command behavior

### Enrollment UI behavior

* guest behavior:
  * join actions remain blocked by shared guest action flow (`.js-guest-action`) and open the shared auth modal
* member behavior:
  * request-to-join submits a real `POST` to enrollment routes from trip cards/detail pages
* host behavior:
  * hosts do not submit self-requests; they navigate to hosting inbox and review pending rows
  * review actions are owner-scoped and use `POST` (approve/deny)

### Enrollment verbose behavior

`enrollment` prints server-side debug lines prefixed with `[enrollment][verbose]` when verbose mode is enabled by any of:

* `?verbose=1` on request URL
* `verbose=1` in POST body
* `X-Tapne-Verbose: 1` request header

### Enrollment seed/bootstrap command

`enrollment` includes `bootstrap_enrollment` for seeding host inbox rows with pending/approved/denied request states.

```powershell
# Seed enrollment requests with verbose logs (requires member seed users to exist)
python manage.py bootstrap_enrollment --verbose

# Also create missing demo requester members first
python manage.py bootstrap_enrollment --verbose --create-missing-members
```

---

## Comments/replies + DMs (interactions app) (member-only actions)

**Comments**

* `POST /interactions/comment/` (target_type=trip|blog, target_id, text)
* `POST /interactions/reply/` (comment_id, text)

**DMs**

* `GET /interactions/dm/` (inbox)
* `GET /interactions/dm/<thread_id>/`
* `POST /interactions/dm/<thread_id>/send/`

### Current `interactions` implementation contract

* project routing:
  * `tapne/urls.py` delegates `/interactions/` to `interactions/urls.py`
  * `interactions/urls.py` maps:
    * `path("comment/", views.comment_view, name="comment")`
    * `path("reply/", views.reply_view, name="reply")`
    * `path("dm/", views.dm_inbox_view, name="dm-inbox")`
    * `path("dm/<int:thread_id>/", views.dm_thread_view, name="dm-thread")`
    * `path("dm/<int:thread_id>/send/", views.dm_send_view, name="dm-send")`
* auth and method behavior:
  * all interactions endpoints are member-only (`@login_required`)
  * comment/reply/send actions are `POST`
  * DM inbox/thread pages are `GET`
  * post-action redirects use safe same-origin `next` resolution (posted `next`, then safe referer, then fallback)
* comments/replies behavior:
  * `submit_comment(...)` accepts `target_type=trip|blog`, `target_id`, `text`
  * target resolution supports:
    * live `trips.Trip` and `blogs.Blog` rows
    * fallback to seeded demo trip/blog catalog from `feed.models`
  * comments are normalized to single-space text and enforce max length (`2000`)
  * `submit_reply(...)` only allows replies to top-level comments (one-level reply depth)
  * reply rows inherit target metadata (`target_type`, `target_key`, `target_label`, `target_url`) from parent comment
* DM behavior:
  * `GET /interactions/dm/?with=<username>` can open or create a one-to-one thread, then redirects to thread view
  * self-thread creation is blocked
  * thread view is participant-scoped; non-participants receive `404`
  * send action validates participant membership and enforces message max length (`4000`)
* payload builders used by views/templates:
  * `build_comment_threads_payload_for_target(...)` returns top-level comments (newest first) and replies (oldest first)
  * `build_dm_inbox_payload_for_member(...)` returns threads ordered by latest activity (`updated_at desc`)
  * `build_dm_thread_payload_for_member(...)` returns messages ordered oldest-to-newest
* persistence:
  * `interactions.models.Comment`
    * fields: `author`, `target_type`, `target_key`, `target_label`, `target_url`, `text`, `parent`, timestamps
    * target types: `trip`, `blog`
    * integrity rule: self-parent blocked; reply target must match parent target
    * indexes for target/thread and author activity queries
  * `interactions.models.DirectMessageThread`
    * canonical 1:1 pair: `member_one`, `member_two`
    * constraints:
      * unique pair
      * no self-thread
      * canonical ordering (`member_one_id < member_two_id`) for idempotent lookups
    * indexed by both participants + `updated_at`
  * `interactions.models.DirectMessage`
    * fields: `thread`, `sender`, `body`, timestamps
    * sender must be a participant in the thread
    * indexed by thread timeline and sender timeline
* template integration:
  * trip/blog detail pages now render real comments and reply forms:
    * `templates/pages/trips/detail.html`
    * `templates/pages/blogs/detail.html`
  * member message entry points route to DM flows:
    * `templates/pages/users/profile.html`
    * `templates/partials/cards/user_card.html`
  * member nav includes `/interactions/dm/` in `templates/base.html`
  * DM pages:
    * `templates/pages/interactions/dm_inbox.html`
    * `templates/pages/interactions/dm_thread.html`
* admin:
  * `interactions/admin.py` registers:
    * `Comment`
    * `DirectMessageThread`
    * `DirectMessage`
* tests:
  * `interactions/tests.py` covers:
    * auth gating
    * comment/reply validation and persistence behavior
    * DM thread creation/access/send behavior
    * verbose logging path
    * bootstrap command behavior

### Interactions verbose behavior

`interactions` prints server-side debug lines prefixed with `[interactions][verbose]` when verbose mode is enabled by any of:

* `?verbose=1` on request URL
* `verbose=1` in POST body
* `X-Tapne-Verbose: 1` request header

### Interactions seed/bootstrap command

`interactions` includes `bootstrap_interactions` for seeding demo comment threads and direct-message threads.

```powershell
# Seed comments/replies + DM rows with verbose logs
python manage.py bootstrap_interactions --verbose

# Also create missing demo members first
python manage.py bootstrap_interactions --verbose --create-missing-members
```

`bootstrap_interactions` seeds:
* top-level comments on trip/blog targets
* one-level replies to selected comments
* two-member DM threads with initial message history

---

## Reviews (reviews app)

* `POST /reviews/create/` (member-only)
* `GET /reviews/<target_type>/<target_id>/` (readable by guests and members)

### Current `reviews` implementation contract

* project routing:
  * `tapne/urls.py` delegates `/reviews/` to `reviews/urls.py`
  * `reviews/urls.py` maps:
    * `path("create/", views.review_create_view, name="create")`
    * `path("<slug:target_type>/<str:target_id>/", views.review_target_list_view, name="target-list")`
* auth and method behavior:
  * create endpoint is `POST` and enforces `@login_required`
  * target reviews page is `GET` and readable by guests/members
  * create redirects use safe same-origin `next` resolution (posted `next`, then safe referer, then fallback)
* target resolution and payload behavior:
  * supported review targets: `trip`, `blog`
  * target resolution supports:
    * live `trips.Trip` and `blogs.Blog` rows
    * fallback to demo trip/blog catalog from `feed.models`
  * canonical target key strategy:
    * `trip`: numeric trip id as string
    * `blog`: lowercase slug
  * `build_reviews_payload_for_target(...)` returns:
    * newest-first review rows
    * total review count + average rating
    * 5-to-1 rating distribution buckets
    * `viewer_review` marker for the logged-in member’s own row (if present)
* persistence (`reviews.models.Review`):
  * one row per `(author, target_type, target_key)` (`UniqueConstraint`)
  * fields: `author`, `target_type`, `target_key`, `target_label`, `target_url`, `rating`, `headline`, `body`, timestamps
  * validation:
    * rating range is constrained to `1..5`
    * headline/body are whitespace-normalized before persistence
    * body must be non-empty and max length is `4000`
  * create route is idempotent per member/target:
    * first submit creates review row
    * repeated submit updates the existing row instead of creating duplicates
* blog integration:
  * review writes automatically sync live `blogs.Blog.reviews_count` for the reviewed blog target so blog list/detail counters stay consistent with review records
* template integration:
  * trip and blog detail pages now render review summary, rating distribution, and member review form:
    * `templates/pages/trips/detail.html`
    * `templates/pages/blogs/detail.html`
  * dedicated review list page:
    * `templates/pages/reviews/list.html`
* admin:
  * `reviews/admin.py` registers `Review` with filters/search/autocomplete/read-only timestamps
* tests:
  * `reviews/tests.py` covers auth gating, create/update semantics, guest-readable review listing, blog counter sync, verbose logging path, and bootstrap command behavior

### Reviews UI behavior

* guest behavior:
  * guests can browse aggregated review pages (`GET /reviews/<target_type>/<target_id>/`)
  * trip/blog detail pages show review summaries, but write actions trigger the shared auth modal (`.js-guest-action`)
* member behavior:
  * members can post or update one review per target (trip/blog)
  * trip/blog detail pages include in-place review forms (`#reviews` anchor sections)
  * members can open the dedicated target review page for full review history and rating distribution

### Reviews verbose behavior

`reviews` prints server-side debug lines prefixed with `[reviews][verbose]` when verbose mode is enabled by any of:

* `?verbose=1` on request URL
* `verbose=1` in POST body
* `X-Tapne-Verbose: 1` request header

### Reviews seed/bootstrap command

`reviews` includes `bootstrap_reviews` for creating/updating demo review rows against trip/blog targets.

```powershell
# Seed demo reviews with verbose logs
python manage.py bootstrap_reviews --verbose

# Also create missing demo members first
python manage.py bootstrap_reviews --verbose --create-missing-members
```

`bootstrap_reviews` behavior:
* idempotent for seeded rows (existing member-target reviews are updated, not duplicated)
* unresolved targets or missing members are skipped with verbose diagnostics

Quick verification flow:

```powershell
python manage.py migrate
python manage.py bootstrap_reviews --verbose --create-missing-members
python manage.py test reviews
```

---

## Activity (activity app) (member-only)

* `GET /activity/`

### Current `activity` implementation contract

* project routing:
  * `tapne/urls.py` delegates `/activity/` to `activity/urls.py`
  * `activity/urls.py` maps `path("", views.activity_index_view, name="index")`
* auth and method behavior:
  * activity page is member-only (`@login_required`)
  * route is `GET` only (`@require_http_methods(["GET"])`)
* request query contract:
  * `type` filter supports: `all|follows|enrollment|comments|replies|bookmarks|reviews`
  * unsupported `type` values are normalized and fall back to `all`
  * optional `limit` query controls timeline length (default `80`, clamped to `5..250`)
* view and context:
  * `activity/views.py::activity_index_view` builds context via `build_activity_payload_for_member(...)`
  * context keys used by template:
    * `activity_items`
    * `activity_counts`
    * `activity_mode`
    * `activity_reason`
    * `activity_filter`
* payload and filtering (`activity/models.py`):
  * normalized filters: `all|follows|enrollment|comments|replies|bookmarks|reviews`
  * stream mode: `member-activity`
  * stream ordering: newest first by event timestamp
  * actor self-noise suppression:
    * incoming activity rows exclude self-authored/self-acted events where applicable
  * activity counts include:
    * follows (`social.FollowRelation`)
    * enrollment decisions (`enrollment.EnrollmentRequest`)
    * comments/replies (`interactions.Comment`)
    * bookmarks (`social.Bookmark`)
    * reviews (`reviews.Review`)
  * target ownership rules:
    * comments/bookmarks/reviews are scoped to member-owned trip/blog targets where applicable
    * reply activity is scoped to replies on the member’s own comments
  * enrollment activity scope:
    * includes approved/denied decisions for the member’s own join requests
    * uses reviewer/host attribution and reviewed timestamp when available
  * fallback behavior:
    * guest/invalid-member payloads are explicit and safe (`guest-not-allowed` / empty payload)
    * missing/unknown target metadata falls back to safe labels/URLs instead of hard failures
* template behavior:
  * `templates/pages/activity/index.html` renders:
    * member activity summary metadata (`activity_reason`, `activity_mode`)
    * filter tabs with counts
    * timeline cards with actor, action, target, timestamp, and preview text
    * empty-state guidance including bootstrap command hint
* tests:
  * `activity/tests.py` covers:
    * auth gating
    * unified activity payload rendering
    * filter behavior
    * verbose logging path
    * bootstrap command behavior

### Activity UI behavior

* guest behavior:
  * direct access to `/activity/` redirects to modal login entry route (`/accounts/login/?next=/activity/`)
* member behavior:
  * timeline defaults to `type=all`
  * filter tabs expose category-specific streams with per-category counts
  * empty categories render deterministic empty states (no server error/no blank UI)

### Activity verbose behavior

`activity` prints server-side debug lines prefixed with `[activity][verbose]` when verbose mode is enabled by any of:

* `?verbose=1` on request URL
* `verbose=1` in POST body
* `X-Tapne-Verbose: 1` request header

### Activity seed/bootstrap command

`activity` includes `bootstrap_activity` for seeding activity-source rows across follows, enrollment decisions, comments/replies, bookmarks, and reviews.

```powershell
# Seed demo activity rows with verbose logs
python manage.py bootstrap_activity --verbose

# Also create missing demo members first
python manage.py bootstrap_activity --verbose --create-missing-members
```

`bootstrap_activity` behavior:
* idempotent for seeded rows (existing rows are reused/updated where appropriate)
* can create missing demo members (`mei`, `arun`, `sahar`, `nora`) when `--create-missing-members` is enabled
* unresolved targets (for example missing trip/blog seeds) are skipped with verbose diagnostics

Quick verification flow:

```powershell
python manage.py migrate
python manage.py bootstrap_activity --verbose --create-missing-members
python manage.py test activity
```

---

## Settings (settings_app) (member-only)

* `GET /settings/`
* `POST /settings/`

---

# 4) The single rule that makes everything work

* **GET routes** are mostly browseable by guests (sometimes “limited” rendering).
* **POST routes** are actions and are **member-only**.

Enforcement is simple:

* backend: `@login_required` on member-only routes
* frontend: guests clicking action buttons open the shared login/signup modal
* auth flow keeps users on-origin by default (`next`/origin-safe redirects)

---

## Faithful-to-production strategy (local vs real world)

### Goal

Develop on your laptop in a way that behaves like production, so deploying to GCP later is mostly:
**change env values + deploy**, not rewrite code.

### Principle

**Same code. Different configuration.**

* Local config comes from `.env`
* Production config comes from **Cloud Run env vars** + **Secret Manager**
* Code never hardcodes URLs/ports/credentials. It reads env vars and computes derived values.

---

# Local development stack (your laptop = mini cloud)

## 0) Run the app the same way as production (container + real web server)

To avoid “works on my machine” surprises, local should run the Django web app in a **Docker container** with a production-style server (e.g., gunicorn), just like Cloud Run.

* Local: Docker Compose runs `web` + `db` + `minio` + `redis`
* Production: same container image runs on Cloud Run

> You can still use `python manage.py runserver` for quick debugging, but the “most faithful” path is containerized `web`.

### Use `infra\setup-faithful-local.ps1` as the standard local entrypoint

This script is the recommended way to run local because it enforces the same shape as production:

* validates infra files (`config.json`, compose, Dockerfile, `.env.example`, `requirements.txt`)
* initializes `.env` from `.env.example` (and validates required keys)
* checks Docker CLI, Docker Compose, and Docker daemon availability
* starts `web`, `db`, `minio`, `redis` with Docker Compose
* waits for service health checks before printing final success

When app code is not present yet:

* if `manage.py` is missing, it auto-creates a minimal placeholder Django bootstrap so the stack can still come up
* generated placeholder files:
  * `manage.py`
  * `tapne/__init__.py`
  * `tapne/settings.py`
  * `tapne/urls.py`
  * `tapne/wsgi.py`
  * `tapne/asgi.py`
  * `.tapne-placeholder-generated`

Replace placeholder files with real app code as soon as your actual Django project is available.

### Common commands

```powershell
# Full local stack (build + start + health wait)
.\infra\setup-faithful-local.ps1 --verbose

# Same as above using native PowerShell verbosity switch
.\infra\setup-faithful-local.ps1 -Verbose

# Start without rebuilding web image
.\infra\setup-faithful-local.ps1 -NoBuild --verbose

# Only validate/generate files; do not start containers
.\infra\setup-faithful-local.ps1 -GenerateOnly --verbose

# Regenerate .env from template with fresh random secrets
.\infra\setup-faithful-local.ps1 -ForceEnv --verbose

# Bring up infra only (db/minio/redis), skip web
.\infra\setup-faithful-local.ps1 -InfraOnly --verbose

# Increase health wait timeout (seconds)
.\infra\setup-faithful-local.ps1 --verbose -HealthTimeoutSeconds 300
```

### Health semantics

The script prints final success only after health checks pass:

* `[OK] Service 'db' is healthy.`
* `[OK] Service 'minio' is healthy.`
* `[OK] Service 'redis' is healthy.`
* `[OK] Service 'web' is healthy.` (unless `-InfraOnly`)
* `[OK] Local production-faithful stack is ready.`

If a service becomes unhealthy or fails to start within timeout, the script fails fast and surfaces logs for diagnosis.

### Stop and cleanup

```powershell
# Stop and remove containers + network
docker compose --project-directory . --env-file .\.env -f .\infra\docker-compose.yml down

# Optional: include volumes (deletes local Postgres/Redis/MinIO data)
docker compose --project-directory . --env-file .\.env -f .\infra\docker-compose.yml down -v
```

### Troubleshooting

* `Docker CLI was not found on PATH`:
  install Docker Desktop, reopen terminal, rerun script.
* `Docker daemon is not reachable`:
  start Docker Desktop and wait for it to show Running.
* `web` stays in `starting`:
  wait for migrations/collectstatic to complete, then re-check with:

```powershell
docker compose --project-directory . --env-file .\.env -f .\infra\docker-compose.yml ps
docker compose --project-directory . --env-file .\.env -f .\infra\docker-compose.yml logs --tail=100 web
```

* Page renders as plain white/unstyled text:
  static files are likely not being served (CSS/JS 404). Verify:

```powershell
Invoke-WebRequest http://localhost:8000/static/css/tapne.css
Invoke-WebRequest http://localhost:8000/static/js/tapne-ui.js
```

If either request is not `200`:
* ensure Django settings include:
  * `STATIC_ROOT = BASE_DIR / "staticfiles"`
  * `STATICFILES_DIRS = [BASE_DIR / "static"]`
  * WhiteNoise middleware + `CompressedManifestStaticFilesStorage`
* rebuild/restart web so `collectstatic` runs again:

```powershell
docker compose --project-directory . --env-file .\.env -f .\infra\docker-compose.yml up -d --build web
```

---

## 1) Django Web App (Cloud Run Service equivalent)

**Port is configured and auto-picked up.**

* You set:

  * `APP_PORT=8000` in `.env`
* Your web server reads `APP_PORT` and binds to it (local)
* Your code computes:

  * `BASE_URL = http://localhost:<APP_PORT>`

Local:

* open `http://localhost:<APP_PORT>/`

Production:

* Cloud Run provides `PORT` automatically; the app binds to `PORT`
* `BASE_URL` is explicitly `https://www.tapne.com` (no port)

---

## 2) PostgreSQL in Docker (Cloud SQL equivalent)

**Port is configured and auto-picked up.**

* You set:

  * `DB_HOST_PORT=5432` in `.env`
* Docker Compose uses `${DB_HOST_PORT}:5432`
* Your app uses DB connection values from env (no hardcoding)

Local:

* Postgres runs on `localhost:<DB_HOST_PORT>`
* Django connects using a computed `DATABASE_URL`

Production:

* Cloud SQL connection details replace host/port
* Code stays the same, env values change

---

## 3) MinIO in Docker (Cloud Storage equivalent)

**Port is configured and auto-picked up.**

* You set:

  * `MINIO_PORT=9000` in `.env`
* Docker Compose exposes `${MINIO_PORT}:9000`
* Your app computes:

  * `STORAGE_ENDPOINT = http://localhost:<MINIO_PORT>`

Local:

* uploads go to MinIO (object storage), not local disk

Production:

* storage backend switches to GCS (`STORAGE_BACKEND=gcs`)
* uploads go to a GCS bucket via IAM (no access keys in code)

---

## 4) Redis in Docker (Queue/Cache equivalent)

Redis is useful for:

* background jobs (queues)
* caching (fast home/search defaults)
* rate limiting / anti-spam

**Port is configured and auto-picked up.**

* You set:

  * `REDIS_PORT=6379` in `.env`
* Docker Compose uses `${REDIS_PORT}:6379`
* Your app computes:

  * `REDIS_URL = redis://localhost:<REDIS_PORT>/0`

Production (GCP equivalent):

* Use **Memorystore for Redis**
* Provide `REDIS_URL` via Cloud Run env vars / Secret Manager

---

## 5) Static & media handling must match production

To avoid rewriting at deploy time:

### Static files (CSS/JS)

Production needs a strategy (dev server behavior is not production behavior):

* common simple option: **WhiteNoise** (static served by Django container)
* requires: `collectstatic` + correct static settings:
  * `STATIC_ROOT = BASE_DIR / "staticfiles"`
  * `STATICFILES_DIRS = [BASE_DIR / "static"]`
  * `STORAGES["staticfiles"]["BACKEND"] = "whitenoise.storage.CompressedManifestStaticFilesStorage"`
* `base.html` should load project assets with:
  * `href="{% static 'css/tapne.css' %}"`
  * `src="{% static 'js/tapne-ui.js' %}"`
* quick health check after startup:
  * `GET /static/css/tapne.css` -> `200`
  * `GET /static/js/tapne-ui.js` -> `200`
* local dev note: this Docker setup runs from a built image (no source bind mount),
  so template/static edits require rebuilding `web`:

```powershell
docker compose --project-directory . --env-file .\.env -f .\infra\docker-compose.yml up -d --build web
```

### Media uploads (photos)

Must never rely on local filesystem:

* Local: MinIO bucket
* Prod: GCS bucket

---

## 6) HTTPS/proxy correctness (Cloud Run reality)

Cloud Run sits behind a proxy/TLS terminator. Production settings should be env-driven, e.g.:

* secure cookies in prod
* correct CSRF trusted origins for `https://www.tapne.com`
* proxy SSL header config

Local keeps these relaxed.

---

## 7) Migrations are a deployment step (not “maybe on boot”)

Local:

* `python manage.py migrate`

Production:

* run migrations as a deliberate release step (often a one-off job/command) before new code serves traffic

---

# Recommended `.env` pattern (single source of truth for ports)

### Local `.env` example (ports defined once)

```text
APP_ENV=dev

# Ports (single source of truth)
APP_PORT=8000
DB_HOST_PORT=5432
MINIO_PORT=9000
REDIS_PORT=6379

# Derived in code (do not hardcode full URLs here)
HOST=localhost
SCHEME=http

# DB credentials (local)
DB_NAME=tapne_db
DB_USER=tapne
DB_PASSWORD=tapne_password

# Storage (local)
STORAGE_BACKEND=minio
MINIO_BUCKET=tapne-local
MINIO_ACCESS_KEY=...
MINIO_SECRET_KEY=...

# Redis (cache/queue)
REDIS_ENABLED=true

# Django secret
SECRET_KEY=dev-only
```

### What your Python config computes from that

* `BASE_URL = f"{SCHEME}://{HOST}:{APP_PORT}"`
* `DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{HOST}:{DB_HOST_PORT}/{DB_NAME}"`
* `STORAGE_ENDPOINT = f"{SCHEME}://{HOST}:{MINIO_PORT}"`
* `REDIS_URL = f"redis://{HOST}:{REDIS_PORT}/0"`

So you never repeat ports in multiple places.

---

# Production (GCP) equivalent

In production you still “auto-pick up” ports, but differently:

* Cloud Run sets `PORT` automatically
* Your app binds to `PORT`
* `BASE_URL` is explicitly `https://www.tapne.com`

And:

* DB points to Cloud SQL
* Storage backend is GCS (via IAM)
* Redis points to Memorystore

Same code, different env.
