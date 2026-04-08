#!/usr/bin/env bash
# Bootstraps a production-faithful local Tapne stack with Docker.
# Mac equivalent of infra/setup-faithful-local.ps1
#
# Usage:
#   bash infra/setup-faithful-local.sh
#   bash infra/setup-faithful-local.sh --force-env --verbose
#   bash infra/setup-faithful-local.sh --generate-only
#   bash infra/setup-faithful-local.sh --no-build --infra-only
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

GENERATE_ONLY=0
NO_BUILD=0
FORCE_ENV=0
INFRA_ONLY=0
WEB_IMAGE_REF=""
HEALTH_TIMEOUT=180
AUTO_START_DOCKER=1
DISABLE_BUILD_ATTESTATIONS=1
VERBOSE=0

# ── Colours ───────────────────────────────────────────────────────────────────
CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
step()  { echo ""; echo -e "${CYAN}==> $*${NC}"; }
ok()    { echo -e "${GREEN}[OK] $*${NC}"; }
info()  { echo -e "${YELLOW}[INFO] $*${NC}"; }
die()   { echo -e "${RED}[FAILED] $*${NC}" >&2; exit 1; }

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --generate-only)              GENERATE_ONLY=1;         shift   ;;
    --no-build)                   NO_BUILD=1;               shift   ;;
    --force-env)                  FORCE_ENV=1;              shift   ;;
    --infra-only)                 INFRA_ONLY=1;             shift   ;;
    --web-image-ref)              WEB_IMAGE_REF="$2";       shift 2 ;;
    --health-timeout)             HEALTH_TIMEOUT="$2";      shift 2 ;;
    --no-auto-start-docker)       AUTO_START_DOCKER=0;      shift   ;;
    --no-disable-build-attestations) DISABLE_BUILD_ATTESTATIONS=0; shift ;;
    -v|--verbose)                 VERBOSE=1;                shift   ;;
    -h|--help)
      echo "Usage: $0 [--generate-only] [--no-build] [--force-env] [--infra-only]"
      echo "          [--web-image-ref REF] [--health-timeout SECS] [--no-auto-start-docker] [--verbose]"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

[[ "$VERBOSE" -eq 1 ]] && set -x

# ── Helpers ───────────────────────────────────────────────────────────────────
random_token() {
  local len="${1:-48}"
  LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom 2>/dev/null | head -c "$len" || true
}

