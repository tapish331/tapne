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
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES: dict[str, dict[str, Any]] = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

storage_backend = os.getenv("STORAGE_BACKEND", "filesystem").strip().lower()
if storage_backend == "minio":
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": os.getenv("AWS_ACCESS_KEY_ID", os.getenv("MINIO_ROOT_USER", "minioadmin")),
            "secret_key": os.getenv("AWS_SECRET_ACCESS_KEY", os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")),
            "bucket_name": os.getenv("AWS_STORAGE_BUCKET_NAME", os.getenv("MINIO_BUCKET", "tapne-local")),
            "endpoint_url": os.getenv("AWS_S3_ENDPOINT_URL", os.getenv("MINIO_ENDPOINT", "http://minio:9000")),
            "region_name": os.getenv("AWS_S3_REGION_NAME", "us-east-1"),
            "default_acl": None,
            "querystring_auth": False,
            "addressing_style": os.getenv("AWS_S3_ADDRESSING_STYLE", "path"),
            "signature_version": os.getenv("AWS_S3_SIGNATURE_VERSION", "s3v4"),
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

csrf_trusted_origins = os.getenv("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS: list[str] = [item.strip() for item in csrf_trusted_origins.split(",") if item.strip()]

if env_bool("USE_X_FORWARDED_PROTO", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", False)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TAPNE_PLACEHOLDER_MODE = True
