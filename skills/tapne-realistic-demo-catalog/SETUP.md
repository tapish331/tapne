# Setup: `tapne-realistic-demo-catalog`

Environment variable configuration, migration order, and flag-flip procedure.

---

## Environment Variables

### `TAPNE_DEMO_CATALOG_VISIBLE`

| Value | Effect |
|-------|--------|
| `true` | Demo rows (`is_demo=True`) appear in all public trip/blog/profile lists |
| `false` | Demo rows are filtered out of every public query |
| _(unset)_ | Defaults to `DEBUG` — demo rows visible in local dev, hidden in production |

**Where to set:**

- **Local dev (`.env`):**
  ```
  TAPNE_DEMO_CATALOG_VISIBLE=true
  ```
- **Cloud Run revision env (production):**
  ```
  TAPNE_DEMO_CATALOG_VISIBLE=false
  ```

This setting is read at **Django settings load time** (via `env_bool()` in `tapne/settings.py`). A running server does not see changes — a restart or new Cloud Run revision is required.

### `TAPNE_ENABLE_DEMO_DATA`

Separate flag. Controls in-memory constant fallbacks (pre-existing feature). Does not interact with `TAPNE_DEMO_CATALOG_VISIBLE`. See SKILL.md Hard Rule 5.

---

## Migration Order

Run these in order. Each depends on the previous model change.

```bash
# Apply all pending migrations (includes the three is_demo migrations)
python manage.py migrate
```

If the migrations haven't been generated yet (fresh checkout):

```bash
python manage.py makemigrations trips --name is_demo
python manage.py makemigrations blogs --name is_demo
python manage.py makemigrations accounts --name is_demo
python manage.py migrate
```

Expected migration files after this step:
- `trips/migrations/0008_is_demo.py`
- `blogs/migrations/0003_is_demo.py`
- `accounts/migrations/0002_is_demo.py`

---

## Seed Command Reference

```bash
# Standard seed (safe to re-run)
python manage.py populate_demo_catalog

# With progress output
python manage.py populate_demo_catalog --verbose

# Dry run (no DB writes)
python manage.py populate_demo_catalog --dry-run

# Reset all demo rows, then re-seed
python manage.py populate_demo_catalog --reset --confirm --verbose

# Seed users, trips, blogs only (skip follows/bookmarks)
python manage.py populate_demo_catalog --skip-social

# Seed without enrollments, reviews, comments, DMs
python manage.py populate_demo_catalog --skip-activity
```

---

## Flag-Flip Procedure

### Turning demo catalog on (local dev or staging)

1. Set `TAPNE_DEMO_CATALOG_VISIBLE=true` in `.env`
2. Ensure seed is complete (Gate B)
3. Restart Django: `python manage.py runserver`
4. Run Gate C checks (TROUBLESHOOTING.md)

### Turning demo catalog off (production cutover)

1. In Cloud Run service config, set `TAPNE_DEMO_CATALOG_VISIBLE=false`
2. Deploy a new revision
3. Run Gate D checks (TROUBLESHOOTING.md)
4. Confirm no `demo_` usernames appear in any API response

### Turning demo catalog on in production

Only do this if you want demo data visible on the live site (e.g., for investor demo mode):

1. Ensure seed ran against the production DB: `python manage.py populate_demo_catalog --verbose`
2. Set `TAPNE_DEMO_CATALOG_VISIBLE=true` in Cloud Run env
3. Deploy new revision
4. Run Gate C checks

---

## Docker Compose (local full-stack)

When running via `docker-compose -f infra/docker-compose.yml up`, set the env var in the `django` service environment block in `infra/docker-compose.yml` or in `.env` (which `docker-compose` loads automatically):

```
# .env
TAPNE_DEMO_CATALOG_VISIBLE=true
```

Then run the seed inside the container:

```bash
docker-compose -f infra/docker-compose.yml exec django python manage.py migrate
docker-compose -f infra/docker-compose.yml exec django python manage.py populate_demo_catalog --verbose
```

---

## Reset / Teardown

To remove all demo data without affecting real rows:

```bash
python manage.py populate_demo_catalog --reset --confirm
```

Or from the shell:

```bash
python manage.py shell -c "
from trips.models import Trip
from blogs.models import Blog
from accounts.models import AccountProfile
from django.contrib.auth import get_user_model
User = get_user_model()

demo_uids = list(AccountProfile.objects.filter(is_demo=True).values_list('user_id', flat=True))
Trip.objects.filter(is_demo=True).delete()
Blog.objects.filter(is_demo=True).delete()
User.objects.filter(pk__in=demo_uids).delete()  # cascades profiles, follows, DMs
print('Demo data removed.')
"
```

**Warning:** The cascade from `User.delete()` removes FollowRelation, Bookmark, EnrollmentRequest, Review, Comment, and DM rows associated with demo users. This is the intended cleanup path.
