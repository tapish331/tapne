# Troubleshooting: `tapne-realistic-demo-catalog`

Six acceptance gate checklists. Declare the skill run complete only when all six pass.

---

## Gap-Fix Protocol

When a gate fails:

1. **Identify the layer** — migration gap (Gate A), seed gap (Gate B), queryset patch gap (Gates C/D), or data-quality gap (Gates E/F).
2. **Fix the root cause** — do not work around it (e.g., do not manually insert rows to pass Gate B; fix the seed command).
3. **Re-run from the failed gate** — you don't need to restart from Gate A unless you changed models.
4. **Document the fix** — add a note to this file's "Known Issues" section at the bottom if the issue might recur.

---

## Gate A — Migrations

Verify the three new columns exist in the database.

```bash
python manage.py shell -c "
from django.db import connection
cursor = connection.cursor()
for table, col in [
    ('trips_trip', 'is_demo'),
    ('blogs_blog', 'is_demo'),
    ('accounts_accountprofile', 'is_demo'),
]:
    cursor.execute(f\"SELECT column_name FROM information_schema.columns WHERE table_name='{table}' AND column_name='{col}'\")
    row = cursor.fetchone()
    print(f'{table}.{col}:', 'OK' if row else 'MISSING')
"
```

**Expected:** All three print `OK`.

**Fix if failing:** `python manage.py migrate` — if migration files are missing, run `python manage.py makemigrations trips blogs accounts` first.

---

## Gate B — Seed Counts

Verify minimum row counts after running `populate_demo_catalog`.

```bash
python manage.py shell -c "
from trips.models import Trip
from blogs.models import Blog
from accounts.models import AccountProfile
from social.models import FollowRelation, Bookmark

trips = Trip.objects.filter(is_demo=True).count()
blogs = Blog.objects.filter(is_demo=True).count()
profiles = AccountProfile.objects.filter(is_demo=True).count()
follows = FollowRelation.objects.count()
bookmarks = Bookmark.objects.count()

print(f'Trips (demo): {trips} (need ≥65)')
print(f'Blogs (demo): {blogs} (need ≥33)')
print(f'Profiles (demo): {profiles} (need ≥70)')
print(f'FollowRelation total: {follows} (need ≥400)')
print(f'Bookmark total: {bookmarks} (need ≥280)')
"
```

**Expected:** All values at or above the threshold.

**Fix if failing:** Re-run `python manage.py populate_demo_catalog --verbose`. If still failing, check for exceptions in seed output and examine the specific `_seed_*` function.

---

## Gate C — Flag On (`TAPNE_DEMO_CATALOG_VISIBLE=true`)

Ensure demo rows appear in all public API responses.

```bash
# Start server with flag on
TAPNE_DEMO_CATALOG_VISIBLE=true python manage.py runserver 127.0.0.1:8000 --noreload &

# Home feed
curl -s http://localhost:8000/frontend-api/home/ | python -c "
import json, sys
d = json.load(sys.stdin)
trips = d.get('featured_trips', [])
profiles = d.get('community_profiles', [])
stats = d.get('stats', {})
print('home trips:', len(trips), '(need ≥8)')
print('home profiles:', len(profiles), '(need ≥6)')
print('stats travelers:', stats.get('travelers_count', 0), '(need ≥70)')
print('stats trips_hosted:', stats.get('trips_hosted_count', 0), '(need ≥50)')
"

# Trip list — total count
curl -s 'http://localhost:8000/frontend-api/trips/' | python -c "
import json, sys
d = json.load(sys.stdin)
print('trip list total:', d.get('total_count', 0), '(need ≥50)')
trips = d.get('trips', [])
types = {t.get('trip_type') for t in trips}
print('trip types present:', sorted(types))
print('all 11 types:', len(types) == 11)
"

# Blog list
curl -s http://localhost:8000/frontend-api/blogs/ | python -c "
import json, sys
d = json.load(sys.stdin)
print('blogs:', len(d.get('blogs', [])), '(need ≥20 in first page)')
"
```

