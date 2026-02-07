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

If they try any action, they are prompted to **login/signup**.

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
  Shared HTML layout pieces like `base.html`, cards, and the login prompt modal.
* `static/`
  Shared CSS/JS (small UI helpers).
* `infra/`
  Docker config (Postgres, MinIO/Redis).
* `tapne/` (inner folder)
  Django project configuration: `settings.py`, top `urls.py`, etc.

## Django apps (made with `startapp`)

These are feature modules:

* `accounts` (signup/login/logout, profile view/edit)
* `feed` (home logic: guest trending vs member personalized)
* `search` (search defaults + results)
* `trips` (trip list/detail + trip CRUD)
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

---

## Search (search app)

* `GET /search/`

  * Guest default: globally most searched trips/users/blogs
  * Member default: most searched by like-minded users
* `GET /search/?q=...&type=all|trips|users|blogs`

  * shows results

---

## Auth + Profiles (accounts app)

**Auth**

* `GET /accounts/signup/` + `POST /accounts/signup/`
* `GET /accounts/login/` + `POST /accounts/login/`
* `POST /accounts/logout/`

**My profile (member-only CRUD)**

* `GET /accounts/me/`
* `GET /accounts/me/edit/` + `POST /accounts/me/edit/`

**Public profile**

* `GET /u/<username>/`

  * Guest: limited profile
  * Member: full profile + follow/DM/bookmark

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

---

## Blogs (blogs app)

**Browse**

* `GET /blogs/`
* `GET /blogs/<slug>/`

  * Guest: full blog content, actions disabled
  * Member: full blog + actions

**CRUD (member-only)**

* `GET/POST /blogs/create/`
* `GET/POST /blogs/<slug>/edit/`
* `POST /blogs/<slug>/delete/`

---

## Follow + Bookmarks (social app) (member-only actions)

* `POST /social/follow/<username>/`
* `POST /social/unfollow/<username>/`
* `POST /social/bookmark/` (type=trip|user|blog, id=...)
* `POST /social/unbookmark/`
* `GET /social/bookmarks/` (member saved items)

---

## Join requests (enrollment app) (member-only actions)

* `POST /enroll/trips/<trip_id>/request/`
* `GET /enroll/hosting/inbox/` (host sees requests)
* `POST /enroll/requests/<request_id>/approve/`
* `POST /enroll/requests/<request_id>/deny/`

---

## Comments/replies + DMs (interactions app) (member-only actions)

**Comments**

* `POST /interactions/comment/` (target_type=trip|blog, target_id, text)
* `POST /interactions/reply/` (comment_id, text)

**DMs**

* `GET /interactions/dm/` (inbox)
* `GET /interactions/dm/<thread_id>/`
* `POST /interactions/dm/<thread_id>/send/`

---

## Reviews (reviews app)

* `POST /reviews/create/` (member-only)
* `GET /reviews/<target_type>/<target_id>/` (readable by all, if you want)

---

## Activity (activity app) (member-only)

* `GET /activity/`

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
* frontend: guests clicking action buttons get a “Login/Signup” prompt

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
* requires: `collectstatic` + correct `STATIC_ROOT` settings

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
