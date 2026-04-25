# Skill: `tapne-realistic-demo-catalog`

Seed a realistic, maximum-traffic Tapne marketplace with ~70 demo users, ~70 trips, ~35 blogs, and ~1,300 social/activity records — all tagged `is_demo=True` — plus relevant trip/blog imagery so public demo surfaces never fall back to default images or placeholders.

**Scope boundary:** This skill operates exclusively on the Django backend (DB + Python). It never reads, writes, or modifies anything inside `lovable/` or `frontend_spa/`.

---

## Operator Runbook (8 steps)

### Step 0 — Pull latest code in both roots

```bash
# Django repo root
git pull

# Lovable SPA root
cd lovable && git pull && cd ..
```

Both pulls must succeed with no merge conflicts before proceeding. If either has uncommitted changes, stash or commit them first.

### Step 1 — Run migrations (once per deployment)

```bash
python manage.py migrate
```

Confirm the three new columns exist:
- `trips_trip.is_demo`
- `blogs_blog.is_demo`
- `accounts_accountprofile.is_demo`

### Step 2 — Audit all seeding and media entry points

Before seeding, confirm every model that accepts demo data or image attachments is covered. Run:

```bash
python manage.py shell -c "
from trips.models import Trip
from blogs.models import Blog
from accounts.models import AccountProfile
from social.models import FollowRelation, Bookmark
from enrollment.models import EnrollmentRequest
from reviews.models import Review
from interactions.models import Comment, DirectMessageThread, DirectMessage
from media.models import MediaAsset, MediaAttachment
print('All seeding targets importable — OK')
print('Trip image field:', Trip._meta.get_field('banner_image').get_internal_type())
print('Blog image field:', Blog._meta.get_field('cover_image_url').get_internal_type())
print('AccountProfile image field: none (expected until backend adds one)')
"
```

If any import fails, the model may have been renamed or moved. Fix the import in `populate_demo_catalog.py` before proceeding. If a public demo surface still depends on fallback imagery, fix the seeder itself; do not patch images manually in admin/storage after the run.

### Step 3 — Seed with maximum-traffic data and real imagery

```bash
python manage.py populate_demo_catalog --verbose
```

"Maximum traffic" means all seed targets are populated at their upper bounds:
- 72 users, 70 trips (50 published, 15 completed, 5 draft)
- 35 blogs, 500+ follows, 300+ bookmarks
- 130+ enrollments, 180+ reviews, 300+ comments, 50+ DM threads
- every demo trip that can appear on cards/detail/dashboard has a non-empty, content-relevant `banner_image`
- every demo blog has a non-empty, content-relevant `cover_image_url`
- if trip/blog detail pages use `media.MediaAttachment`, seed contextual image attachments for those high-traffic targets after the base rows exist
- no seeded trip/blog may rely on `feed._default_trip_banner_url(...)`, `build_trip_banner_fallback_url(...)`, `Blog._default_cover_image_url()`, or frontend `/placeholder.svg`
- `AccountProfile` does not currently expose a backend avatar field in this repo; do not invent profile-image coverage until the schema/payload exists

Expected output: `[populate_demo_catalog] Done. Seeded N users, N trips, N blogs, …`

Re-running without `--reset` is always safe (pure upsert — idempotent).

### Step 4 — Verify seed counts (Gate B)

```bash
python manage.py shell -c "
from trips.models import Trip
from blogs.models import Blog
from accounts.models import AccountProfile
from django.db.models import Q
print('Trips (demo):', Trip.objects.filter(is_demo=True).count())
print('Blogs (demo):', Blog.objects.filter(is_demo=True).count())
print('Profiles (demo):', AccountProfile.objects.filter(is_demo=True).count())
print('Trips missing banner_image:', Trip.objects.filter(is_demo=True).filter(Q(banner_image='') | Q(banner_image__isnull=True)).count())
print('Blogs missing cover_image_url:', Blog.objects.filter(is_demo=True).filter(Q(cover_image_url='') | Q(cover_image_url__isnull=True)).count())
"
```

