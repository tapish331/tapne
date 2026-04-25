#!/usr/bin/env bash
# Provision and deploy Tapne web to Cloud Run (idempotent).
# Mac equivalent of infra/deploy-cloud-run.ps1
#
# Usage:
#   bash infra/deploy-cloud-run.sh
#   bash infra/deploy-cloud-run.sh --project-id tapne-487110 --region asia-south1
#   bash infra/deploy-cloud-run.sh \
#     --domain tapnetravel.com --www-domain www.tapnetravel.com \
#     --smoke-base-url https://tapnetravel.com \
#     --skip-migrations --verbose
#
# What this script does (in order):
#   1.  Preflight: gcloud + docker checks, auth, project set
#   2.  Enable all required GCP APIs
#   3.  Ensure runtime service account + project IAM bindings
#   4.  (optional) Private service networking for Cloud SQL
#   5.  Ensure Cloud SQL instance, database, and user
#   6.  (optional) Ensure Memorystore Redis
#   7.  Ensure Serverless VPC Access connector
#   8.  Ensure GCS bucket + IAM bindings
#   9.  Check GCS dependency in requirements.txt
#  10.  (optional) Build/push image via push-web-image-to-artifact.sh
#  11.  Verify GCS imports in container
#  12.  Upsert secrets in Secret Manager
#  13.  (optional) Run migration Cloud Run Job
#  14.  Deploy Cloud Run web service
#  15.  Bootstrap ALLOWED_HOSTS/CSRF if not yet configured
#  16.  (optional) Run bootstrap_runtime job
#  17.  Post-deploy smoke tests
#  18.  Configure Cloud Monitoring uptime check + alert policy
set -Eeuo pipefail
export CLOUDSDK_COMPONENT_MANAGER_DISABLE_UPDATE_CHECK=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Defaults ──────────────────────────────────────────────────────────────────
PROJECT_ID="tapne-487110"
REGION="asia-south1"
REPOSITORY="tapne"
IMAGE_NAME="tapne-web"
IMAGE_TAG=""
SERVICE_NAME="tapne-web"
SERVICE_ACCOUNT_NAME="tapne-runtime"
CLOUD_SQL_INSTANCE="tapne-pg"
CLOUD_SQL_DATABASE="tapne_db"
CLOUD_SQL_USER="tapne"
CLOUD_SQL_TIER="db-f1-micro"
CLOUD_SQL_STORAGE_GB=10
CLOUD_SQL_STORAGE_TYPE="HDD"
CLOUD_SQL_DATABASE_VERSION="POSTGRES_15"
CLOUD_SQL_BACKUP_START_TIME="03:00"
ENABLE_CLOUD_SQL_BACKUPS=1
ENABLE_CLOUD_SQL_PITR=1
USE_PRIVATE_CLOUD_SQL_IP=1
PRIVATE_SERVICE_RANGE_NAME=""
PRIVATE_SERVICE_RANGE_PREFIX=16
REDIS_INSTANCE="tapne-redis"
REDIS_SIZE_GB=1
ENABLE_REDIS=0
NETWORK="default"
VPC_CONNECTOR="tapne-svpc"
VPC_CONNECTOR_RANGE="10.8.0.0/28"
BUCKET_NAME=""
CLOUD_RUN_CPU=1
CLOUD_RUN_MEMORY="1Gi"
CLOUD_RUN_TIMEOUT=300
CLOUD_RUN_MIN_INSTANCES=0
CLOUD_RUN_MAX_INSTANCES=10
CLOUD_RUN_CONCURRENCY=10
CLOUD_RUN_INGRESS="internal-and-cloud-load-balancing"
WEB_CONCURRENCY=2
GUNICORN_TIMEOUT=120
ALLOW_UNAUTHENTICATED=1
ENABLE_GCS_SIGNED_URLS=1
AUTO_FIX_GCS_DEPENDENCY=1
BUILD_AND_PUSH_IMAGE=1
DISABLE_BUILD_ATTESTATIONS=1
DISABLE_CONTAINER_SCANNING=1
CONFIGURE_MONITORING=1
MONITORING_NOTIFICATION_CHANNELS=""
DJANGO_ALLOWED_HOSTS=""
CSRF_TRUSTED_ORIGINS=""
CANONICAL_HOST=""
GOOGLE_MAPS_API_KEY="${GOOGLE_MAPS_API_KEY:-}"
ENABLE_DEMO_CATALOG=1
SMOKE_BASE_URL=""
SMOKE_HEALTH_PATH="/runtime/health/"
SMOKE_CSS_PATH="/"
SMOKE_JS_PATH="/sitemap.xml"
UPTIME_CHECK_HOST=""
UPTIME_CHECK_PATH="/runtime/health/"
SKIP_MIGRATIONS=0
RUN_BOOTSTRAP_RUNTIME=0
SKIP_SMOKE_TEST=0
VALIDATE_ONLY=0
SKIP_AUTH_LOGIN=0
VERBOSE=0

