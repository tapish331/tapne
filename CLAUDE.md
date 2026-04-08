# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Tapne** is a Django-based social marketplace for hosting/joining trips and writing travel blogs. Website: www.tapne.com.

## Commands

### Backend (Django)

```bash
# Run locally (full stack: Postgres, MinIO, Redis, Django)
docker-compose -f infra/docker-compose.yml up

# Django management
python manage.py runserver          # Dev server (no Docker)
python manage.py migrate
python manage.py test               # All tests
python manage.py test accounts      # Single app tests

# Seed demo data (each app has a bootstrap command)
python manage.py bootstrap_trips --verbose --create-missing-hosts
python manage.py bootstrap_accounts --verbose
# Pattern: bootstrap_<appname> --verbose [--create-missing-*]
```

### Frontend (React SPA)

```bash
cd lovable/
npm run dev        # Dev server
npm run build      # Production build → artifacts/lovable-production-dist/
npm run lint       # ESLint
npm test           # Vitest
npm run test:watch # Watch mode
```

### Deployment

```powershell
# Build React SPA for production
infra/build-lovable-production-frontend.ps1

# Deploy to GCP Cloud Run
infra/deploy-cloud-run.ps1
```

## Architecture

### Dual Frontend Strategy

The app has **two frontend approaches**, switchable via `LOVABLE_FRONTEND_ENABLED` in settings:

1. **Server-rendered** (Django templates + jQuery): Templates in `templates/`, shared CSS in `static/css/tapne.css`, behavior in `static/js/tapne-ui.js`
2. **React SPA** (Lovable): Located in `lovable/`, customization layer in `frontend_spa/src/`. The SPA is built and served as a static artifact from `artifacts/lovable-production-dist/`. Routes are intercepted in `frontend/urls.py` and served via `frontend_entrypoint_view`.

The `frontend_spa/` directory extends `lovable/` via TypeScript path aliases (`@frontend/*` → `frontend_spa/src/*`).

### Django Apps

Each feature is a self-contained Django app with `models.py`, `views.py`, `urls.py`, `tests.py`, `admin.py`, and `management/commands/bootstrap_<app>.py`.

Key apps and their roles:
- **`accounts`** — Auth + profiles (`AccountProfile` extends Django `User` via OneToOne)
- **`feed`** — Home feed personalization (`MemberFeedPreference` drives ranking for logged-in users; guest view shows trending)
- **`trips`** / **`blogs`** — Main content types (CRUD + detail views)
- **`social`** — Follow/bookmark (M2M relations)
- **`enrollment`** — Trip join requests (host inbox + member requests)
- **`interactions`** — Comments + direct messages
- **`reviews`** — Ratings for trips/hosts
- **`activity`** — Aggregated activity streams
- **`frontend`** — ~40 JSON API endpoints (`/frontend-api/*`) consumed by the React SPA, plus SPA route interception
- **`runtime`** — Redis caching utilities and health endpoint
- **`settings_app`** — Per-user preferences

### Key Patterns

**Payload builders:** Views don't build context ad-hoc — they call typed builder functions (e.g., `build_trip_list_payload_for_user()`, `build_home_payload_for_user()`). Payloads use `TypedDict` for structure.

**Demo fallbacks:** When live DB data is insufficient, apps fall back to typed demo payloads defined in `feed/models.py`. This lets the app render meaningfully without seeded data.

**Auth modal (not pages):** Login/signup are handled via a modal overlay (`templates/partials/modals/login_prompt_modal.html`) triggered by URL query params (`?auth=login`, `?auth=signup`, `?auth_next=/path/`). Guest actions use class `.js-guest-action` + `data-action-label`.

**Verbose debugging:** Pass `?verbose=1` or header `X-Tapne-Verbose: 1` to any view for detailed ranking/payload logs.

**Frontend API:** JSON endpoints in `frontend/views.py` use custom `DjangoJSONEncoder` — no Django REST Framework.

### Storage

`STORAGE_BACKEND` env var switches between MinIO (local, S3-compatible) and Google Cloud Storage (production). All upload logic routes through `media/` app.

### Infrastructure

- Local: Docker Compose (`infra/docker-compose.yml`) runs PostgreSQL 16, MinIO, Redis, and the Django app (Gunicorn)
- Production: GCP Cloud Run + Artifact Registry; config in `infra/cloud-run.service.yaml`
- Env vars: Copy `.env.example` → `.env`, generate `SECRET_KEY` and `MINIO_ROOT_PASSWORD`
