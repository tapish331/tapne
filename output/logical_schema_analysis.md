# Tapne Logical Schema Analysis

## Scope

This logical schema analysis is based on the current Django models plus the actual SQLite schema in:

- `test_settings.sqlite3`
- `accounts/models.py`
- `blogs/models.py`
- `trips/models.py`
- `social/models.py`
- `enrollment/models.py`
- `interactions/models.py`
- `reviews/models.py`
- `media/models.py`
- `settings_app/models.py`
- `feed/models.py`
- `runtime/models.py`

## What "Logical Schema" Means Here

This diagram focuses on the **persisted write model**:

- concrete tables
- primary keys
- direct foreign keys
- one-to-one and one-to-many structure
- uniqueness and check constraints
- major logical attributes

It intentionally separates that from:

- **computed read models** such as home feed, search, and activity
- **framework support tables** that are real but not central to the product domain

## Persisted Table Inventory

### Core logical schema rendered in the main image

The main logical schema image includes:

1. `auth_user`
2. `accounts_accountprofile`
3. `settings_app_membersettings`
4. `feed_memberfeedpreference`
5. `trips_trip`
6. `blogs_blog`
7. `enrollment_enrollmentrequest`
8. `social_followrelation`
9. `social_bookmark`
10. `interactions_comment`
11. `interactions_directmessagethread`
12. `interactions_directmessage`
13. `reviews_review`
14. `media_mediaasset`
15. `media_mediaattachment`
16. `runtime_runtimeidempotencyrecord`
17. `runtime_runtimecounter`

### Framework tables present in the database but omitted from the main image

These exist and are valid parts of the physical schema, but they are framework support rather than the product’s core logical model:

- `auth_group`
- `auth_permission`
- `auth_group_permissions`
- `auth_user_groups`
- `auth_user_user_permissions`
- `django_admin_log`
- `django_content_type`
- `django_migrations`
- `django_session`

## Central Logical Structure

### 1. `auth_user` is the root identity table

The project uses Django’s built-in user table as the single identity anchor.

Three one-to-one extensions hang off it:

- `accounts_accountprofile`
- `settings_app_membersettings`
- `feed_memberfeedpreference`

This means the logical identity model is intentionally split into:

- authentication + account state in `auth_user`
- public-facing profile data in `accounts_accountprofile`
- private preference data in `settings_app_membersettings`
- ranking/personalization state in `feed_memberfeedpreference`

### 2. `trips_trip` is the dominant aggregate root

`trips_trip` is the richest table by far. Logically it combines:

- publishing state
- schedule
- pricing
- host logistics
- itinerary structure
- policy text
- denormalized discovery signals

It is directly referenced by:

- `enrollment_enrollmentrequest` through a real foreign key

It is indirectly targeted by:

- `social_bookmark`
- `interactions_comment`
- `reviews_review`
- `media_mediaattachment`

Those indirect relationships are implemented through polymorphic logical keys, not foreign keys.

### 3. `blogs_blog` is the secondary content aggregate

`blogs_blog` is simpler than `trips_trip`, but it participates in the same interaction model:

- can be bookmarked
- can be commented on
- can be reviewed
- can receive media attachments

It also stores denormalized engagement fields:

- `reads`
- `reviews_count`

### 4. `enrollment_enrollmentrequest` is the conversion table

This table connects a traveler to a hosted trip with a small explicit state machine:

- `pending`
- `approved`
- `denied`

The uniqueness rule `UNIQUE(trip_id, requester_id)` means a traveler can have at most one logical enrollment row per trip.

### 5. Social graph and messaging are explicit tables

- `social_followrelation` stores directed follow edges with self-follow prevention.
- `interactions_directmessagethread` stores one canonical thread per ordered user pair.
- `interactions_directmessage` stores the message rows inside those threads.

This is a clean logical split between:

- graph edges
- conversation containers
- conversation entries

### 6. Comments, reviews, bookmarks, and attachments use application-level polymorphism

These tables do **not** use foreign keys to content targets:

- `social_bookmark`
- `interactions_comment`
- `reviews_review`
- `media_mediaattachment`

Instead they store:

- `target_type`
- `target_key`
- snapshot fields like `target_label` and `target_url`

This is the defining logical pattern in the project.

It gives flexibility and stable historical display behavior, but it also means:

- relational integrity to the target content is enforced in application code
- the database cannot guarantee target existence for those rows

## Important Logical Design Decisions

### JSON-heavy schema in `trips_trip`

The trip table stores many structured collections in JSON columns:

- `extra_costs_not_included`
- `highlights`
- `itinerary_days`
- `included_items`
- `not_included_items`
- `things_to_carry`
- `suitable_for`
- `trip_vibe`
- `faqs`
- `draft_form_data`

This is logically significant because the project favors a **single rich trip aggregate** over many child tables.

### Denormalized ranking and engagement fields

Several tables contain derived counters or ranking signals:

- `trips_trip.traffic_score`
- `trips_trip.review_prompts_sent`
- `blogs_blog.reads`
- `blogs_blog.reviews_count`

These fields support feed/search/activity behavior without requiring separate warehouse-style tables.

### Computed surfaces are not separate write tables

The project has no persisted tables for:

- activity feed
- search index
- notifications
- destination catalog

Instead those surfaces are computed from the persisted domain tables at request time.

## Most Important Relationships

### Direct relational edges

- `auth_user` 1:1 `accounts_accountprofile`
- `auth_user` 1:1 `settings_app_membersettings`
- `auth_user` 1:1 `feed_memberfeedpreference`
- `auth_user` 1:N `trips_trip`
- `auth_user` 1:N `blogs_blog`
- `trips_trip` 1:N `enrollment_enrollmentrequest`
- `auth_user` 1:N `enrollment_enrollmentrequest` as requester
- `auth_user` 1:N `enrollment_enrollmentrequest` as reviewer
- `auth_user` 1:N `social_followrelation` in both follower and following roles
- `auth_user` 1:N `social_bookmark`
- `auth_user` 1:N `interactions_comment`
- `interactions_comment` 1:N `interactions_comment` via `parent_id`
- `auth_user` 1:N `reviews_review`
- `auth_user` 1:N `interactions_directmessagethread` in both participant roles
- `interactions_directmessagethread` 1:N `interactions_directmessage`
- `auth_user` 1:N `interactions_directmessage` as sender
- `auth_user` 1:N `media_mediaasset`
- `media_mediaasset` 1:N `media_mediaattachment`
- `auth_user` 0:N `runtime_runtimeidempotencyrecord`

### Logical but non-FK target relationships

- `social_bookmark` -> `Trip | Blog | User`
- `interactions_comment` -> `Trip | Blog`
- `reviews_review` -> `Trip | Blog`
- `media_mediaattachment` -> `Trip | Blog | Review`

## Diagram Strategy

The rendered logical schema image is optimized for readability rather than full DDL transcription:

- direct FK edges are shown explicitly
- logical target-key patterns are grouped and labeled
- `Trip` is visually emphasized because it is the largest aggregate
- computed read models are explicitly called out as omitted from the logical image
- framework tables are summarized instead of fully expanded