# ── Colours ───────────────────────────────────────────────────────────────────
CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
step()  { echo ""; echo -e "${CYAN}==> $*${NC}"; }
ok()    { echo -e "${GREEN}[OK] $*${NC}"; }
info()  { echo -e "${YELLOW}[INFO] $*${NC}"; }
warn()  { echo -e "${YELLOW}[WARN] $*${NC}" >&2; }
die()   { echo -e "${RED}[FAILED] $*${NC}" >&2; exit 1; }

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-id)                     PROJECT_ID="$2";                    shift 2 ;;
    --region)                         REGION="$2";                        shift 2 ;;
    --repository)                     REPOSITORY="$2";                    shift 2 ;;
    --image-name)                     IMAGE_NAME="$2";                    shift 2 ;;
    --image-tag)                      IMAGE_TAG="$2";                     shift 2 ;;
    --service-name)                   SERVICE_NAME="$2";                  shift 2 ;;
    --service-account-name)           SERVICE_ACCOUNT_NAME="$2";          shift 2 ;;
    --cloud-sql-instance)             CLOUD_SQL_INSTANCE="$2";            shift 2 ;;
    --cloud-sql-database)             CLOUD_SQL_DATABASE="$2";            shift 2 ;;
    --cloud-sql-user)                 CLOUD_SQL_USER="$2";                shift 2 ;;
    --cloud-sql-tier)                 CLOUD_SQL_TIER="$2";                shift 2 ;;
    --cloud-sql-storage-gb)           CLOUD_SQL_STORAGE_GB="$2";         shift 2 ;;
    --cloud-sql-storage-type)         CLOUD_SQL_STORAGE_TYPE="$2";       shift 2 ;;
    --cloud-sql-database-version)     CLOUD_SQL_DATABASE_VERSION="$2";   shift 2 ;;
    --cloud-sql-backup-start-time)    CLOUD_SQL_BACKUP_START_TIME="$2";  shift 2 ;;
    --no-cloud-sql-backups)           ENABLE_CLOUD_SQL_BACKUPS=0;         shift   ;;
    --no-cloud-sql-pitr)              ENABLE_CLOUD_SQL_PITR=0;            shift   ;;
    --no-private-cloud-sql-ip)        USE_PRIVATE_CLOUD_SQL_IP=0;         shift   ;;
    --private-service-range-name)     PRIVATE_SERVICE_RANGE_NAME="$2";    shift 2 ;;
    --private-service-range-prefix)   PRIVATE_SERVICE_RANGE_PREFIX="$2"; shift 2 ;;
    --redis-instance)                 REDIS_INSTANCE="$2";                shift 2 ;;
    --redis-size-gb)                  REDIS_SIZE_GB="$2";                 shift 2 ;;
    --enable-redis)                   ENABLE_REDIS=1;                     shift   ;;
    --network)                        NETWORK="$2";                       shift 2 ;;
    --vpc-connector)                  VPC_CONNECTOR="$2";                 shift 2 ;;
    --vpc-connector-range)            VPC_CONNECTOR_RANGE="$2";           shift 2 ;;
    --bucket-name)                    BUCKET_NAME="$2";                   shift 2 ;;
    --cloud-run-cpu)                  CLOUD_RUN_CPU="$2";                 shift 2 ;;
    --cloud-run-memory)               CLOUD_RUN_MEMORY="$2";              shift 2 ;;
    --cloud-run-timeout)              CLOUD_RUN_TIMEOUT="$2";             shift 2 ;;
    --cloud-run-min-instances)        CLOUD_RUN_MIN_INSTANCES="$2";       shift 2 ;;
    --cloud-run-max-instances)        CLOUD_RUN_MAX_INSTANCES="$2";       shift 2 ;;
    --cloud-run-concurrency)          CLOUD_RUN_CONCURRENCY="$2";         shift 2 ;;
    --cloud-run-ingress)              CLOUD_RUN_INGRESS="$2";             shift 2 ;;
    --web-concurrency)                WEB_CONCURRENCY="$2";               shift 2 ;;
    --gunicorn-timeout)               GUNICORN_TIMEOUT="$2";              shift 2 ;;
    --no-allow-unauthenticated)       ALLOW_UNAUTHENTICATED=0;            shift   ;;
    --no-gcs-signed-urls)             ENABLE_GCS_SIGNED_URLS=0;           shift   ;;
    --no-auto-fix-gcs-dependency)     AUTO_FIX_GCS_DEPENDENCY=0;          shift   ;;
    --no-build-and-push)              BUILD_AND_PUSH_IMAGE=0;             shift   ;;
    --no-disable-build-attestations)  DISABLE_BUILD_ATTESTATIONS=0;       shift   ;;
    --no-disable-container-scanning)  DISABLE_CONTAINER_SCANNING=0;       shift   ;;
    --no-configure-monitoring)        CONFIGURE_MONITORING=0;             shift   ;;
    --monitoring-notification-channels) MONITORING_NOTIFICATION_CHANNELS="$2"; shift 2 ;;
    --django-allowed-hosts)           DJANGO_ALLOWED_HOSTS="$2";          shift 2 ;;
    --csrf-trusted-origins)           CSRF_TRUSTED_ORIGINS="$2";          shift 2 ;;
    --canonical-host)                 CANONICAL_HOST="$2";                shift 2 ;;
    --google-maps-api-key)            GOOGLE_MAPS_API_KEY="$2";           shift 2 ;;
    --no-demo-catalog)                ENABLE_DEMO_CATALOG=0;              shift   ;;
    --enable-demo-catalog)            ENABLE_DEMO_CATALOG=1;              shift   ;;
    --smoke-base-url)                 SMOKE_BASE_URL="$2";                shift 2 ;;
    --smoke-health-path)              SMOKE_HEALTH_PATH="$2";             shift 2 ;;
    --smoke-css-path)                 SMOKE_CSS_PATH="$2";                shift 2 ;;
    --smoke-js-path)                  SMOKE_JS_PATH="$2";                 shift 2 ;;
    --uptime-check-host)              UPTIME_CHECK_HOST="$2";             shift 2 ;;
    --uptime-check-path)              UPTIME_CHECK_PATH="$2";             shift 2 ;;
    --skip-migrations)                SKIP_MIGRATIONS=1;                  shift   ;;
    --run-bootstrap-runtime)          RUN_BOOTSTRAP_RUNTIME=1;            shift   ;;
    --skip-smoke-test)                SKIP_SMOKE_TEST=1;                  shift   ;;
    --validate-only)                  VALIDATE_ONLY=1;                    shift   ;;
    --skip-auth-login)                SKIP_AUTH_LOGIN=1;                  shift   ;;
    -v|--verbose)                     VERBOSE=1;                          shift   ;;
    -h|--help)
      echo "Usage: $0 [--project-id ID] [--region R] [--domain D] [--www-domain W]"
      echo "          [--smoke-base-url URL] [--skip-migrations] [--skip-smoke-test] [--verbose]"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

[[ "$VERBOSE" -eq 1 ]] && set -x

# ── Derived values ────────────────────────────────────────────────────────────
[[ -z "$IMAGE_TAG" ]]         && IMAGE_TAG="cloudrun-$(date +%Y%m%d%H%M%S)"
[[ -z "$BUCKET_NAME" ]]       && BUCKET_NAME="tapne-${PROJECT_ID}-media"
[[ -z "$PRIVATE_SERVICE_RANGE_NAME" ]] && PRIVATE_SERVICE_RANGE_NAME="google-managed-services-${NETWORK}"

SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
REGISTRY_HOST="${REGION}-docker.pkg.dev"
IMAGE_REF="${REGISTRY_HOST}/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${IMAGE_TAG}"
BUCKET_REF="gs://${BUCKET_NAME}"
REQUIREMENTS_FILE="$REPO_ROOT/requirements.txt"
PUSH_SCRIPT="$SCRIPT_DIR/push-web-image-to-artifact.sh"

