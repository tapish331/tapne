#!/usr/bin/env bash
# Bootstraps a production-faithful local Tapne stack with Docker.
# Mac equivalent of infra/setup-faithful-local.ps1.
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

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
step() { echo ""; printf "${CYAN}==> %s${NC}\n" "$*"; }
ok()   { printf "${GREEN}[OK] %s${NC}\n" "$*"; }
info() { printf "${YELLOW}[INFO] %s${NC}\n" "$*"; }
warn() { printf "${YELLOW}[WARN] %s${NC}\n" "$*" >&2; }
die()  { printf "${RED}[FAILED] %s${NC}\n" "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --generate-only)                  GENERATE_ONLY=1; shift ;;
    --no-build)                       NO_BUILD=1; shift ;;
    --force-env)                      FORCE_ENV=1; shift ;;
    --infra-only)                     INFRA_ONLY=1; shift ;;
    --web-image-ref)                  WEB_IMAGE_REF="$2"; shift 2 ;;
    --health-timeout|--health-timeout-seconds)
                                      HEALTH_TIMEOUT="$2"; shift 2 ;;
    --no-auto-start-docker)           AUTO_START_DOCKER=0; shift ;;
    --auto-start-docker)              AUTO_START_DOCKER=1; shift ;;
    --no-disable-build-attestations)  DISABLE_BUILD_ATTESTATIONS=0; shift ;;
    -v|--verbose)                     VERBOSE=1; shift ;;
    -h|--help)
      echo "Usage: $0 [--generate-only] [--no-build] [--force-env] [--infra-only]"
      echo "          [--web-image-ref REF] [--health-timeout SECS] [--no-auto-start-docker]"
      echo "          [--no-disable-build-attestations] [--verbose]"
      exit 0
      ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[[ "$VERBOSE" -eq 1 ]] && set -x

