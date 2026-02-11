# pyright: reportMissingImports=false, reportMissingModuleSource=false, reportUnknownMemberType=false
"""
Placeholder settings for local container bootstrap.

This file is intentionally minimal but production-aware:
- env-driven configuration
- PostgreSQL via DATABASE_URL
- Redis cache support
- WhiteNoise static serving
- MinIO-compatible S3 media storage
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

import dj_database_url


def env_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key, str(default))
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(key: str, default: int) -> int:
    raw_value = os.getenv(key, str(default))
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        parsed = int(default)
    return parsed


def env_csv(key: str, default: str) -> tuple[str, ...]:
    raw_value = os.getenv(key, default)
    values = [item.strip().lower() for item in raw_value.split(",") if item.strip()]
    return tuple(values)


def strip_url_scheme(url: str) -> str:
    normalized = url.strip()
    lowered = normalized.lower()
    if lowered.startswith("http://"):
        return normalized[7:]
    if lowered.startswith("https://"):
        return normalized[8:]
    return normalized


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "dev-placeholder-secret")
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "feed",
    "search",
    "trips",
    "blogs",
    "social",
    "enrollment",
    "interactions",
    "reviews",
    "activity",
    "settings_app",
    "media",
    "runtime"
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "tapne.urls"
WSGI_APPLICATION = "tapne.wsgi.application"
ASGI_APPLICATION = "tapne.asgi.application"

TEMPLATES: list[dict[str, Any]] = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.auth_modal_forms",
            ],
        }
    }
]

default_database_url: str = (
    os.getenv("DATABASE_URL")
    or "postgresql://{user}:{password}@{host}:{port}/{name}".format(
        user=os.getenv("DB_USER", "tapne"),
        password=os.getenv("DB_PASSWORD", "tapne_password"),
        host=os.getenv("DB_HOST", "db"),
        port=os.getenv("DB_PORT", "5432"),
        name=os.getenv("DB_NAME", "tapne_db"),
    )
)

DATABASES: dict[str, dict[str, Any]] = {
    "default": cast(
        dict[str, Any],
        dj_database_url.parse(default_database_url, conn_max_age=600, ssl_require=False),
    )
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Include project-level shared assets (templates/static scaffold).
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
# Keep fallback filesystem uploads out of the `media/` Django app package.
MEDIA_ROOT = BASE_DIR / "mediafiles"

STORAGES: dict[str, dict[str, Any]] = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Manifest storage is production-faithful but requires collectstatic output.
    # Use plain staticfiles storage in DEBUG/test runs to keep local iteration simple.
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

storage_backend = os.getenv("STORAGE_BACKEND", "filesystem").strip().lower()
if storage_backend == "minio":
    minio_bucket_name = os.getenv("AWS_STORAGE_BUCKET_NAME", os.getenv("MINIO_BUCKET", "tapne-local"))
    minio_internal_endpoint = os.getenv(
        "AWS_S3_ENDPOINT_URL",
        os.getenv("MINIO_ENDPOINT", "http://minio:9000"),
    )
    minio_public_endpoint = os.getenv(
        "MEDIA_PUBLIC_ENDPOINT",
        f"http://localhost:{os.getenv('MINIO_PORT', '9000')}",
    ).rstrip("/")
    default_custom_domain = f"{strip_url_scheme(minio_public_endpoint)}/{minio_bucket_name}"
    custom_domain = os.getenv("AWS_S3_CUSTOM_DOMAIN", default_custom_domain).strip().strip("/")
    if not custom_domain:
        custom_domain = default_custom_domain

    default_url_protocol = "https:" if minio_public_endpoint.lower().startswith("https://") else "http:"

    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": os.getenv("AWS_ACCESS_KEY_ID", os.getenv("MINIO_ROOT_USER", "minioadmin")),
            "secret_key": os.getenv("AWS_SECRET_ACCESS_KEY", os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")),
            "bucket_name": minio_bucket_name,
            "endpoint_url": minio_internal_endpoint,
            "region_name": os.getenv("AWS_S3_REGION_NAME", "us-east-1"),
            "default_acl": None,
            "querystring_auth": env_bool("AWS_QUERYSTRING_AUTH", False),
            "addressing_style": os.getenv("AWS_S3_ADDRESSING_STYLE", "path"),
            "signature_version": os.getenv("AWS_S3_SIGNATURE_VERSION", "s3v4"),
            "custom_domain": custom_domain,
            "url_protocol": os.getenv("AWS_S3_URL_PROTOCOL", default_url_protocol),
        },
    }

redis_url = os.getenv("REDIS_URL", "").strip()
cache_backend: dict[str, Any]
if redis_url:
    cache_backend = {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": redis_url,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
else:
    cache_backend = {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}

CACHES: dict[str, dict[str, Any]] = {"default": cache_backend}
AUTH_PASSWORD_VALIDATORS: list[dict[str, Any]] = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "accounts.validators.ComplexityPasswordValidator"},
]

csrf_trusted_origins = os.getenv("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS: list[str] = [item.strip() for item in csrf_trusted_origins.split(",") if item.strip()]
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/accounts/me/"
LOGOUT_REDIRECT_URL = "/"

if env_bool("USE_X_FORWARDED_PROTO", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", False)

# Media upload validation defaults (used by media app, env-overridable).
TAPNE_MEDIA_IMAGE_MAX_MB = max(1, env_int("TAPNE_MEDIA_IMAGE_MAX_MB", 12))
TAPNE_MEDIA_VIDEO_MAX_MB = max(1, env_int("TAPNE_MEDIA_VIDEO_MAX_MB", 100))
TAPNE_MEDIA_ALLOWED_IMAGE_MIME_TYPES = env_csv(
    "TAPNE_MEDIA_ALLOWED_IMAGE_MIME_TYPES",
    "image/jpeg,image/png,image/webp,image/gif",
)
TAPNE_MEDIA_ALLOWED_VIDEO_MIME_TYPES = env_csv(
    "TAPNE_MEDIA_ALLOWED_VIDEO_MIME_TYPES",
    "video/mp4,video/quicktime,video/webm,video/x-m4v",
)
TAPNE_MEDIA_ALLOWED_IMAGE_EXTENSIONS = env_csv(
    "TAPNE_MEDIA_ALLOWED_IMAGE_EXTENSIONS",
    ".jpg,.jpeg,.png,.webp,.gif",
)
TAPNE_MEDIA_ALLOWED_VIDEO_EXTENSIONS = env_csv(
    "TAPNE_MEDIA_ALLOWED_VIDEO_EXTENSIONS",
    ".mp4,.mov,.webm,.m4v",
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TAPNE_PLACEHOLDER_MODE = True