SECRET_KEY_NAME="tapne-secret-key"
DATABASE_URL_SECRET="tapne-database-url"
REDIS_URL_SECRET="tapne-redis-url"
GOOGLE_MAPS_SECRET="tapne-google-maps-api-key"

# ── Helpers ───────────────────────────────────────────────────────────────────
random_token() {
  local len="${1:-32}"
  LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom 2>/dev/null | head -c "$len" || true
}

# Read a secret's latest value; returns empty string on failure
secret_get() {
  local name="$1"
  gcloud secrets versions access latest --secret="$name" --project="$PROJECT_ID" 2>/dev/null || true
}

# Create or add version to a secret (idempotent)
secret_set() {
  local name="$1" value="$2"
  local tmp
  tmp="$(mktemp)"
  printf '%s' "$value" > "$tmp"
  if gcloud secrets describe "$name" --project="$PROJECT_ID" >/dev/null 2>&1; then
    local current
    current="$(secret_get "$name" || true)"
    if [[ "$current" == "$value" ]]; then
      info "Secret unchanged, skipping new version: $name"
      rm -f "$tmp"
      return
    fi
    gcloud secrets versions add "$name" \
      --project="$PROJECT_ID" \
      --data-file="$tmp" \
      --quiet
    ok "Updated secret: $name"
  else
    gcloud secrets create "$name" \
      --project="$PROJECT_ID" \
      --replication-policy=automatic \
      --data-file="$tmp" \
      --quiet
    ok "Created secret: $name"
  fi
  rm -f "$tmp"
}

# Wait for a Cloud SQL operation to complete (handles "taking longer than expected")
wait_cloudsql() {
  local instance="$1"
  gcloud sql operations wait \
    --project="$PROJECT_ID" \
    --instance="$instance" \
    --quiet 2>/dev/null || true
}

# Wait until a resource reaches an expected state
wait_for_state() {
  local label="$1" expected="$2" timeout="${3:-900}" sleep_sec="${4:-10}"
  local deadline=$(( $(date +%s) + timeout ))
  while true; do
    local state
    state="$(eval "${WAIT_STATE_CMD}" 2>/dev/null | head -1 | tr -d '[:space:]' || true)"
    [[ "$VERBOSE" -eq 1 ]] && echo "[verbose] $label state: $state"
    if [[ "$state" == "$expected" ]]; then
      ok "$label is $expected"
      return 0
    fi
    now=$(date +%s)
    [[ $now -ge $deadline ]] && die "Timed out waiting for $label to become $expected (current: $state)"
    printf '.'
    sleep "$sleep_sec"
  done
}

# Smoke: HTTP status check with retries
smoke_check() {
  local url="$1" expected_code="${2:-200}" retries="${3:-15}" interval="${4:-4}"
  local code
  for (( i=1; i<=retries; i++ )); do
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$url" 2>/dev/null || echo "000")"
    [[ "$code" == "$expected_code" ]] && { ok "Smoke check passed ($code): $url"; return 0; }
    [[ "$i" -eq "$retries" ]] && die "Smoke check failed after $retries attempts (last HTTP $code): $url"
    printf '.'
    sleep "$interval"
  done
}

# HEAD check (single attempt)
smoke_head() {
  local url="$1"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' -I --max-time 30 "$url" 2>/dev/null || echo "000")"
  [[ "$code" == "200" ]] || die "Smoke HEAD failed ($code): $url"
  ok "Smoke HEAD passed ($code): $url"
}

# Ensure requirement line is present in requirements.txt
ensure_requirement() {
  local line="$1"
  [[ -f "$REQUIREMENTS_FILE" ]] || die "requirements.txt not found: $REQUIREMENTS_FILE"
  if grep -qF "$line" "$REQUIREMENTS_FILE"; then
    ok "Dependency already present: $line"
    return
  fi
  if [[ "$AUTO_FIX_GCS_DEPENDENCY" -eq 1 ]]; then
    echo "$line" >> "$REQUIREMENTS_FILE"
    ok "Added dependency to requirements.txt: $line"
  else
    die "Missing required dependency '$line'. Add it to requirements.txt or use --auto-fix-gcs-dependency."
  fi
}

# Get connection name from DATABASE_URL (postgres://user:pass@/db?host=/cloudsql/CONN_NAME)
sql_connection_name_from_url() {
  local url="$1"
  echo "$url" | grep -oP '(?<=host=/cloudsql/)[^&]+' || true
}

# Extract Cloud SQL instance leaf name from connection name (project:region:instance)
sql_instance_from_connection_name() {
  local conn="$1"
  echo "$conn" | awk -F: '{print $NF}' || true
}

# ── Step 1: Preflight ─────────────────────────────────────────────────────────
step "Preflight checks"
command -v gcloud >/dev/null 2>&1 || die "gcloud CLI not found. Install: https://cloud.google.com/sdk/docs/install"
command -v docker  >/dev/null 2>&1 || die "Docker CLI not found."
gcloud --version >/dev/null 2>&1   || die "gcloud is installed but not functioning."
docker version --format '{{.Server.Version}}' >/dev/null 2>&1 \
  || die "Docker daemon check failed. Is Docker Desktop running?"
ok "gcloud and docker are available."

ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -1 || true)"
if [[ -z "$ACTIVE_ACCOUNT" ]]; then
  if [[ "$SKIP_AUTH_LOGIN" -eq 1 ]]; then
    die "No active gcloud account and --skip-auth-login was set."
  fi
  info "No active gcloud account. Launching interactive login..."
  gcloud auth login
  ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -1 || true)"
fi
[[ -n "$ACTIVE_ACCOUNT" ]] || die "No active gcloud account after login."
ok "Using gcloud account: $ACTIVE_ACCOUNT"

gcloud config set project "$PROJECT_ID" --quiet
gcloud config set run/region "$REGION" --quiet
ok "gcloud project/region configured: $PROJECT_ID / $REGION"

[[ "$VALIDATE_ONLY" -eq 1 ]] && { echo ""; ok "Validate-only mode: preflight passed, no resources changed."; exit 0; }

