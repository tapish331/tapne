# CLAUDE.md

## Tapne — mandatory session rules

Before anything else in this repo, load and obey the canonical rules:

@RULES.md

Everything below is supplementary context. The rules above override anything in this file unless the user explicitly countermands them in-session.

---

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

### Frontend

All user-facing UI originates in the Lovable React SPA ([lovable/](lovable/)), customised via `frontend_spa/src/` through TypeScript path aliases (`@frontend/*` → `frontend_spa/src/*`). The SPA is built into `artifacts/lovable-production-dist/` and served by [frontend_entrypoint_view](frontend/views.py) for every SPA route declared in [frontend/urls.py](frontend/urls.py). A global catch-all in [tapne/urls.py](tapne/urls.py) routes any otherwise-unmatched URL to the same shell.

There is **no Django-rendered UI fallback**. The legacy `LOVABLE_FRONTEND_ENABLED` toggle, `templates/pages/**`, `templates/partials/**`, `templates/base.html`, `static/css/tapne.css`, `static/js/tapne-ui.js`, and the Django `else:` branch in `tapne/urls.py` were all removed in the SPA cutover. Django owns data, APIs, admin, and OAuth — not visual output.

Planned client routes live in [lovable/src/App.tsx](lovable/src/App.tsx); the deployed SPA entrypoints must mirror them in [frontend/urls.py](frontend/urls.py) (see RULES.md §6 drift rules).

### Django Apps

Each feature is a self-contained Django app with `models.py`, `views.py`, `urls.py`, `tests.py`, `admin.py`, and `management/commands/bootstrap_<app>.py`.

Key apps and their roles. With the SPA cutover, every app's Django-rendered HTML views were retired — the apps now own models, payload builders, management commands, admin, and whatever non-page URLs remain (image serving, JSON AJAX). User-facing UI is entirely the Lovable SPA, driven by `/frontend-api/*` endpoints in the `frontend` app.

- **`accounts`** — Auth + profiles (`AccountProfile` extends Django `User` via OneToOne).
- **`feed`** — Home-feed personalization (`MemberFeedPreference` drives ranking for logged-in users; guest view shows trending).
- **`trips`** / **`blogs`** — Main content types (models + payload builders). The `blogs` app is surfaced to end users as "Stories" in the Lovable SPA (`/stories/*`); the Django app, model, and `/frontend-api/blogs/*` endpoint all keep the `blogs` name. `trips/urls.py` still serves the trip banner image and destination autocomplete/details APIs.
- **`social`** — Follow/bookmark relations.
- **`enrollment`** — Trip join requests (host inbox + member requests).
- **`interactions`** — Comments + direct messages.
- **`reviews`** — Ratings for trips/stories.
- **`activity`** — Aggregated activity streams.
- **`frontend`** — JSON API endpoints (`/frontend-api/*`) consumed by the React SPA, plus SPA route interception and runtime-config injection.
- **`runtime`** — Redis caching utilities and health endpoint.
- **`settings_app`** — Per-user preferences; `settings_app/urls.py` exposes only the appearance JSON-update endpoint.

### Key Patterns

**Payload builders:** Views don't build context ad-hoc — they call typed builder functions (e.g., `build_trip_list_payload_for_user()`, `build_home_payload_for_user()`). Payloads use `TypedDict` for structure.

**Demo fallbacks:** When live DB data is insufficient, apps fall back to typed demo payloads defined in `feed/models.py`. This lets the app render meaningfully without seeded data.

**Auth modal (not pages):** Login/signup are handled via a modal overlay in the Lovable SPA — there are no `/login` or `/signup` routes. Auth goes through `/frontend-api/auth/*` (login, signup, logout, OTP) and `/frontend-api/auth/google/*` (OAuth start/callback).

**Verbose debugging:** Pass `?verbose=1` or header `X-Tapne-Verbose: 1` to any view for detailed ranking/payload logs.

**Frontend API:** JSON endpoints in `frontend/views.py` use custom `DjangoJSONEncoder` — no Django REST Framework.

### Storage

`STORAGE_BACKEND` env var switches between MinIO (local, S3-compatible) and Google Cloud Storage (production). All upload logic routes through `media/` app.

### Infrastructure

- Local: Docker Compose (`infra/docker-compose.yml`) runs PostgreSQL 16, MinIO, Redis, and the Django app (Gunicorn)
- Production: GCP Cloud Run + Artifact Registry; config in `infra/cloud-run.service.yaml`
- Env vars: Copy `.env.example` → `.env`, generate `SECRET_KEY` and `MINIO_ROOT_PASSWORD`
