<#
.SYNOPSIS
  Bootstraps a production-faithful local tapne stack with Docker.

.DESCRIPTION
  This script verifies Docker availability, ensures .env exists, validates
  required environment keys, and starts:
    - Django web container (Cloud Run equivalent)
    - PostgreSQL container (Cloud SQL equivalent)
    - MinIO container (Cloud Storage equivalent)
    - Redis container (cache/queue equivalent)

  Supports PowerShell -Verbose and unix-style --verbose logging.

.PARAMETER GenerateOnly
  Prepares and validates files but does not start containers.

.PARAMETER NoBuild
  Starts containers without rebuilding the web image.

.PARAMETER ForceEnv
  Regenerates .env from .env.example with fresh random secrets.

.PARAMETER InfraOnly
  Starts only infrastructure services (db, minio, redis) and skips web.

.PARAMETER HealthTimeoutSeconds
  Maximum time to wait for service health before failing.

.EXAMPLE
  pwsh -File infra/setup-faithful-local.ps1 --verbose

.EXAMPLE
  pwsh -File infra/setup-faithful-local.ps1 -GenerateOnly -ForceEnv -Verbose
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$GenerateOnly,
    [switch]$NoBuild,
    [switch]$ForceEnv,
    [switch]$InfraOnly,
    [ValidateRange(30, 1800)]
    [int]$HealthTimeoutSeconds = 180,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($ExtraArgs -contains "--verbose") {
    $VerbosePreference = "Continue"
    Write-Verbose "Verbose logging enabled via --verbose."
}

$unsupportedArgs = @($ExtraArgs | Where-Object { -not [string]::IsNullOrWhiteSpace($_) -and $_ -ne "--verbose" })
if ($unsupportedArgs.Count -gt 0) {
    Write-Warning ("Ignoring unsupported argument(s): {0}" -f ($unsupportedArgs -join ", "))
}

Write-Verbose (
    "Run options => GenerateOnly={0}; NoBuild={1}; ForceEnv={2}; InfraOnly={3}; HealthTimeoutSeconds={4}" -f
    $GenerateOnly, $NoBuild, $ForceEnv, $InfraOnly, $HealthTimeoutSeconds
)

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host ("==> {0}" -f $Message) -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host ("[OK] {0}" -f $Message) -ForegroundColor Green
}

function Test-CommandExists {
    param([string]$CommandName)
    return [bool](Get-Command $CommandName -ErrorAction SilentlyContinue)
}

function New-RandomToken {
    param([int]$Length = 48)
    $alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    $bytes = New-Object byte[] $Length
    $builder = New-Object System.Text.StringBuilder
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()

    try {
        $rng.GetBytes($bytes)
        foreach ($byte in $bytes) {
            [void]$builder.Append($alphabet[$byte % $alphabet.Length])
        }
    }
    finally {
        $rng.Dispose()
    }

    return $builder.ToString()
}

function Read-EnvMap {
    param([string]$Path)
    $map = @{}
    foreach ($rawLine in Get-Content -Path $Path) {
        $line = $rawLine.Trim()
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) {
            continue
        }

        $split = $line -split "=", 2
        if ($split.Count -ne 2) {
            continue
        }

        $key = $split[0].Trim()
        $value = $split[1].Trim()
        $map[$key] = $value
    }

    return $map
}

function Convert-ToStringArray {
    param([object]$Value)

    if ($null -eq $Value) {
        return @()
    }

    if ($Value -is [string]) {
        $single = $Value.Trim()
        if ([string]::IsNullOrWhiteSpace($single)) {
            return @()
        }
        return @($single)
    }

    if ($Value -is [System.Collections.IEnumerable]) {
        $items = @()
        foreach ($item in $Value) {
            if ($null -eq $item) {
                continue
            }
            $text = [string]$item
            if ([string]::IsNullOrWhiteSpace($text)) {
                continue
            }
            $items += $text.Trim()
        }
        return $items
    }

    $fallback = [string]$Value
    if ([string]::IsNullOrWhiteSpace($fallback)) {
        return @()
    }
    return @($fallback.Trim())
}