# ── Step 2: Enable APIs ───────────────────────────────────────────────────────
step "Ensuring required APIs are enabled"
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  redis.googleapis.com \
  vpcaccess.googleapis.com \
  compute.googleapis.com \
  artifactregistry.googleapis.com \
  servicenetworking.googleapis.com \
  iamcredentials.googleapis.com \
  monitoring.googleapis.com \
  apikeys.googleapis.com \
  maps-backend.googleapis.com \
  places-backend.googleapis.com \
  places.googleapis.com \
  --project="$PROJECT_ID" \
  --quiet
ok "Required APIs are enabled."

# ── Step 3: Service account + IAM ─────────────────────────────────────────────
step "Ensuring runtime service account and project IAM bindings"
if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
    --project="$PROJECT_ID" \
    --display-name="Tapne Cloud Run runtime" \
    --quiet
  ok "Created service account: $SERVICE_ACCOUNT_EMAIL"
else
  ok "Service account already exists: $SERVICE_ACCOUNT_EMAIL"
fi

for role in roles/cloudsql.client roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="$role" \
    --quiet >/dev/null
done

gcloud iam service-accounts add-iam-policy-binding "$SERVICE_ACCOUNT_EMAIL" \
  --project="$PROJECT_ID" \
  --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
  --role="roles/iam.serviceAccountTokenCreator" \
  --quiet >/dev/null
ok "Project IAM bindings ensured for Cloud SQL, Secret Manager, and signed URL access."

# ── Step 4: Private service networking (optional) ─────────────────────────────
if [[ "$USE_PRIVATE_CLOUD_SQL_IP" -eq 1 ]]; then
  step "Ensuring private service networking for Cloud SQL"

  if ! gcloud compute addresses describe "$PRIVATE_SERVICE_RANGE_NAME" \
      --project="$PROJECT_ID" --global >/dev/null 2>&1; then
    gcloud compute addresses create "$PRIVATE_SERVICE_RANGE_NAME" \
      --project="$PROJECT_ID" \
      --global \
      --purpose=VPC_PEERING \
      --prefix-length="$PRIVATE_SERVICE_RANGE_PREFIX" \
      --network="$NETWORK" \
      --quiet
    ok "Created private service range: $PRIVATE_SERVICE_RANGE_NAME"
  else
    ok "Private service range already exists: $PRIVATE_SERVICE_RANGE_NAME"
  fi

  PEERING="$(gcloud services vpc-peerings list \
    --project="$PROJECT_ID" \
    --network="$NETWORK" \
    --service=servicenetworking.googleapis.com \
    --format='value(peering)' 2>/dev/null | head -1 || true)"

  if [[ -z "$PEERING" ]]; then
    if gcloud services vpc-peerings connect \
        --project="$PROJECT_ID" \
        --service=servicenetworking.googleapis.com \
        --network="$NETWORK" \
        --ranges="$PRIVATE_SERVICE_RANGE_NAME" 2>&1 | grep -qi "already exists"; then
      gcloud services vpc-peerings update \
        --project="$PROJECT_ID" \
        --service=servicenetworking.googleapis.com \
        --network="$NETWORK" \
        --ranges="$PRIVATE_SERVICE_RANGE_NAME" \
        --quiet
      ok "Private service connection updated."
    else
      ok "Private service connection established."
    fi
  else
    ok "Private service connection already exists for servicenetworking.googleapis.com."
  fi
fi

# ── Step 5: Cloud SQL ─────────────────────────────────────────────────────────
step "Ensuring Cloud SQL Postgres instance / database / user"

# Reuse DB password from existing secret if present
EXISTING_DB_URL="$(secret_get "$DATABASE_URL_SECRET" || true)"
DB_PASSWORD=""
if [[ -n "$EXISTING_DB_URL" ]]; then
  # Extract password from postgresql://user:PASSWORD@/db?host=...
  DB_PASSWORD="$(echo "$EXISTING_DB_URL" | grep -oP '(?<=postgresql://[^:]{1,64}:)[^@]+' | python3 -c 'import sys,urllib.parse; print(urllib.parse.unquote(sys.stdin.read().strip()))' 2>/dev/null || true)"
fi
[[ -z "$DB_PASSWORD" ]] && DB_PASSWORD="$(random_token 28)"

# Check if instance exists
SQL_INSTANCE_EXISTS=0
if gcloud sql instances describe "$CLOUD_SQL_INSTANCE" --project="$PROJECT_ID" >/dev/null 2>&1; then
  SQL_INSTANCE_EXISTS=1
  ok "Cloud SQL instance already exists: $CLOUD_SQL_INSTANCE"
fi

if [[ "$SQL_INSTANCE_EXISTS" -eq 0 ]]; then
  info "Creating Cloud SQL instance: $CLOUD_SQL_INSTANCE"
  CREATE_ARGS=(
    sql instances create "$CLOUD_SQL_INSTANCE"
    --project="$PROJECT_ID"
    --region="$REGION"
    --database-version="$CLOUD_SQL_DATABASE_VERSION"
    --tier="$CLOUD_SQL_TIER"
    --storage-size="$CLOUD_SQL_STORAGE_GB"
    --storage-type="$CLOUD_SQL_STORAGE_TYPE"
    --storage-auto-increase
  )
  if [[ "$USE_PRIVATE_CLOUD_SQL_IP" -eq 1 ]]; then
    CREATE_ARGS+=(--network="$NETWORK" --no-assign-ip)
  else
    CREATE_ARGS+=(--assign-ip)
  fi
  if [[ "$ENABLE_CLOUD_SQL_BACKUPS" -eq 1 ]]; then
    CREATE_ARGS+=(--backup-start-time="$CLOUD_SQL_BACKUP_START_TIME")
  else
    CREATE_ARGS+=(--no-backup)
  fi
  [[ "$ENABLE_CLOUD_SQL_PITR" -eq 1 ]] && CREATE_ARGS+=(--enable-point-in-time-recovery)
  CREATE_ARGS+=(--quiet)
  gcloud "${CREATE_ARGS[@]}" 2>&1 | (grep -v "^$" || true)
  ok "Created Cloud SQL instance: $CLOUD_SQL_INSTANCE"
fi

CLOUD_SQL_CONNECTION_NAME="$(gcloud sql instances describe "$CLOUD_SQL_INSTANCE" \
  --project="$PROJECT_ID" \
  --format='value(connectionName)' 2>/dev/null || true)"
