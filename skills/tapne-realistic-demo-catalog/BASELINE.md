# Baseline: `tapne-realistic-demo-catalog`

Reference map of every file this skill touches, data-count targets, and the host persona index.

---

## Key File Map

### New files created by this skill

| File | Role |
|------|------|
| `trips/management/commands/populate_demo_catalog.py` | Main seed command (~700 lines) |
| `trips/migrations/0008_is_demo.py` | Adds `trips_trip.is_demo` |
| `blogs/migrations/0003_is_demo.py` | Adds `blogs_blog.is_demo` |
| `accounts/migrations/0002_is_demo.py` | Adds `accounts_accountprofile.is_demo` |

### Edited files

| File | Change |
|------|--------|
| `trips/models.py` | Added `is_demo = BooleanField(default=False, db_index=True)` to `Trip`; patched `_live_trip_rows()` |
| `blogs/models.py` | Added `is_demo` to `Blog`; patched `_live_blog_rows()` |
| `accounts/models.py` | Added `is_demo` to `AccountProfile` |
| `tapne/features.py` | Added `demo_catalog_visible()` and `_demo_qs_filter()` |
| `tapne/settings.py` | Added `TAPNE_DEMO_CATALOG_VISIBLE` env-var flag |
| `feed/models.py` | Patched `_live_trip_rows()`, `_live_profile_rows()`, `_live_blog_rows()` |
| `search/models.py` | Patched `_live_profiles_for_query()`, `_live_trips_for_query()`, `_live_blogs_for_query()` |
| `frontend/views.py` | Patched homepage stats block to respect `_demo_qs_filter()` |

---

## Data-Count Targets

These are the minimum counts the seed command produces. Gate B in TROUBLESHOOTING.md verifies them.

| Model | Target |
|-------|--------|
| `User` (demo) | ≥ 70 |
| `AccountProfile` (`is_demo=True`) | ≥ 70 |
| `Trip` (`is_demo=True`) | ≥ 65 |
| `Blog` (`is_demo=True`) | ≥ 33 |
| `FollowRelation` (demo edges) | ≥ 400 |
| `Bookmark` (demo) | ≥ 280 |
| `EnrollmentRequest` (demo) | ≥ 120 |
| `Review` (demo) | ≥ 150 |
| `Comment` (demo) | ≥ 280 |
| `DirectMessageThread` (demo) | ≥ 45 |

---

## Host Persona Index

12 host personas — all `demo_` prefixed usernames. All seeded with `AccountProfile.is_demo=True`.

| # | username | display_name | location | specialty |
|---|----------|-------------|----------|-----------|
| 1 | `demo_priya` | Priya Sharma | Mumbai, India | Coastal, wellness |
| 2 | `demo_arjun` | Arjun Kapoor | Delhi, India | Trekking, camping |
| 3 | `demo_sanika` | Sanika Patil | Pune, India | Food & culinary |
| 4 | `demo_rajan` | Rajan Mehta | Bengaluru, India | Road trips, wildlife |
| 5 | `demo_kavitha` | Kavitha Nair | Chennai, India | Culture & heritage |
| 6 | `demo_yusuf` | Yusuf Khan | Hyderabad, India | Desert, adventure |
| 7 | `demo_leila` | Leila Nazari | Dubai, UAE | City breaks, premium |
| 8 | `demo_tao` | Tao Chen | Singapore | City breaks, food |
| 9 | `demo_amara` | Amara Osei | Nairobi, Kenya | Wildlife, adventure |
| 10 | `demo_elena` | Elena Vasquez | Barcelona, Spain | Culture, coastal |
| 11 | `demo_kiran` | Kiran Patel | London, UK | City breaks, culture |
| 12 | `demo_nisha` | Nisha Verma | Jaipur, India | Heritage, desert |

---

## Trip Coverage

70 trips total, covering all 11 trip types:

| trip_type | count | status mix |
|-----------|-------|------------|
| `city` | 7 | 5 published, 1 completed, 1 draft |
| `trekking` | 8 | 6 published, 2 completed |
| `coastal` | 6 | 4 published, 2 completed |
| `culture-heritage` | 6 | 5 published, 1 completed |
| `food-culture` | 5 | 4 published, 1 completed |
| `road-trip` | 5 | 4 published, 1 completed |
| `adventure-sports` | 7 | 5 published, 2 completed |
| `desert` | 4 | 3 published, 1 completed |
| `wildlife` | 4 | 3 published, 1 completed |
| `camping` | 4 | 3 published, 1 draft |
| `wellness` | 4 | 3 published, 1 completed |
| **Total** | **70** | **50 published, 15 completed, 5 draft** |

Price range: ₹4,500 – ₹55,000.

---

## Traveler Persona Count

60 traveler users (`demo_traveler_*` prefixed usernames), seeded from a fixed `TRAVELER_SEEDS` tuple in the command. Names drawn from Indian cities and international cities for realistic diversity.

---

## Feature Flag Summary

| Setting | Default | Controlled by |
|---------|---------|--------------|
| `TAPNE_DEMO_CATALOG_VISIBLE` | `DEBUG` value | `tapne/settings.py` + env var |
| `demo_catalog_visible()` | reads setting | `tapne/features.py` |
| `_demo_qs_filter()` | `{}` when visible, `{"is_demo": False}` when hidden | `tapne/features.py` |

`TAPNE_DEMO_CATALOG_VISIBLE` is **independent** of `TAPNE_ENABLE_DEMO_DATA`. See SKILL.md Hard Rule 5.