trim() {
  printf '%s' "$1" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

random_token() {
  local len="${1:-48}"
  LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom 2>/dev/null | head -c "$len" || true
}

read_env_value() {
  local file="$1" name="$2" line key val
  [[ -f "$file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="$(trim "$line")"
    [[ -z "$line" || "$line" == \#* ]] && continue
    case "$line" in export\ *) line="$(trim "${line#export }")" ;; esac
    case "$line" in *=*) ;; *) continue ;; esac
    key="$(trim "${line%%=*}")"
    [[ "$key" == "$name" ]] || continue
    val="$(trim "${line#*=}")"
    if [[ "${#val}" -ge 2 ]]; then
      case "$val" in
        \"*\") val="${val#\"}"; val="${val%\"}" ;;
        \'*\') val="${val#\'}"; val="${val%\'}" ;;
      esac
    fi
    printf '%s\n' "$val"
    return 0
  done < "$file"
}

config_value() {
  local path="$1"
  python3 - "$CONFIG_FILE" "$path" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
value = data
for part in sys.argv[2].split("."):
    value = value[part]
if isinstance(value, list):
    for item in value:
        print(item)
else:
    print(value)
PY
}

config_required_files() {
  python3 - "$CONFIG_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
for item in data.get("ui_shared_assets", {}).get("required_template_files", []):
    print(item)
for item in data.get("ui_shared_assets", {}).get("required_static_files", []):
    print(item)
for app in data.get("django_apps", {}).values():
    for item in app.get("required_files", []):
        print(item)
PY
}

docker_ready() {
  docker info >/dev/null 2>&1
}

ensure_docker() {
  step "Checking Docker installation"
  command -v docker >/dev/null 2>&1 || die "Docker CLI was not found on PATH. Install Docker Desktop for Mac."
  if ! docker compose version >/dev/null 2>&1 && ! command -v docker-compose >/dev/null 2>&1; then
    die "Docker Compose is not installed. Install Docker Desktop, then rerun this script."
  fi
  if ! docker_ready; then
    if [[ "$AUTO_START_DOCKER" -eq 1 ]]; then
      info "Docker daemon is not reachable. Attempting to start Docker Desktop..."
      open -a Docker 2>/dev/null || true
      local i
      for i in $(seq 1 60); do
        sleep 2
        docker_ready && break
      done
    fi
  fi
  docker_ready || die "Docker daemon is not reachable. Start Docker Desktop and rerun this script."
  ok "Docker is installed and running."
}

compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  else
    docker-compose "$@"
  fi
}

wait_service_healthy() {
  local service="$1" deadline container_id status exit_code
  deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
  while true; do
    container_id="$(compose_cmd "${COMPOSE_BASE_ARGS[@]}" ps -q "$service" 2>/dev/null | tail -1 || true)"
    if [[ -n "$container_id" ]]; then
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
      [[ "$VERBOSE" -eq 1 ]] && echo "[verbose] service '$service' status: $status"
      [[ "$status" == "healthy" || "$status" == "running" ]] && { ok "Service '$service' is healthy."; return; }
      if [[ "$status" == "exited" ]]; then
        exit_code="$(docker inspect --format '{{.State.ExitCode}}' "$container_id" 2>/dev/null || true)"
        [[ "$exit_code" == "0" ]] && { ok "Service '$service' completed successfully."; return; }
      fi
      if [[ "$status" == "unhealthy" || "$status" == "exited" || "$status" == "dead" ]]; then
        warn "Service '$service' reported status '$status'. Showing logs..."
        compose_cmd "${COMPOSE_BASE_ARGS[@]}" logs --tail 80 "$service" >&2 || true
        die "Service '$service' failed to become healthy."
      fi
    fi
    [[ "$(date +%s)" -ge "$deadline" ]] && {
      compose_cmd "${COMPOSE_BASE_ARGS[@]}" logs --tail 80 "$service" >&2 || true
      die "Timed out waiting for service '$service' to become healthy."
    }
    printf '.'
    sleep 3
  done
}

step "Loading local stack configuration"
CONFIG_FILE="$REPO_ROOT/config.json"
[[ -f "$CONFIG_FILE" ]] || die "Missing local stack config: $CONFIG_FILE"
command -v python3 >/dev/null 2>&1 || die "python3 is required to read config.json."

COMPOSE_FILE_REL="$(config_value "local_stack.compose_file")"
DOCKERFILE_REL="$(config_value "local_stack.dockerfile")"
ENV_FILE_REL="$(config_value "local_stack.env_file")"
ENV_TEMPLATE_REL="$(config_value "local_stack.env_template_file")"

COMPOSE_FILE="$REPO_ROOT/$COMPOSE_FILE_REL"
DOCKERFILE="$REPO_ROOT/$DOCKERFILE_REL"
ENV_FILE="$REPO_ROOT/$ENV_FILE_REL"
ENV_TEMPLATE="$REPO_ROOT/$ENV_TEMPLATE_REL"

for file in "$CONFIG_FILE" "$COMPOSE_FILE" "$DOCKERFILE" "$ENV_TEMPLATE"; do
  [[ -f "$file" ]] || die "Missing required infrastructure file: $file"
done
ok "Infrastructure files are present."

step "Validating project file manifest"
MISSING_FILES=()
while IFS= read -r rel_path || [[ -n "$rel_path" ]]; do
  [[ -z "$rel_path" ]] && continue
  [[ -f "$REPO_ROOT/$rel_path" ]] || MISSING_FILES+=("$rel_path")
done < <(config_required_files)
for rel_path in manage.py requirements.txt "$DOCKERFILE_REL" "$COMPOSE_FILE_REL"; do
  [[ -f "$REPO_ROOT/$rel_path" ]] || MISSING_FILES+=("$rel_path")
done
if [[ "${#MISSING_FILES[@]}" -gt 0 ]]; then
  die "Missing required files: ${MISSING_FILES[*]}"
fi
ok "Project file manifest is present."

step "Preparing environment file"
if [[ ! -f "$ENV_FILE" || "$FORCE_ENV" -eq 1 ]]; then
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

step "Validating required .env keys"
MISSING_KEYS=()
while IFS= read -r key || [[ -n "$key" ]]; do
  [[ -z "$key" ]] && continue
  value="$(read_env_value "$ENV_FILE" "$key" || true)"
  [[ -z "$value" ]] && MISSING_KEYS+=("$key")
done < <(config_value "required_env_keys")
if [[ "${#MISSING_KEYS[@]}" -gt 0 ]]; then
  die "Missing required .env keys: ${MISSING_KEYS[*]}"
fi
ok ".env contains all required keys."

if [[ "$INFRA_ONLY" -eq 0 ]]; then
  step "Checking built frontend artifact"
  ARTIFACT_INDEX="$REPO_ROOT/artifacts/lovable-production-dist/index.html"
  [[ -f "$ARTIFACT_INDEX" ]] || die "Missing built frontend artifact: $ARTIFACT_INDEX. Run infra/build-lovable-production-frontend.sh before building the web image."
  ok "Built frontend artifact is present."
fi

if [[ "$GENERATE_ONLY" -eq 1 ]]; then
  ok "Generate-only mode complete. No containers were started."
  exit 0
fi

ensure_docker

if [[ "$DISABLE_BUILD_ATTESTATIONS" -eq 1 ]]; then
  export BUILDX_NO_DEFAULT_ATTESTATIONS=1
fi

COMPOSE_BASE_ARGS=(--project-directory "$REPO_ROOT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
if [[ -n "$WEB_IMAGE_REF" ]]; then
  export WEB_IMAGE_REF
  info "Using WEB_IMAGE_REF override: $WEB_IMAGE_REF"
fi

if [[ "$INFRA_ONLY" -eq 1 ]]; then
  step "Infra-only cleanup"
  compose_cmd "${COMPOSE_BASE_ARGS[@]}" rm --stop --force web >/dev/null 2>&1 || true
fi

step "Starting local stack"
UP_ARGS=(up -d)
if [[ "$NO_BUILD" -eq 1 ]]; then
  UP_ARGS+=(--no-build)
elif [[ "$INFRA_ONLY" -eq 0 ]]; then
  UP_ARGS+=(--build)
fi
if compose_cmd "${COMPOSE_BASE_ARGS[@]}" up --help 2>/dev/null | grep -q -- '--wait'; then
  UP_ARGS+=(--wait --wait-timeout "$HEALTH_TIMEOUT")
fi
if [[ "$INFRA_ONLY" -eq 1 ]]; then
  UP_ARGS+=(db minio minio-init redis)
fi
compose_cmd "${COMPOSE_BASE_ARGS[@]}" "${UP_ARGS[@]}"
ok "Containers started."

step "Waiting for service health"
if [[ "$INFRA_ONLY" -eq 1 ]]; then
  for service in db minio redis; do
    wait_service_healthy "$service"
  done
else
  for service in db minio minio-init redis web; do
    wait_service_healthy "$service"
  done
fi

step "Container status"
compose_cmd "${COMPOSE_BASE_ARGS[@]}" ps || true

APP_PORT="$(read_env_value "$ENV_FILE" "APP_PORT" || true)"
DB_PORT="$(read_env_value "$ENV_FILE" "DB_HOST_PORT" || true)"
MINIO_PORT="$(read_env_value "$ENV_FILE" "MINIO_PORT" || true)"
MINIO_CONSOLE_PORT="$(read_env_value "$ENV_FILE" "MINIO_CONSOLE_PORT" || true)"
REDIS_PORT="$(read_env_value "$ENV_FILE" "REDIS_PORT" || true)"

step "Stack endpoints"
[[ "$INFRA_ONLY" -eq 0 ]] && echo "Web app:            http://localhost:${APP_PORT:-8000}"
echo "PostgreSQL:         localhost:${DB_PORT:-5432}"
echo "MinIO API:          http://localhost:${MINIO_PORT:-9000}"
echo "MinIO Console:      http://localhost:${MINIO_CONSOLE_PORT:-9001}"
echo "Redis:              localhost:${REDIS_PORT:-6379}"
echo ""
ok "Local production-faithful stack is ready."