[[ -n "$CLOUD_SQL_CONNECTION_NAME" ]] || die "Could not read Cloud SQL connection name for $CLOUD_SQL_INSTANCE"
ok "Cloud SQL connection: $CLOUD_SQL_CONNECTION_NAME"

# Database
if ! gcloud sql databases list --instance="$CLOUD_SQL_INSTANCE" --project="$PROJECT_ID" \
    --format='value(name)' 2>/dev/null | grep -qx "$CLOUD_SQL_DATABASE"; then
  gcloud sql databases create "$CLOUD_SQL_DATABASE" \
    --instance="$CLOUD_SQL_INSTANCE" --project="$PROJECT_ID" --quiet
  ok "Created database: $CLOUD_SQL_DATABASE"
else
  ok "Database already exists: $CLOUD_SQL_DATABASE"
fi

# User
if gcloud sql users list --instance="$CLOUD_SQL_INSTANCE" --project="$PROJECT_ID" \
    --format='value(name)' 2>/dev/null | grep -qx "$CLOUD_SQL_USER"; then
  gcloud sql users set-password "$CLOUD_SQL_USER" \
    --instance="$CLOUD_SQL_INSTANCE" --project="$PROJECT_ID" \
    --password="$DB_PASSWORD" --quiet
  ok "Updated password for DB user: $CLOUD_SQL_USER"
else
  gcloud sql users create "$CLOUD_SQL_USER" \
    --instance="$CLOUD_SQL_INSTANCE" --project="$PROJECT_ID" \
    --password="$DB_PASSWORD" --quiet
  ok "Created DB user: $CLOUD_SQL_USER"
fi

# ── Step 6: Memorystore Redis (optional) ──────────────────────────────────────
REDIS_HOST=""
REDIS_PORT=""
if [[ "$ENABLE_REDIS" -eq 1 ]]; then
  step "Ensuring Memorystore Redis"
  if ! gcloud redis instances describe "$REDIS_INSTANCE" \
      --project="$PROJECT_ID" --region="$REGION" >/dev/null 2>&1; then
    gcloud redis instances create "$REDIS_INSTANCE" \
      --project="$PROJECT_ID" \
      --region="$REGION" \
      --network="$NETWORK" \
      --size="$REDIS_SIZE_GB" \
      --tier=basic \
      --quiet
    ok "Created Redis instance: $REDIS_INSTANCE"
  else
    ok "Redis instance already exists: $REDIS_INSTANCE"
  fi

  WAIT_STATE_CMD="gcloud redis instances describe $REDIS_INSTANCE --project=$PROJECT_ID --region=$REGION --format='value(state)' 2>/dev/null | head -1 | tr -d '[:space:]'"
  wait_for_state "Redis instance $REDIS_INSTANCE" "READY" 1800 10

  REDIS_HOST="$(gcloud redis instances describe "$REDIS_INSTANCE" --project="$PROJECT_ID" --region="$REGION" --format='value(host)' 2>/dev/null || true)"
  REDIS_PORT="$(gcloud redis instances describe "$REDIS_INSTANCE" --project="$PROJECT_ID" --region="$REGION" --format='value(port)' 2>/dev/null || true)"
  [[ -n "$REDIS_HOST" && -n "$REDIS_PORT" ]] || die "Redis host/port could not be resolved."
  ok "Redis endpoint: ${REDIS_HOST}:${REDIS_PORT}"
else
  info "Skipping Memorystore Redis provisioning because --enable-redis was not set."
fi

# ── Step 7: VPC connector ─────────────────────────────────────────────────────
step "Ensuring Serverless VPC Access connector"
if ! gcloud compute networks vpc-access connectors describe "$VPC_CONNECTOR" \
    --project="$PROJECT_ID" --region="$REGION" >/dev/null 2>&1; then
  gcloud compute networks vpc-access connectors create "$VPC_CONNECTOR" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --network="$NETWORK" \
    --range="$VPC_CONNECTOR_RANGE" \
    --min-instances=2 \
    --max-instances=3 \
    --quiet
  ok "Created VPC connector: $VPC_CONNECTOR"
else
  ok "VPC connector already exists: $VPC_CONNECTOR"
fi

WAIT_STATE_CMD="gcloud compute networks vpc-access connectors describe $VPC_CONNECTOR --project=$PROJECT_ID --region=$REGION --format='value(state)' 2>/dev/null | head -1 | tr -d '[:space:]'"
wait_for_state "VPC connector $VPC_CONNECTOR" "READY" 1200 10

# ── Step 8: GCS bucket + IAM ──────────────────────────────────────────────────
step "Ensuring GCS bucket and IAM"
if ! gcloud storage buckets describe "$BUCKET_REF" --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud storage buckets create "$BUCKET_REF" \
    --project="$PROJECT_ID" \
    --location="$REGION" \
    --uniform-bucket-level-access \
    --public-access-prevention \
    --quiet
  ok "Created bucket: $BUCKET_REF"
else
  ok "Bucket already exists: $BUCKET_REF"
fi

for role in roles/storage.objectUser roles/storage.bucketViewer; do
  gcloud storage buckets add-iam-policy-binding "$BUCKET_REF" \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="$role" \
    --quiet >/dev/null
done

# Remove legacy over-permissive roles if present
for legacy_role in roles/storage.objectAdmin roles/storage.legacyBucketReader; do
  gcloud storage buckets remove-iam-policy-binding "$BUCKET_REF" \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="$legacy_role" \
    --quiet >/dev/null 2>&1 || true
done

ok "Bucket IAM bindings ensured (least-privilege profile)."

# ── Step 9: Verify GCS dependency in requirements.txt ────────────────────────
step "Ensuring GCS dependency in requirements.txt"
ensure_requirement "google-cloud-storage>=2.18,<3.0"

# ── Step 10: Build and push image (optional) ──────────────────────────────────
if [[ "$BUILD_AND_PUSH_IMAGE" -eq 1 ]]; then
  step "Building and pushing image"
  [[ -f "$PUSH_SCRIPT" ]] || die "Missing push script: $PUSH_SCRIPT"

  PUSH_EXTRA_ARGS=()
  [[ "$DISABLE_BUILD_ATTESTATIONS" -eq 0 ]]  && PUSH_EXTRA_ARGS+=(--no-disable-build-attestations)
  [[ "$DISABLE_CONTAINER_SCANNING" -eq 0 ]]  && PUSH_EXTRA_ARGS+=(--no-disable-container-scanning)
  [[ "$SKIP_AUTH_LOGIN" -eq 1 ]]             && PUSH_EXTRA_ARGS+=(--skip-auth-login)
  [[ "$VERBOSE" -eq 1 ]]                     && PUSH_EXTRA_ARGS+=(--verbose)

  bash "$PUSH_SCRIPT" \
    --project-id "$PROJECT_ID" \
    --region "$REGION" \
    --repository "$REPOSITORY" \
    --image-name "$IMAGE_NAME" \
    --image-tag "$IMAGE_TAG" \
    "${PUSH_EXTRA_ARGS[@]+"${PUSH_EXTRA_ARGS[@]}"}"