**Expected:**
- `home trips ≥ 8`, `home profiles ≥ 6`
- `stats travelers ≥ 70`, `stats trips_hosted ≥ 50`
- `trip list total ≥ 50`
- All 11 trip types present
- `blogs ≥ 20`

**Fix if failing:** Check that `_demo_qs_filter()` import is in each model file and that `TAPNE_DEMO_CATALOG_VISIBLE` is being read correctly from settings.

---

## Gate D — Flag Off (`TAPNE_DEMO_CATALOG_VISIBLE=false`)

Ensure demo rows are hidden and no `demo_` usernames appear.

```bash
# Start server with flag off
TAPNE_DEMO_CATALOG_VISIBLE=false python manage.py runserver 127.0.0.1:8000 --noreload &

# Trip list should have 0 items (no real trips seeded)
curl -s 'http://localhost:8000/frontend-api/trips/' | python -c "
import json, sys
d = json.load(sys.stdin)
print('trip list total (flag off):', d.get('total_count', 0), '(expected 0 if no real trips)')
trips = d.get('trips', [])
demo_hosts = [t for t in trips if t.get('host_username', '').startswith('demo_')]
print('demo_ trips in list:', len(demo_hosts), '(must be 0)')
"

# Home stats — should reflect real-user counts only
curl -s http://localhost:8000/frontend-api/home/ | python -c "
import json, sys
d = json.load(sys.stdin)
stats = d.get('stats', {})
print('stats travelers (flag off):', stats.get('travelers_count', 0))
# Check no demo_ profiles appear
profiles = d.get('community_profiles', [])
demo_profiles = [p for p in profiles if p.get('username', '').startswith('demo_')]
print('demo_ profiles in home:', len(demo_profiles), '(must be 0)')
"
```

**Expected:** No `demo_` usernames in any response. Trip list empty (assuming no real trips exist). Stats reflect real-user counts.

**Fix if failing:** Check that all 8 queryset patch sites are importing `_demo_qs_filter` and applying it correctly. See BASELINE.md "Edited files" for the full list.

---

## Gate E — Detail Realism

Spot-check that a completed trip has full data.

```bash
python manage.py shell -c "
from trips.models import Trip
from reviews.models import Review

t = Trip.objects.filter(is_demo=True, status='completed').first()
if not t:
    print('ERROR: no completed demo trips found')
else:
    from trips.models import TripItineraryDay
    days = TripItineraryDay.objects.filter(trip=t).count()
    reviews = Review.objects.filter(target_key=str(t.pk), target_type='trip').count()
    print(f'Trip: {t.title}')
    print(f'  itinerary_days: {days} (need ≥3)')
    print(f'  highlights: {len(t.highlights or [])} (need ≥3)')
    print(f'  reviews: {reviews} (need ≥8)')
"
```

**Expected:** `itinerary_days ≥ 3`, `highlights ≥ 3`, `reviews ≥ 8`.

**Fix if failing:** Check `_seed_enrollments()` and `_seed_reviews()` in the command — reviews are only seeded for completed trips and require enrolled travelers.

---

## Gate F — Idempotency

Running the command twice without `--reset` must produce identical counts.

```bash
# Run 1
python manage.py populate_demo_catalog --verbose 2>&1 | tail -5

# Run 2
python manage.py populate_demo_catalog --verbose 2>&1 | tail -5

# Compare counts
python manage.py shell -c "
from trips.models import Trip
from blogs.models import Blog
from accounts.models import AccountProfile
print(Trip.objects.filter(is_demo=True).count(),
      Blog.objects.filter(is_demo=True).count(),
      AccountProfile.objects.filter(is_demo=True).count())
"
# Run again and compare — numbers must be identical
```

**Expected:** Second run produces zero new rows. Counts unchanged.

**Fix if failing:** Find the model whose `_seed_*` function is using `create()` instead of `update_or_create()` / `get_or_create()`. See BASELINE.md "Idempotency keys per model".

---

## Known Issues

_(Add entries here when a recurring gap is found and fixed.)_

| Date | Symptom | Root cause | Fix |
|------|---------|-----------|-----|
| — | — | — | — |