Expected: trips ≥ 65, blogs ≥ 33, profiles ≥ 70, and both missing-image counts must be `0`.

### Step 5 — Flip demo visibility on

Set in environment (`.env` or Cloud Run revision env):

```
TAPNE_DEMO_CATALOG_VISIBLE=true
```

Restart the server. Run Gate C and Gate G checks (see TROUBLESHOOTING.md).

### Step 6 — Flip demo visibility off (production)

```
TAPNE_DEMO_CATALOG_VISIBLE=false
```

Redeploy Cloud Run revision. Run Gate D checks (see TROUBLESHOOTING.md).

### Step 7 — Reset demo data (if needed)

```bash
python manage.py populate_demo_catalog --reset --confirm --verbose
```

`--reset` deletes ALL `is_demo=True` rows before re-seeding. See Hard Rule 5 before running on any shared DB.

### Step 8 — Confirm lovable git status is clean

```bash
cd lovable && git status
```

**Expected:** `nothing to commit, working tree clean`

If `git status` shows any modified or untracked files, this skill has violated its scope boundary. Stop immediately, investigate what changed, and do not proceed until the working tree is clean. This skill must not leave any trace in `lovable/`.

---

## Hard Rules

1. **Never modify anything inside `lovable/` or `frontend_spa/`.** This skill is backend-only. All seeding is done via Django management commands and ORM writes. If any implementation step requires editing a file under `lovable/` or `frontend_spa/`, it is out of scope — stop and raise it separately. Step 8 enforces this at the end of every run.

2. **Never run `populate_demo_catalog` without running migrations first.** The command writes to `is_demo` columns that don't exist pre-migration.

3. **Never set `TAPNE_DEMO_CATALOG_VISIBLE=true` without seeding first.** The flag only controls visibility of existing rows; an unseeded DB with the flag on shows nothing.

4. **Re-running the command without `--reset` is always safe.** All creates use `update_or_create` / `get_or_create` — no duplicate rows. The same applies to image coverage: re-runs must keep demo trips/blogs fully populated instead of stacking duplicate media or drifting to blank fields.

5. **`--reset` deletes ALL `is_demo=True` rows.** Do not run on a shared DB that has real users whose usernames happen to start with `demo_` (the command wipes rows by `AccountProfile.is_demo=True`, not by prefix, but verify before use on production).

6. **`TAPNE_DEMO_CATALOG_VISIBLE` is orthogonal to `TAPNE_ENABLE_DEMO_DATA`.** They control independent systems. `TAPNE_ENABLE_DEMO_DATA` controls in-memory constant fallbacks when DB is empty; `TAPNE_DEMO_CATALOG_VISIBLE` controls DB-seeded demo row visibility. Both can be active simultaneously.

7. **Never add `is_demo` to Django's `User` model.** `AccountProfile.is_demo` is the user-level flag. The `User` table is not owned by this feature.

8. **`TAPNE_DEMO_CATALOG_VISIBLE` is read at settings load time.** Changing it in Cloud Run requires a new revision — it does not take effect on a running server.

9. **Default-image fallbacks do not count as success.** A seeded trip/blog is incomplete if it still depends on `Blog._default_cover_image_url()`, `_default_trip_banner_url(...)`, `build_trip_banner_fallback_url(...)`, or frontend `/placeholder.svg`.

10. **Do not promise profile avatars unless the backend actually supports them.** Today `AccountProfile` has no image field and the typed feed payload does not carry profile image URLs. Document that gap instead of pretending it was seeded.

11. **Declare the run done only after all acceptance gates in TROUBLESHOOTING.md pass.** Partial gate failures indicate migration, seeding, queryset-patch, or image-coverage gaps.

---

## Companion References

| Doc | Purpose |
|-----|---------|
| [BASELINE.md](BASELINE.md) | Key file map, data-count targets, host persona index |
| [DATASET.md](DATASET.md) | Full human-readable seed catalog (personas, trips, blogs) |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Gap-fix protocol, acceptance gate checklists A–G |
| [SETUP.md](SETUP.md) | Env-var setup, migration order, flag-flip procedure |