else
  info "Skipping image build/push. Using existing image: $IMAGE_REF"
fi

# ── Step 11: Verify GCS imports in container ─────────────────────────────────
step "Verifying image can import GCS bindings"
docker run --rm "$IMAGE_REF" \
  python manage.py check --deploy 2>&1 | head -5 || true
docker run --rm "$IMAGE_REF" \
  python -c "import storages.backends.gcloud, google.cloud.storage; print('gcs deps ok')" \
  || die "Image is missing GCS dependencies. Ensure requirements include google-cloud-storage and rebuild."
ok "Image GCS import check passed."

# ── Step 12: Upsert secrets ───────────────────────────────────────────────────
step "Upserting secrets"

EXISTING_SECRET_KEY="$(secret_get "$SECRET_KEY_NAME" || true)"
if [[ -z "$EXISTING_SECRET_KEY" ]]; then
  EXISTING_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
fi
secret_set "$SECRET_KEY_NAME" "$EXISTING_SECRET_KEY"

DATABASE_URL="postgresql://${CLOUD_SQL_USER}:${DB_PASSWORD}@/${CLOUD_SQL_DATABASE}?host=/cloudsql/${CLOUD_SQL_CONNECTION_NAME}"
secret_set "$DATABASE_URL_SECRET" "$DATABASE_URL"

if [[ "$ENABLE_REDIS" -eq 1 ]]; then
  secret_set "$REDIS_URL_SECRET" "redis://${REDIS_HOST}:${REDIS_PORT}/0"
fi

# Google Maps API key: arg > env var > existing secret
RESOLVED_GOOGLE_MAPS_API_KEY=""
if [[ -n "$GOOGLE_MAPS_API_KEY" ]]; then
  RESOLVED_GOOGLE_MAPS_API_KEY="$GOOGLE_MAPS_API_KEY"
  info "Using GOOGLE_MAPS_API_KEY from argument/environment."
else
  EXISTING_MAPS_SECRET="$(secret_get "$GOOGLE_MAPS_SECRET" || true)"
  if [[ -n "$EXISTING_MAPS_SECRET" ]]; then
    RESOLVED_GOOGLE_MAPS_API_KEY="$EXISTING_MAPS_SECRET"
    info "Preserving GOOGLE_MAPS_API_KEY from Secret Manager."
  else
    info "GOOGLE_MAPS_API_KEY not provided and not in Secret Manager. Destination autocomplete will be disabled."
  fi
fi
if [[ -n "$RESOLVED_GOOGLE_MAPS_API_KEY" ]]; then
  secret_set "$GOOGLE_MAPS_SECRET" "$RESOLVED_GOOGLE_MAPS_API_KEY"
fi

# ── Step 13: Build env var / secret maps ──────────────────────────────────────
GCS_QUERYSTRING_AUTH="false"
[[ "$ENABLE_GCS_SIGNED_URLS" -eq 1 ]] && GCS_QUERYSTRING_AUTH="true"

BASE_ENV_ENTRIES=(
  "APP_ENV=prod"
  "DEBUG=false"
  "TAPNE_ENABLE_DEMO_DATA=false"
  "TAPNE_DEMO_CATALOG_VISIBLE=$([[ "$ENABLE_DEMO_CATALOG" -eq 1 ]] && echo true || echo false)"
  "LOVABLE_FRONTEND_REQUIRE_LIVE_DATA=true"
  "LOVABLE_FRONTEND_DIST_DIR=/app/artifacts/lovable-production-dist"
  "WEB_CONCURRENCY=${WEB_CONCURRENCY}"
  "GUNICORN_TIMEOUT=${GUNICORN_TIMEOUT}"
  "STORAGE_BACKEND=gcs"
  "GCS_BUCKET_NAME=${BUCKET_NAME}"
  "GCS_QUERYSTRING_AUTH=${GCS_QUERYSTRING_AUTH}"
  "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
  "USE_X_FORWARDED_PROTO=true"
  "CANONICAL_SCHEME=https"
  "SECURE_SSL_REDIRECT=true"
  "SESSION_COOKIE_SECURE=true"
  "CSRF_COOKIE_SECURE=true"
)
[[ -n "$DJANGO_ALLOWED_HOSTS" ]] && BASE_ENV_ENTRIES+=("DJANGO_ALLOWED_HOSTS=${DJANGO_ALLOWED_HOSTS}")
[[ -n "$CSRF_TRUSTED_ORIGINS" ]] && BASE_ENV_ENTRIES+=("CSRF_TRUSTED_ORIGINS=${CSRF_TRUSTED_ORIGINS}")
if [[ -n "$CANONICAL_HOST" ]]; then
  BASE_ENV_ENTRIES+=("CANONICAL_HOST=${CANONICAL_HOST}" "CANONICAL_HOST_REDIRECT_ENABLED=true")
else
  BASE_ENV_ENTRIES+=("CANONICAL_HOST_REDIRECT_ENABLED=false")
fi

WEB_ENV_ENTRIES=("${BASE_ENV_ENTRIES[@]}" "COLLECTSTATIC_ON_BOOT=true")
JOB_ENV_ENTRIES=("${BASE_ENV_ENTRIES[@]}" "COLLECTSTATIC_ON_BOOT=false")

# Build comma-separated env-vars string with a safe delimiter (~)
build_env_arg() {
  local IFS=$'\n'
  # Join with comma — values shouldn't contain commas
  local result
  result="$(printf '%s,' "$@")"
  echo "${result%,}"
}

WEB_ENV_ARG="$(build_env_arg "${WEB_ENV_ENTRIES[@]}")"
JOB_ENV_ARG="$(build_env_arg "${JOB_ENV_ENTRIES[@]}")"

