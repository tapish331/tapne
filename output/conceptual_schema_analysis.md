# Tapne Conceptual Schema Analysis

## Scope

This analysis is based on the current Django project structure and persisted model layer under:

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
- `activity/models.py`
- `search/models.py`

The project currently uses the built-in Django `auth_user` table plus **16 project-owned persisted tables**.

## Platform Shape

Tapne is a **social travel marketplace** with one central actor and two primary content types:

- `User / Member` is the central actor.
- `Trip` is the main marketplace aggregate.
- `Blog` is the main editorial/content aggregate.

Everything else supports discovery, conversion, trust, communication, personalization, or operations around those three concepts.

## Core Persisted Aggregates

### 1. Identity and personalization

- `auth_user` is the real authentication principal; the project does **not** define a custom user model.
- `AccountProfile` extends the user with public identity data.
- `MemberSettings` stores private preference and privacy settings.
- `MemberFeedPreference` stores lightweight personalization signals for ranking.

This is a classic **core identity + extension tables** pattern.

### 2. Marketplace content

- `Trip` is the richest aggregate root in the system.
  It carries schedule, pricing, itinerary, policies, publishing state, and host ownership.
- `Blog` is the secondary content aggregate.
  It carries authored story content, slug identity, tags, readership, and review count.

`Trip` and `Blog` are the two main public-facing artifacts that drive search, feed, bookmarking, commenting, reviewing, and media attachment.

### 3. Transactional conversion flow

- `EnrollmentRequest` is the conversion bridge between a traveler and a hosted trip.
- It models a small explicit lifecycle: `pending -> approved | denied`.

This makes `Trip` both a content object and a transactional object.

### 4. Social graph and private communication

- `FollowRelation` models directed user-to-user following.
- `Bookmark` models saved items.
- `DirectMessageThread` and `DirectMessage` model one-to-one messaging.

The DM thread uses a **canonical ordered member pair** pattern, which prevents duplicate threads for the same two members.

### 5. Trust and engagement

- `Comment` models public discussion.
- `Review` models public rating + feedback.

These are intentionally lightweight and attach to target content by canonical keys rather than direct foreign keys.

### 6. Media subsystem

- `MediaAsset` stores the uploaded file and file metadata.
- `MediaAttachment` maps an asset onto a target object.

This separates **file storage concerns** from **business attachment concerns**.

### 7. Operational support

- `RuntimeIdempotencyRecord` persists idempotency reservations and finalized responses.
- `RuntimeCounter` snapshots runtime counters.

These are not product-domain entities; they are platform-operational entities.

## Key Architectural Patterns

### Pattern A: repeated polymorphic target references

The project deliberately avoids Django generic foreign keys and instead repeats a normalized target pattern:

- `Comment(target_type, target_key)` -> `Trip | Blog`
- `Review(target_type, target_key)` -> `Trip | Blog`
- `Bookmark(target_type, target_key)` -> `Trip | Blog | User`
- `MediaAttachment(target_type, target_key)` -> `Trip | Blog | Review`

This is the most important schema-level design choice in the codebase.

Benefits:

- keeps tables simple and explicit
- avoids contenttypes dependency in the core write path
- preserves readable snapshots with `target_label` and `target_url`
- allows interaction history to survive target mutation or deletion

Tradeoff:

- referential integrity is enforced in application logic, not by database foreign keys

### Pattern B: derived read models instead of extra tables

`activity/models.py` and `search/models.py` are **projection builders**, not persistent domains.

- `Activity` is assembled from follows, enrollments, comments, bookmarks, reviews, and completed trips.
- `Search` ranks trips, profiles, destinations, blogs, and people from live tables plus demo catalog fallbacks.
- `Feed` similarly acts as a ranking/personalization layer over persisted content.

This means the schema is write-model centric, while several user-facing surfaces are computed on demand.

### Pattern C: live + demo catalog hybrid

Several core entities carry `is_demo`, and `feed/search` also support demo payload fallbacks.

This is a cross-cutting product concern rather than a separate bounded context.

## What The Diagram Emphasizes

The generated conceptual schema diagram focuses on:

- the user as the central actor
- the trip as the primary marketplace aggregate
- the blog as the secondary content aggregate
- explicit social and transactional edges
- polymorphic interaction patterns
- separation between persisted write models and computed read models

It intentionally does **not** try to mirror every column in the physical schema, because that would hide the actual domain structure.