read_env_value() {
  local file="$1" name="$2"
  [[ -f "$file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"   # ltrim
    [[ -z "$line" || "$line" == '#'* ]] && continue
    [[ "$line" == export\ * ]] && line="${line#export }"
    local key="${line%%=*}"
    local val="${line#*=}"
    [[ "$key" == "$name" ]] || continue
    val="${val%\"}"  ; val="${val#\"}"
    val="${val%\'}"  ; val="${val#\'}"
    echo "$val"
    return
  done < "$file"
}

# ── Step 1: Docker availability ───────────────────────────────────────────────
step "Checking Docker"

docker_ready() { docker info >/dev/null 2>&1; }

if ! docker_ready; then
  if [[ "$AUTO_START_DOCKER" -eq 1 ]]; then
    info "Docker daemon not reachable. Attempting to start Docker Desktop..."
    open -a Docker 2>/dev/null || true
    for i in $(seq 1 30); do
      sleep 2
      docker_ready && break
      [[ "$i" -eq 30 ]] && die "Docker Desktop did not start within 60 seconds. Start it manually and retry."
    done
  else
    die "Docker daemon is not reachable and --no-auto-start-docker was set."
  fi
fi
ok "Docker daemon is reachable."

if [[ "$DISABLE_BUILD_ATTESTATIONS" -eq 1 ]]; then
  export BUILDX_NO_DEFAULT_ATTESTATIONS=1
fi

# ── Step 2: .env setup ────────────────────────────────────────────────────────
step "Ensuring .env file"
ENV_FILE="$REPO_ROOT/.env"
ENV_TEMPLATE="$REPO_ROOT/.env.example"

if [[ ! -f "$ENV_FILE" || "$FORCE_ENV" -eq 1 ]]; then
  [[ -f "$ENV_TEMPLATE" ]] || die ".env.example template is missing: $ENV_TEMPLATE"
  SECRET_KEY="$(random_token 64)"
  MINIO_PASSWORD="$(random_token 32)"
  sed \
    -e "s/__GENERATE_SECRET_KEY__/$SECRET_KEY/g" \
    -e "s/__GENERATE_MINIO_PASSWORD__/$MINIO_PASSWORD/g" \
    "$ENV_TEMPLATE" > "$ENV_FILE"
  ok "Created .env at $ENV_FILE"
else
  info ".env already exists at $ENV_FILE"
fi

# ── Step 3: Validate required env keys ────────────────────────────────────────
step "Validating required .env keys"
REQUIRED_KEYS=(SECRET_KEY DB_NAME DB_USER DB_PASSWORD DB_HOST DB_PORT
               MINIO_ROOT_USER MINIO_ROOT_PASSWORD MINIO_BUCKET)
MISSING_KEYS=()

for key in "${REQUIRED_KEYS[@]}"; do
  val="$(read_env_value "$ENV_FILE" "$key")"
  [[ -z "$val" ]] && MISSING_KEYS+=("$key")
done

if [[ "${#MISSING_KEYS[@]}" -gt 0 ]]; then
  die "Missing required .env keys: ${MISSING_KEYS[*]}"
fi
ok ".env contains all required keys."

# ── Step 4: Validate required files ───────────────────────────────────────────
step "Validating project files"
REQUIRED_FILES=(manage.py requirements.txt "tapne/settings.py" "tapne/wsgi.py" "infra/docker-compose.yml")
MISSING_FILES=()
for f in "${REQUIRED_FILES[@]}"; do
  [[ -f "$REPO_ROOT/$f" ]] || MISSING_FILES+=("$f")
done
if [[ "${#MISSING_FILES[@]}" -gt 0 ]]; then
  die "Missing required files: ${MISSING_FILES[*]}"
fi
ok "Required project files are present."

[[ "$GENERATE_ONLY" -eq 1 ]] && { ok "Generate-only mode: stopping here."; exit 0; }

# ── Step 5: Resolve web image ref ─────────────────────────────────────────────
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

if [[ -n "$WEB_IMAGE_REF" ]]; then
  export WEB_IMAGE_REF
  info "Using web image ref: $WEB_IMAGE_REF"
fi

# ── Step 6: Start services ────────────────────────────────────────────────────
step "Starting Docker Compose services"

COMPOSE_SERVICES="db minio redis"
[[ "$INFRA_ONLY" -eq 0 ]] && COMPOSE_SERVICES="db minio redis web"

BUILD_FLAG=""
[[ "$NO_BUILD" -eq 0 && "$INFRA_ONLY" -eq 0 ]] && BUILD_FLAG="--build"

cd "$REPO_ROOT"
# shellcheck disable=SC2086
docker compose -f "$COMPOSE_FILE" up -d $BUILD_FLAG $COMPOSE_SERVICES
ok "Containers started."

# ── Step 7: Health check ──────────────────────────────────────────────────────
if [[ "$INFRA_ONLY" -eq 0 ]]; then
  step "Waiting for web service to become healthy (timeout: ${HEALTH_TIMEOUT}s)"

  APP_PORT="$(read_env_value "$ENV_FILE" "APP_PORT")"
  [[ -z "$APP_PORT" ]] && APP_PORT=8000
  HEALTH_URL="http://localhost:${APP_PORT}/health/"

  deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
  while true; do
    code="$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" 2>/dev/null || echo "000")"
    [[ "$code" == "200" ]] && { ok "Health check passed: $HEALTH_URL"; break; }
    now=$(date +%s)
    if [[ $now -ge $deadline ]]; then
      echo ""
      echo "Container logs:" >&2
      docker compose -f "$COMPOSE_FILE" logs --tail=40 web >&2 || true
      die "Service did not become healthy within ${HEALTH_TIMEOUT}s (last HTTP code: $code)"
    fi
    printf '.'
    sleep 3
  done
fi

echo ""
ok "Local stack is running."
echo ""
echo "  Web:   http://localhost:${APP_PORT:-8000}"
echo "  MinIO: http://localhost:9001  (console)"
echo "  DB:    localhost:5432"
echo "  Redis: localhost:6379"
echo ""
echo "Stop with: docker compose -f infra/docker-compose.yml down"