function Assert-RelativeFileManifest {
    param(
        [string]$ProjectRoot,
        [string[]]$RelativePaths,
        [string]$ManifestLabel
    )

    if (-not $RelativePaths -or $RelativePaths.Count -eq 0) {
        Write-Verbose ("No {0} declared in config; skipping manifest check." -f $ManifestLabel)
        return
    }

    Write-Step ("Validating {0}" -f $ManifestLabel)
    $missing = @()
    foreach ($relativePath in $RelativePaths) {
        $fullPath = Join-Path $ProjectRoot $relativePath
        if (-not (Test-Path -Path $fullPath -PathType Leaf)) {
            $missing += $relativePath
            continue
        }

        Write-Verbose ("Found {0}: {1}" -f $ManifestLabel, $relativePath)
    }

    if ($missing.Count -gt 0) {
        throw ("Missing {0}: {1}" -f $ManifestLabel, ($missing -join ", "))
    }

    Write-Ok ("{0} are present." -f $ManifestLabel)
}

function Initialize-EnvFile {
    param(
        [string]$EnvFilePath,
        [string]$EnvTemplatePath,
        [switch]$Force
    )

    if ((Test-Path -Path $EnvFilePath -PathType Leaf) -and -not $Force) {
        Write-Verbose (".env already exists at {0}" -f $EnvFilePath)
        return
    }

    if (-not (Test-Path -Path $EnvTemplatePath -PathType Leaf)) {
        throw (".env template is missing: {0}" -f $EnvTemplatePath)
    }

    Write-Verbose ("Generating .env from template {0}" -f $EnvTemplatePath)
    $content = Get-Content -Path $EnvTemplatePath -Raw
    $secretKey = New-RandomToken -Length 64
    $minioPassword = New-RandomToken -Length 32

    $content = $content.Replace("__GENERATE_SECRET_KEY__", $secretKey)
    $content = $content.Replace("__GENERATE_MINIO_PASSWORD__", $minioPassword)

    Set-Content -Path $EnvFilePath -Value $content -Encoding utf8NoBOM
    Write-Ok ("Created .env at {0}" -f $EnvFilePath)
}

function Assert-RequiredEnvKeys {
    param(
        [string]$EnvFilePath,
        [string[]]$RequiredKeys
    )

    $envMap = Read-EnvMap -Path $EnvFilePath
    $missing = @()
    foreach ($key in $RequiredKeys) {
        if (-not $envMap.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($envMap[$key])) {
            $missing += $key
        }
    }

    if ($missing.Count -gt 0) {
        throw ("Missing required .env keys: {0}" -f ($missing -join ", "))
    }

    Write-Ok ".env contains all required keys."
}

function Set-TextFileIfMissing {
    param(
        [string]$Path,
        [string]$Content,
        [string]$Label
    )

    if (Test-Path -Path $Path -PathType Leaf) {
        Write-Verbose ("{0} already exists at {1}" -f $Label, $Path)
        return $false
    }

    $directoryPath = Split-Path -Parent $Path
    if (-not [string]::IsNullOrWhiteSpace($directoryPath) -and -not (Test-Path -Path $directoryPath -PathType Container)) {
        New-Item -ItemType Directory -Path $directoryPath -Force | Out-Null
        Write-Verbose ("Created directory: {0}" -f $directoryPath)
    }

    Set-Content -Path $Path -Value $Content -Encoding utf8NoBOM
    Write-Ok ("Created placeholder {0}: {1}" -f $Label, $Path)
    return $true
}