SECRET_MAP_ENTRIES=(
  "SECRET_KEY=${SECRET_KEY_NAME}:latest"
  "DATABASE_URL=${DATABASE_URL_SECRET}:latest"
)
if [[ "$ENABLE_REDIS" -eq 1 ]]; then
  SECRET_MAP_ENTRIES+=("REDIS_URL=${REDIS_URL_SECRET}:latest")
fi
if [[ -n "$RESOLVED_GOOGLE_MAPS_API_KEY" ]]; then
  SECRET_MAP_ENTRIES+=("GOOGLE_MAPS_API_KEY=${GOOGLE_MAPS_SECRET}:latest")
fi
SECRET_MAP_ARG="$(IFS=','; echo "${SECRET_MAP_ENTRIES[*]}")"

# ── Step 14: Run migration Cloud Run Job (optional) ───────────────────────────
if [[ "$SKIP_MIGRATIONS" -eq 0 ]]; then
  step "Deploying and executing migration job"
  gcloud run jobs deploy tapne-migrate \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --image="$IMAGE_REF" \
    --service-account="$SERVICE_ACCOUNT_EMAIL" \
    --set-cloudsql-instances="$CLOUD_SQL_CONNECTION_NAME" \
    --vpc-connector="$VPC_CONNECTOR" \
    --vpc-egress=private-ranges-only \
    --set-secrets="$SECRET_MAP_ARG" \
    --set-env-vars="$JOB_ENV_ARG" \
    --command=python \
    --args='manage.py,migrate,--noinput' \
    --tasks=1 \
    --max-retries=1 \
    --task-timeout=1800 \
    --quiet

  gcloud run jobs execute tapne-migrate \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --wait
  ok "Migration job completed."
else
  info "Skipping migrations (--skip-migrations)."
fi

if [[ "$ENABLE_DEMO_CATALOG" -eq 1 ]]; then
  step "Deploying and executing demo catalog seed job"
  gcloud run jobs deploy tapne-seed-demo-catalog \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --image="$IMAGE_REF" \
    --service-account="$SERVICE_ACCOUNT_EMAIL" \
    --set-cloudsql-instances="$CLOUD_SQL_CONNECTION_NAME" \
    --vpc-connector="$VPC_CONNECTOR" \
    --vpc-egress=private-ranges-only \
    --set-secrets="$SECRET_MAP_ARG" \
    --set-env-vars="$JOB_ENV_ARG" \
    --command=python \
    --args='manage.py,populate_demo_catalog,--verbose' \
    --tasks=1 \
    --max-retries=1 \
    --task-timeout=1800 \
    --quiet

  gcloud run jobs execute tapne-seed-demo-catalog \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --wait
  ok "Demo catalog seed job completed."
else
  info "Demo catalog mode disabled (--no-demo-catalog). Skipping demo seed job."
fi

# ── Step 15: Deploy Cloud Run web service ─────────────────────────────────────
step "Deploying Cloud Run web service"
DEPLOY_EXTRA_ARGS=()
[[ "$ALLOW_UNAUTHENTICATED" -eq 1 ]] \
  && DEPLOY_EXTRA_ARGS+=(--allow-unauthenticated) \
  || DEPLOY_EXTRA_ARGS+=(--no-allow-unauthenticated)

gcloud run deploy "$SERVICE_NAME" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$IMAGE_REF" \
  --service-account="$SERVICE_ACCOUNT_EMAIL" \
  --port=8080 \
  --cpu="$CLOUD_RUN_CPU" \
  --memory="$CLOUD_RUN_MEMORY" \
  --concurrency="$CLOUD_RUN_CONCURRENCY" \
  --ingress="$CLOUD_RUN_INGRESS" \
  --timeout="$CLOUD_RUN_TIMEOUT" \
  --min-instances="$CLOUD_RUN_MIN_INSTANCES" \
  --max-instances="$CLOUD_RUN_MAX_INSTANCES" \
  --set-cloudsql-instances="$CLOUD_SQL_CONNECTION_NAME" \
  --vpc-connector="$VPC_CONNECTOR" \
  --vpc-egress=private-ranges-only \
  --set-secrets="$SECRET_MAP_ARG" \
  --set-env-vars="$WEB_ENV_ARG" \
  --quiet \
  "${DEPLOY_EXTRA_ARGS[@]}"

SERVICE_URL="$(gcloud run services describe "$SERVICE_NAME" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format='value(status.url)' 2>/dev/null | head -1 | tr -d '[:space:]')"
[[ -n "$SERVICE_URL" ]] || die "Cloud Run service URL is empty."
SERVICE_HOST="$(echo "$SERVICE_URL" | sed 's|https\?://||' | sed 's|/.*||')"
ok "Deployed service URL: $SERVICE_URL"

# ── Step 16: Bootstrap ALLOWED_HOSTS/CSRF if not yet set ──────────────────────
BOOTSTRAP_HOST_CSRF=0
[[ -z "$DJANGO_ALLOWED_HOSTS" && -z "$CSRF_TRUSTED_ORIGINS" ]] && BOOTSTRAP_HOST_CSRF=1

if [[ "$BOOTSTRAP_HOST_CSRF" -eq 1 ]]; then
  step "Bootstrapping DJANGO_ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS from service URL"
  EFFECTIVE_ALLOWED_HOSTS="$SERVICE_HOST"
  EFFECTIVE_CSRF_ORIGINS="https://${SERVICE_HOST}"
  gcloud run services update "$SERVICE_NAME" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --update-env-vars="DJANGO_ALLOWED_HOSTS=${EFFECTIVE_ALLOWED_HOSTS},CSRF_TRUSTED_ORIGINS=${EFFECTIVE_CSRF_ORIGINS}" \
    --quiet
  ok "Bootstrapped host/csrf env vars."
else
  EFFECTIVE_ALLOWED_HOSTS="$DJANGO_ALLOWED_HOSTS"
  EFFECTIVE_CSRF_ORIGINS="$CSRF_TRUSTED_ORIGINS"
  info "Keeping configured DJANGO_ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS."
fi