function Initialize-PlaceholderDjangoProject {
    param(
        [string]$ProjectRoot,
        [string]$ManagePyPath
    )

    if (Test-Path -Path $ManagePyPath -PathType Leaf) {
        Write-Verbose ("manage.py already exists at {0}" -f $ManagePyPath)
        return
    }

    Write-Step "Creating placeholder Django app bootstrap"

    $tapnePackagePath = Join-Path $ProjectRoot "tapne"
    $placeholderFlagPath = Join-Path $ProjectRoot ".tapne-placeholder-generated"

    $managePyContent = @'
#!/usr/bin/env python
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""
Placeholder manage.py generated by infra/setup-faithful-local.ps1.

Replace this with your real project entrypoint once the application code is available.
"""
from __future__ import annotations

import os
import sys
from typing import Sequence


def main(argv: Sequence[str] | None = None) -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tapne.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django is not available. Install dependencies from requirements.txt first."
        ) from exc
    execute_from_command_line(list(argv or sys.argv))


if __name__ == "__main__":
    main()
'@

    $tapneInitContent = @'
"""
Placeholder tapne package generated for local docker bootstrap.
"""
'@

    $tapneSettingsContent = @'
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
            ]
        },
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
'@

    $tapneUrlsContent = @'
# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest, JsonResponse
from django.urls import URLPattern, URLResolver, path


def health(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok", "service": "tapne-placeholder"})


urlpatterns: list[URLPattern | URLResolver] = [
    path("", health, name="health"),
    path("admin/", admin.site.urls),
]
'@

    $tapneWsgiContent = @'
# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tapne.settings")

application = get_wsgi_application()
'@

    $tapneAsgiContent = @'
# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tapne.settings")

application = get_asgi_application()
'@

    $placeholderNoticeContent = @'
This file indicates that setup-faithful-local.ps1 auto-generated a placeholder Django project.
Replace the placeholder files once the real application source is available:
- manage.py
- tapne/settings.py
- tapne/urls.py
- tapne/wsgi.py
- tapne/asgi.py
'@

    $placeholderFiles = @(
        @{ Path = $ManagePyPath; Content = $managePyContent; Label = "manage.py" },
        @{ Path = (Join-Path $tapnePackagePath "__init__.py"); Content = $tapneInitContent; Label = "tapne package init" },
        @{ Path = (Join-Path $tapnePackagePath "settings.py"); Content = $tapneSettingsContent; Label = "tapne settings" },
        @{ Path = (Join-Path $tapnePackagePath "urls.py"); Content = $tapneUrlsContent; Label = "tapne urls" },
        @{ Path = (Join-Path $tapnePackagePath "wsgi.py"); Content = $tapneWsgiContent; Label = "tapne wsgi" },
        @{ Path = (Join-Path $tapnePackagePath "asgi.py"); Content = $tapneAsgiContent; Label = "tapne asgi" },
        @{ Path = $placeholderFlagPath; Content = $placeholderNoticeContent; Label = "placeholder marker" }
    )

    $createdCount = 0
    foreach ($file in $placeholderFiles) {
        if (Set-TextFileIfMissing -Path $file.Path -Content $file.Content -Label $file.Label) {
            $createdCount += 1
        }
    }

    if ($createdCount -eq 0) {
        Write-Verbose "No placeholder files were created."
    }
    else {
        Write-Ok "Placeholder Django bootstrap created for local stack startup."
    }
}

function Initialize-DockerRuntime {
    Write-Step "Checking Docker installation"

    if (-not (Test-CommandExists -CommandName "docker")) {
        Write-Host "[ACTION REQUIRED] Docker CLI was not found on PATH." -ForegroundColor Yellow
        Write-Host "Please install Docker Desktop for Windows:" -ForegroundColor Yellow
        Write-Host "https://docs.docker.com/desktop/setup/install/windows-install/" -ForegroundColor Yellow
        throw "Docker is required before continuing."
    }

    $dockerVersion = (& docker --version 2>$null) -join "`n"
    if ($LASTEXITCODE -ne 0) {
        throw "Docker CLI exists but did not return version information."
    }
    Write-Verbose ("Docker version: {0}" -f $dockerVersion)

    $script:ComposeCommand = @("docker", "compose")
    try {
        $composeVersion = (& docker compose version 2>$null) -join "`n"
        if ($LASTEXITCODE -ne 0) {
            throw "compose plugin unavailable"
        }
    }
    catch {
        if (Test-CommandExists -CommandName "docker-compose") {
            $script:ComposeCommand = @("docker-compose")
            $composeVersion = (& docker-compose --version 2>$null) -join "`n"
        }
        else {
            Write-Host "[ACTION REQUIRED] Docker Compose is not installed." -ForegroundColor Yellow
            Write-Host "Install Docker Desktop (includes Compose plugin), then rerun this script." -ForegroundColor Yellow
            throw "Docker Compose is required before continuing."
        }
    }
    Write-Verbose ("Compose version: {0}" -f $composeVersion)

    try {
        & docker info *> $null
    }
    catch {
        Write-Host "[ACTION REQUIRED] Docker daemon is not reachable." -ForegroundColor Yellow
        Write-Host "Start Docker Desktop and wait until it shows Running, then rerun this script." -ForegroundColor Yellow
        throw "Docker daemon is not running."
    }

    Write-Ok "Docker is installed and running."
}

function Invoke-Compose {
    param([string[]]$ComposeArgs)
    $exe = $script:ComposeCommand[0]
    $fullArgs = @()
    if ($script:ComposeCommand.Count -gt 1) {
        $fullArgs += $script:ComposeCommand[1..($script:ComposeCommand.Count - 1)]
    }
    if (-not $ComposeArgs -or $ComposeArgs.Count -eq 0) {
        throw "Invoke-Compose called without compose arguments."
    }
    $fullArgs += $ComposeArgs

    Write-Verbose ("Running: {0} {1}" -f $exe, ($fullArgs -join " "))
    & $exe @fullArgs

    if ($LASTEXITCODE -ne 0) {
        throw ("Docker Compose command failed with exit code {0}." -f $LASTEXITCODE)
    }
}

function Get-ComposeOutput {
    param([string[]]$ComposeArgs)

    $exe = $script:ComposeCommand[0]
    $fullArgs = @()
    if ($script:ComposeCommand.Count -gt 1) {
        $fullArgs += $script:ComposeCommand[1..($script:ComposeCommand.Count - 1)]
    }
    if (-not $ComposeArgs -or $ComposeArgs.Count -eq 0) {
        throw "Get-ComposeOutput called without compose arguments."
    }
    $fullArgs += $ComposeArgs

    $output = & $exe @fullArgs
    if ($LASTEXITCODE -ne 0) {
        throw ("Docker Compose command failed with exit code {0}." -f $LASTEXITCODE)
    }

    return @($output)
}

function Wait-ComposeServiceHealthy {
    param(
        [string[]]$ComposeBaseArgs,
        [string]$ServiceName,
        [int]$TimeoutSeconds,
        [int]$PollIntervalSeconds = 3
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $containerIdLines = Get-ComposeOutput -ComposeArgs ($ComposeBaseArgs + @("ps", "-q", $ServiceName))
        $containerId = ($containerIdLines | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Last 1)

        if ([string]::IsNullOrWhiteSpace($containerId)) {
            Write-Verbose ("Service '{0}' has no container id yet." -f $ServiceName)
            Start-Sleep -Seconds $PollIntervalSeconds
            continue
        }

        $healthStatus = (& docker inspect -f "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" $containerId 2>$null) -join ""
        if ($LASTEXITCODE -ne 0) {
            Write-Verbose ("Could not inspect service '{0}' yet." -f $ServiceName)
            Start-Sleep -Seconds $PollIntervalSeconds
            continue
        }

        $healthStatus = $healthStatus.Trim().ToLowerInvariant()
        Write-Verbose ("Service '{0}' status: {1}" -f $ServiceName, $healthStatus)

        if ($healthStatus -eq "healthy" -or $healthStatus -eq "running") {
            return
        }

        if ($healthStatus -in @("unhealthy", "dead", "exited")) {
            Write-Warning ("Service '{0}' reported status '{1}'. Showing logs..." -f $ServiceName, $healthStatus)
            try {
                Invoke-Compose -ComposeArgs ($ComposeBaseArgs + @("logs", "--tail", "80", $ServiceName))
            }
            catch {
                Write-Verbose ("Failed to fetch logs for service '{0}'." -f $ServiceName)
            }
            throw ("Service '{0}' became unhealthy (status: {1})." -f $ServiceName, $healthStatus)
        }

        Start-Sleep -Seconds $PollIntervalSeconds
    }

    throw ("Timed out after {0}s waiting for service '{1}' health." -f $TimeoutSeconds, $ServiceName)
}

Write-Step "Loading local stack configuration"
$scriptDirectory = Split-Path -Parent $PSCommandPath
$projectRoot = (Resolve-Path (Join-Path $scriptDirectory "..")).Path
$configPath = Join-Path $projectRoot "config.json"

if (-not (Test-Path -Path $configPath -PathType Leaf)) {
    throw ("Missing config file: {0}" -f $configPath)
}

$config = Get-Content -Path $configPath -Raw | ConvertFrom-Json
$verboseSwitches = Convert-ToStringArray -Value $config.verbose_support.switches
if ($verboseSwitches.Count -gt 0) {
    Write-Verbose ("Configured verbose switches: {0}" -f ($verboseSwitches -join ", "))
}

Write-Verbose ("Loaded configuration strategy: {0}" -f $config.strategy)
Write-Verbose ("Compose file (relative): {0}" -f $config.local_stack.compose_file)
Write-Verbose ("Dockerfile (relative): {0}" -f $config.local_stack.dockerfile)
Write-Verbose ("Environment template (relative): {0}" -f $config.local_stack.env_template_file)

$composeFilePath = Join-Path $projectRoot $config.local_stack.compose_file
$dockerfilePath = Join-Path $projectRoot $config.local_stack.dockerfile
$envFilePath = Join-Path $projectRoot $config.local_stack.env_file
$envTemplatePath = Join-Path $projectRoot $config.local_stack.env_template_file
$requirementsPath = Join-Path $projectRoot "requirements.txt"
$managePyPath = Join-Path $projectRoot "manage.py"

$requiredFiles = @(
    $configPath,
    $composeFilePath,
    $dockerfilePath,
    $envTemplatePath,
    $requirementsPath
)

foreach ($path in $requiredFiles) {
    if (-not (Test-Path -Path $path -PathType Leaf)) {
        throw ("Required file missing: {0}" -f $path)
    }
    Write-Verbose ("Found required file: {0}" -f $path)
}
Write-Ok "Infrastructure files are present."

$templateAssetManifest = Convert-ToStringArray -Value $config.ui_shared_assets.required_template_files
$staticAssetManifest = Convert-ToStringArray -Value $config.ui_shared_assets.required_static_files
Assert-RelativeFileManifest -ProjectRoot $projectRoot -RelativePaths $templateAssetManifest -ManifestLabel "template asset files"
Assert-RelativeFileManifest -ProjectRoot $projectRoot -RelativePaths $staticAssetManifest -ManifestLabel "static asset files"

Write-Step "Preparing environment file"
Initialize-EnvFile -EnvFilePath $envFilePath -EnvTemplatePath $envTemplatePath -Force:$ForceEnv
Assert-RequiredEnvKeys -EnvFilePath $envFilePath -RequiredKeys $config.required_env_keys

if ($GenerateOnly) {
    Write-Ok "GenerateOnly mode complete. No containers were started."
    exit 0
}

if ($InfraOnly) {
    Write-Verbose "InfraOnly enabled: web service will be skipped."
}
else {
    Initialize-PlaceholderDjangoProject -ProjectRoot $projectRoot -ManagePyPath $managePyPath
}

Initialize-DockerRuntime

$composeBaseArgs = @(
    "--project-directory", $projectRoot,
    "--env-file", $envFilePath,
    "-f", $composeFilePath
)

if ($InfraOnly) {
    Write-Step "InfraOnly cleanup"
    try {
        Invoke-Compose -ComposeArgs ($composeBaseArgs + @("rm", "--stop", "--force", "web"))
    }
    catch {
        Write-Verbose "No web container needed cleanup."
    }
}

Write-Step "Starting local stack"
$upArgs = $composeBaseArgs + @("up", "-d")
if ($NoBuild) {
    $upArgs += "--no-build"
}
else {
    $upArgs += "--build"
}
if ($InfraOnly) {
    $upArgs += @("db", "minio", "minio-init", "redis")
}
Invoke-Compose -ComposeArgs $upArgs

Write-Step "Waiting for service health"
$servicesToWait = @("db", "minio", "redis")
if (-not $InfraOnly) {
    $servicesToWait += "web"
}

foreach ($serviceName in $servicesToWait) {
    Write-Verbose ("Waiting for '{0}' (timeout: {1}s)..." -f $serviceName, $HealthTimeoutSeconds)
    Wait-ComposeServiceHealthy -ComposeBaseArgs $composeBaseArgs -ServiceName $serviceName -TimeoutSeconds $HealthTimeoutSeconds
    Write-Ok ("Service '{0}' is healthy." -f $serviceName)
}

Write-Step "Container status"
if ($InfraOnly) {
    Invoke-Compose -ComposeArgs ($composeBaseArgs + @("ps", "db", "minio", "minio-init", "redis"))
}
else {
    Invoke-Compose -ComposeArgs ($composeBaseArgs + @("ps"))
}

$envMap = Read-EnvMap -Path $envFilePath
$appPort = $envMap["APP_PORT"]
$dbPort = $envMap["DB_HOST_PORT"]
$minioPort = $envMap["MINIO_PORT"]
$minioConsolePort = $envMap["MINIO_CONSOLE_PORT"]
$redisPort = $envMap["REDIS_PORT"]

Write-Step "Stack endpoints"
if (-not $InfraOnly) {
    Write-Host ("Web app:            http://localhost:{0}" -f $appPort)
}
Write-Host ("PostgreSQL:         localhost:{0}" -f $dbPort)
Write-Host ("MinIO API:          http://localhost:{0}" -f $minioPort)
Write-Host ("MinIO Console:      http://localhost:{0}" -f $minioConsolePort)
Write-Host ("Redis:              localhost:{0}" -f $redisPort)
Write-Host ""
Write-Ok "Local production-faithful stack is ready."