# ── Step 17: Run bootstrap_runtime job (optional) ────────────────────────────
if [[ "$RUN_BOOTSTRAP_RUNTIME" -eq 1 ]]; then
  step "Deploying and running optional bootstrap_runtime job"
  gcloud run jobs deploy tapne-bootstrap-runtime \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --image="$IMAGE_REF" \
    --service-account="$SERVICE_ACCOUNT_EMAIL" \
    --set-cloudsql-instances="$CLOUD_SQL_CONNECTION_NAME" \
    --vpc-connector="$VPC_CONNECTOR" \
    --vpc-egress=private-ranges-only \
    --set-secrets="$SECRET_MAP_ARG" \
    --set-env-vars="$JOB_ENV_ARG" \
    --command=python \
    --args='manage.py,bootstrap_runtime,--verbose' \
    --tasks=1 \
    --max-retries=1 \
    --task-timeout=1800 \
    --quiet

  gcloud run jobs execute tapne-bootstrap-runtime \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --wait
  ok "bootstrap_runtime job completed."
fi

# ── Step 18: Smoke tests ──────────────────────────────────────────────────────
SMOKE_BASE_RESOLVED="${SMOKE_BASE_URL:-$SERVICE_URL}"
# Validate: if ingress is internal-and-cloud-load-balancing, smoke URL must differ from direct run.app URL
if [[ "$SKIP_SMOKE_TEST" -eq 0 && "$CLOUD_RUN_INGRESS" == "internal-and-cloud-load-balancing" ]]; then
  SMOKE_HOST="$(echo "$SMOKE_BASE_RESOLVED" | sed 's|https\?://||' | sed 's|/.*||')"
  if [[ "$SMOKE_HOST" == "$SERVICE_HOST" ]]; then
    die "CLOUD_RUN_INGRESS is internal-and-cloud-load-balancing but smoke URL resolves to direct Cloud Run host. Set --smoke-base-url to your load balancer URL, or use --skip-smoke-test."
  fi
fi

if [[ "$SKIP_SMOKE_TEST" -eq 0 ]]; then
  step "Running post-deploy smoke tests"
  smoke_check "${SMOKE_BASE_RESOLVED}${SMOKE_HEALTH_PATH}" 200 15 4
  smoke_head  "${SMOKE_BASE_RESOLVED}${SMOKE_CSS_PATH}"
  smoke_head  "${SMOKE_BASE_RESOLVED}${SMOKE_JS_PATH}"
  ok "All smoke tests passed."
else
  info "Skipping smoke tests (--skip-smoke-test)."
fi

# ── Step 19: Cloud Monitoring uptime check ────────────────────────────────────
UPTIME_HOST="${UPTIME_CHECK_HOST}"
if [[ -z "$UPTIME_HOST" ]]; then
  # Infer from smoke URL
  UPTIME_HOST="$(echo "$SMOKE_BASE_RESOLVED" | sed 's|https\?://||' | sed 's|/.*||')"
fi

if [[ "$CONFIGURE_MONITORING" -eq 1 && -n "$UPTIME_HOST" ]]; then
  step "Ensuring Cloud Monitoring uptime check"
  ACCESS_TOKEN="$(gcloud auth print-access-token 2>/dev/null || true)"
  if [[ -z "$ACCESS_TOKEN" ]]; then
    warn "Could not get gcloud access token; skipping uptime check setup."
  else
    UPTIME_DISPLAY="tapne-web uptime ($SERVICE_NAME)"
    EXISTING_CHECK_NAME="$(curl -sf \
      -H "Authorization: Bearer $ACCESS_TOKEN" \
      "https://monitoring.googleapis.com/v3/projects/${PROJECT_ID}/uptimeCheckConfigs?pageSize=100" \
      2>/dev/null | python3 -c "
import sys,json
data=json.load(sys.stdin)
for c in data.get('uptimeCheckConfigs',[]):
    if c.get('displayName')=='${UPTIME_DISPLAY}':
        print(c['name'])
        break
" 2>/dev/null || true)"

    if [[ -z "$EXISTING_CHECK_NAME" ]]; then
      NEW_CHECK="$(curl -sf -X POST \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        "https://monitoring.googleapis.com/v3/projects/${PROJECT_ID}/uptimeCheckConfigs" \
        -d "$(python3 -c "
import json
print(json.dumps({
  'displayName': '${UPTIME_DISPLAY}',
  'period': '60s',
  'timeout': '10s',
  'selectedRegions': ['USA','ASIA_PACIFIC','EUROPE'],
  'monitoredResource': {
    'type': 'uptime_url',
    'labels': {'project_id': '${PROJECT_ID}', 'host': '${UPTIME_HOST}'}
  },
  'httpCheck': {
    'requestMethod': 'GET',
    'useSsl': True,
    'validateSsl': True,
    'path': '${UPTIME_CHECK_PATH}',
    'port': 443
  }
}))")" 2>/dev/null || true)"
      ok "Configured uptime check: $UPTIME_DISPLAY"
    else
      ok "Uptime check already configured: $UPTIME_DISPLAY"
    fi
  fi
else
  info "Skipping monitoring setup (--no-configure-monitoring or no uptime host)."
fi

# ── Deploy summary ─────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}Deploy summary:${NC}"
echo "  Project:        $PROJECT_ID"
echo "  Region:         $REGION"
echo "  Service:        $SERVICE_NAME"
echo "  Image:          $IMAGE_REF"
echo "  Service URL:    $SERVICE_URL"
echo "  SQL Instance:   $CLOUD_SQL_INSTANCE ($CLOUD_SQL_CONNECTION_NAME)"
echo "  Redis:          $([ "$ENABLE_REDIS" -eq 1 ] && echo "${REDIS_HOST}:${REDIS_PORT}" || echo "disabled")"
echo "  Bucket:         $BUCKET_REF"
echo "  VPC Connector:  $VPC_CONNECTOR"
echo "  Allowed Hosts:  $EFFECTIVE_ALLOWED_HOSTS"
echo "  CSRF Origins:   $EFFECTIVE_CSRF_ORIGINS"
echo "  Canonical Host: $CANONICAL_HOST"
echo "  Smoke Base URL: $SMOKE_BASE_RESOLVED"
echo "  Uptime Target:  https://${UPTIME_HOST}${UPTIME_CHECK_PATH}"
echo "  Concurrency:    $CLOUD_RUN_CONCURRENCY"
echo "  Ingress:        $CLOUD_RUN_INGRESS"
echo "  Signed URLs:    $GCS_QUERYSTRING_AUTH"
echo "  SQL Private IP: $([ "$USE_PRIVATE_CLOUD_SQL_IP" -eq 1 ] && echo "true" || echo "false")"
echo ""
ok "Cloud Run deployment workflow completed."
