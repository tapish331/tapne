#!/usr/bin/env bash
set -Eeuo pipefail
shopt -s expand_aliases

SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

IMAGE_REF="tapne-web:cloudrun-check"
DOCKERFILE="infra/Dockerfile.web"
BUILD_CONTEXT="."
ENV_FILE=".env"
BUILD_IMAGE=1
SMOKE_PORT=8080
STARTUP_TIMEOUT=120
STOP_TIMEOUT=10
MAX_IMAGE_SIZE_MB=1200
MAX_LAYER_COUNT=30
SMOKE_USE_DEFAULT_CMD=0  # When set via flag, REQUIRE default CMD (no fallback).
ARTIFACT_IMAGE=""
CLOUD_RUN_SERVICE=""
CLOUD_RUN_REGION=""
DOCKER_CLI="docker"
DOCKER_READY=0
DOCKER_CONFIG_FALLBACK_DIR=""
ORIGINAL_DOCKER_CONFIG=""
ORIGINAL_DOCKER_CONFIG_SET=0

# A self-contained smoke command so checks still run even if the image has no CMD.
SMOKE_COMMAND='python manage.py migrate --noinput && python manage.py collectstatic --noinput && exec gunicorn tapne.wsgi:application --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY:-2} --timeout ${GUNICORN_TIMEOUT:-120} --access-logfile - --error-logfile -'

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
SKIP_COUNT=0

CONTAINER_NAME="tapne-cloudrun-check-$$"
SMOKE_DB_VOLUME="tapne-cloudrun-db-$$"
SMOKE_DB_MOUNT="/var/lib/tapne-smoke"
SMOKE_DATABASE_URL="sqlite:////var/lib/tapne-smoke/tapne.db"
HEALTH_BODY_FILE=""
HEALTH_HTTP_CODE="000"
HEALTH_BODY=""
STARTUP_SECONDS=""
CONTAINER_STARTED=0
CONTAINER_STOPPED=0
RUN_OUTPUT=""

_failed_ids=()
_warn_ids=()
_skipped_ids=()

if [[ -v DOCKER_CONFIG ]]; then
  ORIGINAL_DOCKER_CONFIG="$DOCKER_CONFIG"
  ORIGINAL_DOCKER_CONFIG_SET=1
fi

usage() {
  cat <<EOF
Usage: $SCRIPT_NAME [options]

Cloud Run web image readiness checker.

Options:
  --image <ref>                 Docker image reference to build/check.
  --dockerfile <path>           Dockerfile path (default: infra/Dockerfile.web).
  --context <path>              Docker build context (default: .).
  --env-file <path>             Optional env file for smoke run (default: .env).
  --no-build                    Skip docker build and check existing image only.
  --smoke-port <port>           Host/container port for smoke run (default: 8080).
  --startup-timeout <seconds>   Max seconds to wait for app startup (default: 120).
  --stop-timeout <seconds>      Graceful stop timeout in seconds (default: 10).
  --max-image-size-mb <mb>      Max acceptable image size (default: 1200).
  --max-layer-count <n>         Max acceptable image history rows (default: 30).
  --smoke-use-default-cmd       Require image default CMD/ENTRYPOINT (no fallback smoke command).
  --smoke-command <cmd>         Override smoke startup command.
  --artifact-image <ref>        Artifact Registry tag to validate (optional).
  --service <name>              Cloud Run service name to validate deploy inputs.
  --region <region>             Cloud Run region to validate deploy inputs.
  -h, --help                    Show this help.
EOF
}

log() {
  printf '%s\n' "$*"
}

pass() {
  local id="$1"
  local msg="$2"
  PASS_COUNT=$((PASS_COUNT + 1))
  log "[PASS] $id - $msg"
}

fail() {
  local id="$1"
  local msg="$2"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  _failed_ids+=("$id")
  log "[FAIL] $id - $msg"
}

warn() {
  local id="$1"
  local msg="$2"
  WARN_COUNT=$((WARN_COUNT + 1))
  _warn_ids+=("$id")
  log "[WARN] $id - $msg"
}

skip() {
  local id="$1"
  local msg="$2"
  SKIP_COUNT=$((SKIP_COUNT + 1))
  _skipped_ids+=("$id")
  log "[SKIP] $id - $msg"
}

section() {
  log ""
  log "== $1 =="
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    log "Missing required command: $cmd"
    exit 2
  fi
}

is_wsl() {
  [[ -f "/proc/version" ]] && grep -Eqi '(microsoft|wsl)' /proc/version
}

enable_helper_free_docker_config() {
  if [[ -n "$DOCKER_CONFIG_FALLBACK_DIR" ]]; then
    return 0
  fi

  DOCKER_CONFIG_FALLBACK_DIR="$(mktemp -d)"
  printf '{\n  "auths": {}\n}\n' > "${DOCKER_CONFIG_FALLBACK_DIR}/config.json"
  export DOCKER_CONFIG="$DOCKER_CONFIG_FALLBACK_DIR"
  log "Retrying with helper-free Docker config (WSL credential helper workaround)."
}

docker_cli() {
  (
    set +o pipefail
    "$DOCKER_CLI" "$@"
  )
}

docker_cli_original_config() {
  (
    set +o pipefail
    if [[ "$ORIGINAL_DOCKER_CONFIG_SET" -eq 1 ]]; then
      DOCKER_CONFIG="$ORIGINAL_DOCKER_CONFIG" "$DOCKER_CLI" "$@"
    else
      env -u DOCKER_CONFIG "$DOCKER_CLI" "$@"
    fi
  )
}

docker_probe_original_config() {
  local candidate="$1"
  shift
  (
    set +o pipefail
    if [[ "$ORIGINAL_DOCKER_CONFIG_SET" -eq 1 ]]; then
      DOCKER_CONFIG="$ORIGINAL_DOCKER_CONFIG" "$candidate" "$@"
    else
      env -u DOCKER_CONFIG "$candidate" "$@"
    fi
  )
}

docker_manifest_with_alt_clients() {
  local image_ref="$1"
  local candidate
  local output=""
  local -a candidates=()

  candidates+=("$(command -v docker.exe 2>/dev/null || true)")
  candidates+=("/Docker/host/bin/docker.exe")
  candidates+=("/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe")

  for candidate in "${candidates[@]}"; do
    [[ -n "$candidate" ]] || continue
    output="$(docker_probe_original_config "$candidate" manifest inspect "$image_ref" 2>/dev/null || true)"
    if [[ -n "$output" ]]; then
      printf '%s\n' "$output"
      return 0
    fi
  done

  return 1
}

docker_manifest_via_windows_powershell() {
  local image_ref="$1"
  local powershell_exe

  powershell_exe="$(command -v powershell.exe 2>/dev/null || true)"
  if [[ -z "$powershell_exe" && -e /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe ]]; then
    powershell_exe="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
  fi
  [[ -n "$powershell_exe" ]] || return 1

  if [[ "$ORIGINAL_DOCKER_CONFIG_SET" -eq 1 ]]; then
    DOCKER_CONFIG="$ORIGINAL_DOCKER_CONFIG" "$powershell_exe" -NoProfile -Command "docker manifest inspect '$image_ref'" 2>/dev/null | tr -d '\r'
  else
    env -u DOCKER_CONFIG "$powershell_exe" -NoProfile -Command "docker manifest inspect '$image_ref'" 2>/dev/null | tr -d '\r'
  fi
}

artifact_manifest_with_gcloud_token() {
  local image_ref="$1"
  local registry
  local rest
  local image_path
  local manifest_ref
  local token
  local manifest_url
  local cmd_exe
  local powershell_exe

  [[ "$image_ref" == */* ]] || return 1

  registry="${image_ref%%/*}"
  rest="${image_ref#*/}"

  if [[ "$rest" == *"@"* ]]; then
    image_path="${rest%@*}"
    manifest_ref="${rest##*@}"
  elif [[ "$rest" == *:* ]]; then
    image_path="${rest%:*}"
    manifest_ref="${rest##*:}"
  else
    return 1
  fi

  token="$(gcloud auth print-access-token 2>/dev/null | awk 'NF { print; exit }' | tr -d '\r' || true)"
  if [[ -z "$token" ]]; then
    cmd_exe="$(command -v cmd.exe 2>/dev/null || true)"
    if [[ -z "$cmd_exe" && -e /mnt/c/Windows/System32/cmd.exe ]]; then
      cmd_exe="/mnt/c/Windows/System32/cmd.exe"
    fi
    if [[ -n "$cmd_exe" ]]; then
      token="$("$cmd_exe" /C "gcloud auth print-access-token" 2>/dev/null | awk 'NF { print; exit }' | tr -d '\r' || true)"
    fi
  fi
  if [[ -z "$token" ]]; then
    powershell_exe="$(command -v powershell.exe 2>/dev/null || true)"
    if [[ -z "$powershell_exe" && -e /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe ]]; then
      powershell_exe="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    fi
    if [[ -n "$powershell_exe" ]]; then
      token="$("$powershell_exe" -NoProfile -Command "gcloud auth print-access-token" 2>/dev/null | awk 'NF { print; exit }' | tr -d '\r' || true)"
    fi
  fi
  [[ -n "$token" ]] || return 1

  manifest_url="https://${registry}/v2/${image_path}/manifests/${manifest_ref}"
  curl -fsSL \
    -H "Authorization: Bearer ${token}" \
    -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json" \
    "$manifest_url" 2>/dev/null
}

docker_probe() {
  local candidate="$1"
  shift
  (
    set +o pipefail
    "$candidate" "$@"
  )
}

try_docker_cli() {
  local candidate="$1"
  [[ -n "$candidate" ]] || return 1
  if docker_probe "$candidate" info >/dev/null 2>&1; then
    DOCKER_CLI="$candidate"
    DOCKER_READY=1
    return 0
  fi
  return 1
}

require_docker_ready() {
  local docker_path
  local docker_exe_path
  docker_path="$(command -v docker 2>/dev/null || true)"
  docker_exe_path="$(command -v docker.exe 2>/dev/null || true)"

  if try_docker_cli "$docker_path"; then
    return 0
  fi

  if try_docker_cli "$docker_exe_path"; then
    log "Detected unreachable Linux docker client; using docker.exe fallback."
    return 0
  fi

  if try_docker_cli "/Docker/host/bin/docker.exe"; then
    log "Using Docker Desktop host client fallback at /Docker/host/bin/docker.exe."
    return 0
  fi

  if try_docker_cli "/Docker/host/bin/docker"; then
    log "Using Docker Desktop host client fallback at /Docker/host/bin/docker."
    return 0
  fi

  if try_docker_cli "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"; then
    log "Using Docker Desktop client fallback from Program Files."
    return 0
  fi

  if is_wsl; then
    if [[ "$REPO_ROOT" =~ ^/mnt/([a-zA-Z])/(.*)$ ]]; then
      local drive_letter
      local repo_tail
      local git_bash_path
      drive_letter="${BASH_REMATCH[1],,}"
      repo_tail="${BASH_REMATCH[2]}"
      git_bash_path="/${drive_letter}/${repo_tail}"
      log "This appears to be WSL, and Docker Desktop integration for this distro is unavailable."
      log "Run the checker through Git Bash from PowerShell instead:"
      log "  & \"C:\\Program Files\\Git\\bin\\bash.exe\" -lc \"cd ${git_bash_path} && bash infra/check-cloud-run-web-image.sh --image ${IMAGE_REF}\""
    fi
  fi

  log "Docker is installed but not reachable from this shell."
  log "Start Docker Desktop/daemon and ensure this shell can access it, then rerun."
  exit 2
}

HAVE_RG=0
if command -v rg >/dev/null 2>&1; then
  HAVE_RG=1
fi

search_tree() {
  local pattern="$1"
  shift
  if [[ "$HAVE_RG" -eq 1 ]]; then
    rg -n --no-messages "$pattern" "$@" >/dev/null 2>&1
  else
    grep -R -n -E -- "$pattern" "$@" >/dev/null 2>&1
  fi
}

contains_pattern() {
  local file="$1"
  local pattern="$2"
  [[ -f "$file" ]] && grep -Eq -- "$pattern" "$file"
}

json_has_key() {
  local payload="$1"
  local key="$2"
  grep -Eq '"'"$key"'"[[:space:]]*:' <<<"$payload"
}

json_bool_true() {
  local payload="$1"
  local key="$2"
  grep -Eq '"'"$key"'"[[:space:]]*:[[:space:]]*true' <<<"$payload"
}

cleanup() {
  set +e
  if [[ -n "$HEALTH_BODY_FILE" && -f "$HEALTH_BODY_FILE" ]]; then
    rm -f "$HEALTH_BODY_FILE"
  fi

  if [[ -n "$DOCKER_CONFIG_FALLBACK_DIR" && -d "$DOCKER_CONFIG_FALLBACK_DIR" ]]; then
    rm -rf "$DOCKER_CONFIG_FALLBACK_DIR"
  fi

  if [[ "$DOCKER_READY" -eq 1 ]] && docker_cli ps -a --format '{{.Names}}' | grep -Fxq "$CONTAINER_NAME"; then
    docker_cli rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  fi

  if [[ "$DOCKER_READY" -eq 1 && -n "$SMOKE_DB_VOLUME" ]]; then
    if docker_cli volume inspect "$SMOKE_DB_VOLUME" >/dev/null 2>&1; then
      docker_cli volume rm -f "$SMOKE_DB_VOLUME" >/dev/null 2>&1 || true
    fi
  fi
}

trap cleanup EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      IMAGE_REF="$2"
      shift 2
      ;;
    --dockerfile)
      DOCKERFILE="$2"
      shift 2
      ;;
    --context)
      BUILD_CONTEXT="$2"
      shift 2
      ;;
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --no-build)
      BUILD_IMAGE=0
      shift
      ;;
    --smoke-port)
      SMOKE_PORT="$2"
      shift 2
      ;;
    --startup-timeout)
      STARTUP_TIMEOUT="$2"
      shift 2
      ;;
    --stop-timeout)
      STOP_TIMEOUT="$2"
      shift 2
      ;;
    --max-image-size-mb)
      MAX_IMAGE_SIZE_MB="$2"
      shift 2
      ;;
    --max-layer-count)
      MAX_LAYER_COUNT="$2"
      shift 2
      ;;
    --smoke-use-default-cmd)
      SMOKE_USE_DEFAULT_CMD=1   # "Require default CMD/ENTRYPOINT only"
      shift
      ;;
    --smoke-command)
      SMOKE_COMMAND="$2"
      shift 2
      ;;
    --artifact-image)
      ARTIFACT_IMAGE="$2"
      shift 2
      ;;
    --service)
      CLOUD_RUN_SERVICE="$2"
      shift 2
      ;;
    --region)
      CLOUD_RUN_REGION="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      log "Unknown argument: $1"
      usage
      exit 2
      ;;
  esac
done

cd "$REPO_ROOT"

require_cmd grep
require_cmd sed
require_cmd awk
require_cmd curl
require_docker_ready

if [[ "$BUILD_IMAGE" -eq 1 ]]; then
  section "Build"
  log "Building image '$IMAGE_REF' using $DOCKERFILE"
  build_log_file="$(mktemp)"
  build_ok=0
  if docker_cli build -f "$DOCKERFILE" -t "$IMAGE_REF" "$BUILD_CONTEXT" 2>&1 | tee "$build_log_file"; then
    build_ok=1
  fi

  if [[ "$build_ok" -eq 0 ]] && is_wsl && grep -Eqi 'error getting credentials|docker-credential-[^[:space:]]+.*exec format error' "$build_log_file"; then
    enable_helper_free_docker_config
    log "Re-attempting image build after disabling credential helpers for this run."
    if docker_cli build -f "$DOCKERFILE" -t "$IMAGE_REF" "$BUILD_CONTEXT"; then
      build_ok=1
    fi
  fi

  rm -f "$build_log_file"

  if [[ "$build_ok" -eq 1 ]]; then
    pass "B.1" "Image build completed"
  else
    fail "B.1" "Image build failed"
    log ""
    log "Summary: PASS=$PASS_COUNT FAIL=$FAIL_COUNT WARN=$WARN_COUNT SKIP=$SKIP_COUNT"
    exit 1
  fi
else
  section "Build"
  if docker_cli image inspect "$IMAGE_REF" >/dev/null 2>&1; then
    pass "B.1" "Using existing image '$IMAGE_REF'"
  else
    fail "B.1" "Image '$IMAGE_REF' not found and --no-build was set"
    log ""
    log "Summary: PASS=$PASS_COUNT FAIL=$FAIL_COUNT WARN=$WARN_COUNT SKIP=$SKIP_COUNT"
    exit 1
  fi
fi

# Inspect image command contract.
IMAGE_ENTRYPOINT="$(docker_cli image inspect --format '{{json .Config.Entrypoint}}' "$IMAGE_REF")"
IMAGE_CMD="$(docker_cli image inspect --format '{{json .Config.Cmd}}' "$IMAGE_REF")"
IMAGE_RUNTIME_TEXT="${IMAGE_ENTRYPOINT} ${IMAGE_CMD}"
IMAGE_USER="$(docker_cli image inspect --format '{{.Config.User}}' "$IMAGE_REF" 2>/dev/null || echo '')"
SH_BIN="/bin/sh"
HAS_SH=0
SHELL_UTILS_OK=0

if docker_cli run --rm --entrypoint "$SH_BIN" "$IMAGE_REF" -c "true" >/dev/null 2>&1; then
  HAS_SH=1
elif docker_cli run --rm --entrypoint sh "$IMAGE_REF" -c "true" >/dev/null 2>&1; then
  SH_BIN="sh"
  HAS_SH=1
fi

if [[ "$HAS_SH" -eq 1 ]] && docker_cli run --rm --entrypoint "$SH_BIN" "$IMAGE_REF" -c 'for c in chmod mkdir touch rm chown; do command -v "$c" >/dev/null 2>&1 || exit 1; done' >/dev/null 2>&1; then
  SHELL_UTILS_OK=1
fi

section "0) Cloud Run Container Contract"

IMAGE_ARCH="$(docker_cli image inspect --format '{{.Architecture}}' "$IMAGE_REF" 2>/dev/null || echo '')"
IMAGE_OS="$(docker_cli image inspect --format '{{.Os}}' "$IMAGE_REF" 2>/dev/null || echo '')"
if [[ "$IMAGE_ARCH" == "amd64" && "$IMAGE_OS" == "linux" ]]; then
  pass "0.A" "Image platform is linux/amd64 (Cloud Run compatible)"
else
  fail "0.A" "Image platform is '${IMAGE_OS}/${IMAGE_ARCH}'. Cloud Run expects linux/amd64. Use: docker buildx build --platform linux/amd64 ..."
fi

IMAGE_HAS_RUNTIME_CMD=1
if [[ "$IMAGE_RUNTIME_TEXT" == "null null" || "$IMAGE_RUNTIME_TEXT" == "[] []" || "$IMAGE_RUNTIME_TEXT" =~ ^null[[:space:]]\[\]$ || "$IMAGE_RUNTIME_TEXT" =~ ^\[\][[:space:]]null$ ]]; then
  IMAGE_HAS_RUNTIME_CMD=0
  fail "0.1" "Image has no default CMD/ENTRYPOINT; 'docker run <image>' cannot start web server"
else
  pass "0.1" "Image has a default CMD/ENTRYPOINT"
fi

# Heuristic only. Real truth comes from smoke boot.
if [[ "$IMAGE_HAS_RUNTIME_CMD" -eq 1 ]]; then
  if grep -Eqi '0\.0\.0\.0.*\$\{?PORT\}?|\$\{?PORT\}?.*0\.0\.0\.0|0\.0\.0\.0.*PORT|PORT.*0\.0\.0\.0' <<<"$IMAGE_RUNTIME_TEXT"; then
    pass "0.1b" "Runtime command text suggests 0.0.0.0 + \$PORT"
  else
    warn "0.1b" "Runtime command text does not clearly show 0.0.0.0:\$PORT (may still be fine if wrapped)"
  fi
fi

HEALTH_BODY_FILE="$(mktemp)"
START_TS=$SECONDS

run_args=(
  -d
  --name "$CONTAINER_NAME"
  -p "${SMOKE_PORT}:${SMOKE_PORT}"
)
RUN_DATABASE_URL="sqlite:////tmp/tapne.db"
if [[ "$SMOKE_USE_DEFAULT_CMD" -eq 0 && "$HAS_SH" -eq 1 && "$SHELL_UTILS_OK" -eq 1 ]]; then
  run_args+=(-v "${SMOKE_DB_VOLUME}:${SMOKE_DB_MOUNT}")
  RUN_DATABASE_URL="$SMOKE_DATABASE_URL"
fi

if [[ -f "$ENV_FILE" ]]; then
  run_args+=(--env-file "$ENV_FILE")
fi

run_args+=(
  -e "PORT=${SMOKE_PORT}"
  -e "BASE_URL=http://localhost:${SMOKE_PORT}"
  -e "DEBUG=false"
  -e "SECRET_KEY=smoke-secret-key"
  -e "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1"
  -e "DATABASE_URL=${RUN_DATABASE_URL}"
  -e "REDIS_URL="
  -e "STORAGE_BACKEND=filesystem"
)

wait_for_health() {
  local deadline
  deadline=$((START_TS + STARTUP_TIMEOUT))
  HEALTH_HTTP_CODE="000"
  HEALTH_BODY=""
  STARTUP_SECONDS=""

  while (( SECONDS < deadline )); do
    if ! docker_cli ps --format '{{.Names}}' | grep -Fxq "$CONTAINER_NAME"; then
      break
    fi
    HEALTH_HTTP_CODE="$(curl -sS -o "$HEALTH_BODY_FILE" -w '%{http_code}' "http://127.0.0.1:${SMOKE_PORT}/runtime/health/" 2>/dev/null || true)"
    if [[ "$HEALTH_HTTP_CODE" == "200" ]]; then
      HEALTH_BODY="$(cat "$HEALTH_BODY_FILE")"
      STARTUP_SECONDS=$((SECONDS - START_TS))
      return 0
    fi
    sleep 2
  done
  return 1
}

section "Smoke Boot"

SMOKE_DEFAULT_OK=0
SMOKE_FALLBACK_OK=0

if [[ "$HAS_SH" -eq 1 ]]; then
  pass "0.S" "Image includes shell (${SH_BIN}) for prep/fallback diagnostics"
else
  warn "0.S" "Image lacks a usable shell; prep/fallback diagnostics will be skipped"
fi

if [[ "$SMOKE_USE_DEFAULT_CMD" -eq 1 ]]; then
  skip "0.0" "Prep migrate skipped because --smoke-use-default-cmd was set"
elif [[ "$HAS_SH" -eq 1 && "$SHELL_UTILS_OK" -eq 1 ]]; then
  prep_args=(
    --rm
    -v "${SMOKE_DB_VOLUME}:${SMOKE_DB_MOUNT}"
  )
  if [[ -f "$ENV_FILE" ]]; then
    prep_args+=(--env-file "$ENV_FILE")
  fi
  prep_args+=(
    -e "PORT=${SMOKE_PORT}"
    -e "BASE_URL=http://localhost:${SMOKE_PORT}"
    -e "DEBUG=false"
    -e "SECRET_KEY=smoke-secret-key"
    -e "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1"
    -e "DATABASE_URL=${SMOKE_DATABASE_URL}"
    -e "REDIS_URL="
    -e "STORAGE_BACKEND=filesystem"
  )

  WRITE_PROBE_CMD="mkdir -p '${SMOKE_DB_MOUNT}' && touch '${SMOKE_DB_MOUNT}/.tapne-write-test' && rm -f '${SMOKE_DB_MOUNT}/.tapne-write-test'"
  if docker_cli run --rm -v "${SMOKE_DB_VOLUME}:${SMOKE_DB_MOUNT}" --entrypoint "$SH_BIN" "$IMAGE_REF" -c "$WRITE_PROBE_CMD" >/dev/null 2>&1; then
    pass "0.0p" "Smoke DB mount is writable as image user"
  else
    owner_fix_ok=0
    chmod_ok=0
    mount_fix_done=0
    INIT_VOLUME_ERROR=""

    if [[ -n "$IMAGE_USER" && "$IMAGE_USER" != "root" && "$IMAGE_USER" != "0" && "$IMAGE_USER" != "0:0" ]]; then
      if INIT_VOLUME_ERROR="$(docker_cli run --rm --user 0:0 -v "${SMOKE_DB_VOLUME}:${SMOKE_DB_MOUNT}" --entrypoint "$SH_BIN" "$IMAGE_REF" -c "mkdir -p '${SMOKE_DB_MOUNT}' && chown '${IMAGE_USER}' '${SMOKE_DB_MOUNT}'" 2>&1)"; then
        owner_fix_ok=1
      fi
    fi

    if [[ "$owner_fix_ok" -eq 1 ]] && docker_cli run --rm -v "${SMOKE_DB_VOLUME}:${SMOKE_DB_MOUNT}" --entrypoint "$SH_BIN" "$IMAGE_REF" -c "$WRITE_PROBE_CMD" >/dev/null 2>&1; then
      pass "0.0p" "Adjusted smoke volume ownership to make DB mount writable"
      mount_fix_done=1
    elif INIT_VOLUME_ERROR="$(docker_cli run --rm --user 0:0 -v "${SMOKE_DB_VOLUME}:${SMOKE_DB_MOUNT}" --entrypoint "$SH_BIN" "$IMAGE_REF" -c "mkdir -p '${SMOKE_DB_MOUNT}' && chmod 0777 '${SMOKE_DB_MOUNT}'" 2>&1)"; then
      chmod_ok=1
    fi

    if [[ "$mount_fix_done" -eq 1 ]]; then
      :
    elif [[ "$chmod_ok" -eq 1 ]] && docker_cli run --rm -v "${SMOKE_DB_VOLUME}:${SMOKE_DB_MOUNT}" --entrypoint "$SH_BIN" "$IMAGE_REF" -c "$WRITE_PROBE_CMD" >/dev/null 2>&1; then
      pass "0.0p" "Adjusted smoke volume permissions to make DB mount writable"
    else
      warn "0.0p" "Could not ensure smoke DB mount is writable as image user"
      if [[ -n "${INIT_VOLUME_ERROR:-}" ]]; then
        log "$INIT_VOLUME_ERROR"
      fi
    fi
  fi

  if PREP_ERROR="$(docker_cli run --entrypoint "$SH_BIN" "${prep_args[@]}" "$IMAGE_REF" -c "python manage.py migrate --noinput" 2>&1)"; then
    pass "0.0" "Prepared smoke schema via one-off migrate job (smoke convenience, not Cloud Run parity)"
  else
    warn "0.0" "Smoke schema pre-migration failed; default CMD health may fail"
    if [[ -n "$PREP_ERROR" ]]; then
      log "$PREP_ERROR"
    fi
  fi
elif [[ "$HAS_SH" -eq 1 ]]; then
  warn "0.0u" "Shell exists but core utilities are unavailable; cannot prep writable smoke volume"
  warn "0.0" "Prep migrate skipped (no shell utilities). If startup requires DB schema, default CMD may fail here."
else
  warn "0.0" "Prep migrate skipped (no shell). If startup requires DB schema, default CMD may fail here."
fi

# Primary smoke: always try the image default CMD if it exists.
if [[ "$IMAGE_HAS_RUNTIME_CMD" -eq 1 ]]; then
  if RUN_OUTPUT="$(docker_cli run "${run_args[@]}" "$IMAGE_REF" 2>&1)"; then
    CONTAINER_STARTED=1
  else
    CONTAINER_STARTED=0
  fi

  if [[ "$CONTAINER_STARTED" -eq 1 ]] && wait_for_health; then
    SMOKE_DEFAULT_OK=1
    pass "0.2" "Default CMD became healthy within ${STARTUP_SECONDS}s"
  else
    fail "0.2" "Default CMD did not become healthy on /runtime/health/ within ${STARTUP_TIMEOUT}s"
    log "Recent container logs:"
    docker_cli logs --tail 40 "$CONTAINER_NAME" 2>/dev/null || true
  fi
else
  # No default CMD.
  fail "0.2" "Cannot validate default CMD smoke because image has no CMD/ENTRYPOINT"
fi

# Fallback smoke (diagnostics only): run SMOKE_COMMAND so later checks can still run and produce useful output.
if [[ "$SMOKE_DEFAULT_OK" -eq 0 && "$SMOKE_USE_DEFAULT_CMD" -eq 0 ]]; then
  if [[ "$HAS_SH" -eq 1 ]]; then
    docker_cli rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
    START_TS=$SECONDS
    if RUN_OUTPUT="$(docker_cli run --entrypoint "$SH_BIN" "${run_args[@]}" "$IMAGE_REF" -c "$SMOKE_COMMAND" 2>&1)"; then
      CONTAINER_STARTED=1
    else
      CONTAINER_STARTED=0
    fi

    if [[ "$CONTAINER_STARTED" -eq 1 ]] && wait_for_health; then
      SMOKE_FALLBACK_OK=1
      warn "0.2f" "Fallback smoke command became healthy (useful for diagnostics), but DEFAULT CMD still failed"
    else
      warn "0.2f" "Fallback smoke command also failed to become healthy"
      log "Recent container logs:"
      docker_cli logs --tail 40 "$CONTAINER_NAME" 2>/dev/null || true
    fi
  else
    warn "0.2f" "Fallback smoke skipped because image lacks a usable shell and DEFAULT CMD failed"
  fi
fi

if [[ "$CONTAINER_STARTED" -eq 0 ]]; then
  fail "0.2x" "Smoke container failed to start"
  if [[ -n "$RUN_OUTPUT" ]]; then
    log "$RUN_OUTPUT"
  fi
  fail "0.3" "Graceful shutdown could not be validated because container never started"
fi

# PID 1 ownership check (signals/logs)
if [[ "$HEALTH_HTTP_CODE" == "200" ]]; then
  if [[ "$HAS_SH" -eq 1 ]]; then
    PID1_COMM="$(docker_cli exec "$CONTAINER_NAME" "$SH_BIN" -c "cat /proc/1/comm" 2>/dev/null || true)"
    if [[ -z "$PID1_COMM" ]]; then
      PID1_COMM="$(docker_cli exec "$CONTAINER_NAME" "$SH_BIN" -c "ps -o comm= -p 1" 2>/dev/null || true)"
    fi
    if [[ -z "$PID1_COMM" ]]; then
      PID1_COMM="$(docker_cli top "$CONTAINER_NAME" -eo pid,comm,args 2>/dev/null | awk 'NR==2 {print $2}' || true)"
    fi
    if grep -Eqi 'gunicorn|uvicorn|waitress' <<<"$PID1_COMM"; then
      pass "0.B" "PID 1 is app server ($PID1_COMM)"
    elif [[ -z "$PID1_COMM" ]]; then
      warn "0.B" "Unable to determine PID 1 process name"
    else
      PID1_CMDLINE="$(docker_cli exec "$CONTAINER_NAME" "$SH_BIN" -c "tr '\000' ' ' </proc/1/cmdline" 2>/dev/null || true)"
      if [[ -n "$PID1_CMDLINE" ]]; then
        warn "0.B" "PID 1 is '$PID1_COMM' (consider using exec so server is PID 1). cmdline: $PID1_CMDLINE"
      else
        warn "0.B" "PID 1 is '$PID1_COMM' (consider using exec so server is PID 1)"
      fi
    fi
  else
    skip "0.B" "PID 1 inspection skipped (image lacks a usable shell)"
  fi
fi

if contains_pattern "tapne/settings.py" 'os\.getenv\("STORAGE_BACKEND", "filesystem"\)'; then
  if search_tree 'name:[[:space:]]*STORAGE_BACKEND' infra/*.yml infra/*.yaml && \
     search_tree 'value:[[:space:]]*"(gcs|minio)"' infra/*.yml infra/*.yaml; then
    pass "0.4" "Filesystem fallback exists, but infra config sets a non-filesystem backend"
  else
    warn "0.4" "Default storage backend is filesystem; ensure production always sets non-filesystem backend"
  fi
else
  pass "0.4" "Storage backend does not default to local filesystem"
fi

if contains_pattern "infra/docker-compose.yml" '--timeout[[:space:]]+\$+\{GUNICORN_TIMEOUT(:-[0-9]+)?\}' || \
   contains_pattern "infra/Dockerfile.web" '--timeout[[:space:]]+\$+\{GUNICORN_TIMEOUT(:-[0-9]+)?\}'; then
  pass "0.5" "Gunicorn timeout is env-driven (request timeout guard is configurable)"
else
  warn "0.5" "No explicit gunicorn timeout flag found in container startup command"
fi

section "1) Web Server And Entrypoint"

if grep -Eqi 'gunicorn|uvicorn|waitress' <<<"$IMAGE_RUNTIME_TEXT"; then
  if grep -Eqi 'runserver' <<<"$IMAGE_RUNTIME_TEXT"; then
    fail "1.1" "Runtime command mentions runserver"
  else
    pass "1.1" "Runtime command appears to use a production server"
  fi
else
  fail "1.1" "Runtime command does not clearly use gunicorn/uvicorn/waitress"
fi

if grep -Eqi -- '--daemon|daemonize' <<<"$IMAGE_RUNTIME_TEXT"; then
  fail "1.2" "Runtime command daemonizes process; PID 1 should stay attached"
elif [[ "$IMAGE_RUNTIME_TEXT" == "null null" || "$IMAGE_RUNTIME_TEXT" == "[] []" ]]; then
  fail "1.2" "Cannot verify PID 1 behavior because image has no runtime command"
else
  pass "1.2" "Runtime command does not daemonize (PID 1 should own logs/signals)"
fi

if contains_pattern ".env.example" '^APP_PORT=' && contains_pattern ".env.example" '^PORT=' && contains_pattern ".env.example" '^BASE_URL='; then
  pass "1.3" "APP_PORT, PORT, and BASE_URL are all env-configurable"
else
  fail "1.3" "Missing APP_PORT/PORT/BASE_URL split in env template"
fi

section "2) Health Checks"

if contains_pattern "runtime/urls.py" 'path\("health/",[[:space:]]*views\.runtime_health_view' && contains_pattern "runtime/views.py" 'def[[:space:]]+runtime_health_view'; then
  pass "2.1" "Health endpoint route and view are present"
else
  fail "2.1" "Missing /runtime/health/ route or runtime_health_view"
fi

if [[ "$HEALTH_HTTP_CODE" == "200" ]]; then
  if json_has_key "$HEALTH_BODY" "cache_ok" && json_has_key "$HEALTH_BODY" "redis_configured" && json_has_key "$HEALTH_BODY" "broker_configured"; then
    pass "2.1b" "Health response includes dependency fields (cache/redis/broker)"
  else
    fail "2.1b" "Health response missing dependency fields"
  fi

  if json_bool_true "$HEALTH_BODY" "cache_ok"; then
    pass "2.1c" "Health probe reports cache_ok=true"
  else
    warn "2.1c" "Health probe did not report cache_ok=true"
  fi
else
  fail "2.1b" "Health endpoint smoke call failed (HTTP ${HEALTH_HTTP_CODE})"
fi

if search_tree 'startupProbe|--startup-probe' infra/*.yml infra/*.yaml infra/*.ps1 && \
   search_tree '/runtime/health/' infra/*.yml infra/*.yaml infra/*.ps1; then
  pass "2.2" "Startup probe configuration appears wired to /runtime/health/"
else
  fail "2.2" "No Cloud Run startup probe configuration found"
fi

if search_tree 'livenessProbe|--liveness-probe' infra/*.yml infra/*.yaml infra/*.ps1; then
  pass "2.3" "Liveness probe configuration appears in infra assets"
else
  warn "2.3" "No Cloud Run liveness probe wiring found (recommended)"
fi

section "3) Static Files"

if contains_pattern "infra/Dockerfile.web" 'collectstatic' ; then
  pass "3.1" "collectstatic runs during image build"
elif contains_pattern "infra/docker-compose.yml" 'collectstatic' ; then
  warn "3.1" "collectstatic only appears in docker-compose startup command"
else
  fail "3.1" "collectstatic not found in build/startup workflow"
fi

if contains_pattern "tapne/settings.py" 'STATIC_ROOT[[:space:]]*=[[:space:]]*BASE_DIR[[:space:]]*/[[:space:]]*"staticfiles"' && \
   contains_pattern "tapne/settings.py" 'STATICFILES_DIRS[[:space:]]*=[[:space:]]*\[BASE_DIR[[:space:]]*/[[:space:]]*"static"\]' && \
   contains_pattern "tapne/settings.py" 'CompressedManifestStaticFilesStorage'; then
  pass "3.2" "WhiteNoise + manifest static settings are present"
else
  fail "3.2" "Static settings are missing required WhiteNoise manifest configuration"
fi

if [[ "$HEALTH_HTTP_CODE" == "200" ]]; then
  css_code="$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${SMOKE_PORT}/static/css/tapne.css" || true)"
  js_code="$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${SMOKE_PORT}/static/js/tapne-ui.js" || true)"

  if [[ "$css_code" == "200" ]]; then
    pass "3.3a" "GET /static/css/tapne.css returned 200"
  else
    fail "3.3a" "GET /static/css/tapne.css returned ${css_code}"
  fi

  if [[ "$js_code" == "200" ]]; then
    pass "3.3b" "GET /static/js/tapne-ui.js returned 200"
  else
    fail "3.3b" "GET /static/js/tapne-ui.js returned ${js_code}"
  fi
else
  fail "3.3a" "Static smoke tests skipped because app never became healthy"
  fail "3.3b" "Static smoke tests skipped because app never became healthy"
fi

section "4) Media Uploads"

if contains_pattern "tapne/settings.py" 'storage_backend[[:space:]]*=[[:space:]]*os\.getenv\("STORAGE_BACKEND"' && \
   contains_pattern "tapne/settings.py" 'storages\.backends\.s3\.S3Storage'; then
  pass "4.1" "Media storage backend is env-driven with object-storage path"
else
  fail "4.1" "Media storage backend is not clearly env-driven for object storage"
fi

if contains_pattern ".env.example" '^AWS_S3_ENDPOINT_URL=http://minio:9000' && \
   contains_pattern ".env.example" '^MEDIA_PUBLIC_ENDPOINT=http://localhost:' && \
   contains_pattern "tapne/settings.py" 'AWS_S3_ENDPOINT_URL' && \
   contains_pattern "tapne/settings.py" 'MEDIA_PUBLIC_ENDPOINT'; then
  pass "4.2" "MinIO internal endpoint and browser-facing media endpoint split is configured"
else
  fail "4.2" "MinIO endpoint split (internal SDK vs browser endpoint) is incomplete"
fi

if contains_pattern "tapne/settings.py" 'storage_backend[[:space:]]*==[[:space:]]*\"gcs\"|storage_backend[[:space:]]*==[[:space:]]*'\''gcs'\''' || \
   contains_pattern "tapne/settings.py" 'storages\.backends\.gcloud|GoogleCloudStorage'; then
  pass "4.3" "Config hooks for GCS storage backend are present"
else
  fail "4.3" "No explicit GCS storage backend switch found"
fi

section "5) Database And Migrations"

# Guard: never bake migrate into the web runtime CMD (autoscaling stampede risk)
if grep -Eqi 'manage\.py[[:space:]]+migrate' <<<"$IMAGE_RUNTIME_TEXT"; then
  fail "5.0" "Image runtime CMD/ENTRYPOINT includes 'manage.py migrate' (move migrations to a job/release step)"
else
  pass "5.0" "Image runtime CMD does not run migrations"
fi

if contains_pattern "tapne/settings.py" 'os\.getenv\("DATABASE_URL"\)' && contains_pattern "tapne/settings.py" 'default_database_url'; then
  pass "5.1" "DATABASE_URL is env-driven with computed fallback"
else
  fail "5.1" "DATABASE_URL handling is missing or not env-driven"
fi

if contains_pattern "infra/docker-compose.yml" 'manage\.py migrate'; then
  if contains_pattern "infra/docker-compose.yml" 'RUN_MIGRATIONS'; then
    pass "5.2" "Migrations are startup-gated by RUN_MIGRATIONS"
  else
    fail "5.2" "Web startup command always runs migrations (not gated)"
  fi
else
  pass "5.2" "No unconditional migrate in web startup command"
fi

section "6) Redis, Cache, Background Work"

if contains_pattern "tapne/settings.py" 'redis_url[[:space:]]*=[[:space:]]*os\.getenv\("REDIS_URL"' && \
   contains_pattern "runtime/models.py" '"cache_ok"' && \
   contains_pattern "runtime/models.py" '"redis_configured"'; then
  pass "6.1" "REDIS_URL drives cache behavior and health reports cache/redis status"
else
  fail "6.1" "REDIS_URL/cache health integration is incomplete"
fi

if contains_pattern ".env.example" '^REDIS_URL='; then
  pass "6.2" "REDIS_URL is exposed in env template"
else
  fail "6.2" "REDIS_URL missing from env template"
fi

if contains_pattern "runtime/models.py" 'os\.getenv\("CELERY_BROKER_URL"' && contains_pattern ".env.example" '^CELERY_BROKER_URL='; then
  pass "6.3" "Broker mode is env-driven via CELERY_BROKER_URL"
else
  fail "6.3" "CELERY_BROKER_URL wiring is missing"
fi

section "7) Configuration Discipline"

if contains_pattern "tapne/settings.py" 'os\.getenv\("SECRET_KEY", "dev-placeholder-secret"\)' && \
   contains_pattern "tapne/settings.py" 'tapne_password' && \
   contains_pattern "tapne/settings.py" 'minioadmin'; then
  warn "7.1" "Development defaults include hardcoded placeholder values; ensure production overrides all of them"
else
  pass "7.1" "No obvious hardcoded default credentials in settings"
fi

if contains_pattern "tapne/settings.py" 'os\.getenv' && contains_pattern "config.json" '"strategy"[[:space:]]*:[[:space:]]*"faithful-to-production"'; then
  pass "7.2" "Project strategy and settings are env-driven for local/prod parity"
else
  fail "7.2" "Could not validate env-only local/prod split strategy"
fi

section "8) Cloud Run Deployment Specifics"

IMAGE_SIZE_BYTES="$(docker_cli image inspect --format '{{.Size}}' "$IMAGE_REF" 2>/dev/null || echo 0)"
IMAGE_SIZE_MB=$(( (IMAGE_SIZE_BYTES + 1048575) / 1048576 ))
LAYER_COUNT="$(docker_cli history --format '{{.ID}}' "$IMAGE_REF" 2>/dev/null | wc -l | tr -d ' ')"

if [[ "$IMAGE_SIZE_MB" -le "$MAX_IMAGE_SIZE_MB" ]]; then
  pass "8.1a" "Image size ${IMAGE_SIZE_MB}MB is within limit (${MAX_IMAGE_SIZE_MB}MB)"
else
  fail "8.1a" "Image size ${IMAGE_SIZE_MB}MB exceeds limit (${MAX_IMAGE_SIZE_MB}MB)"
fi

if [[ "$LAYER_COUNT" -le "$MAX_LAYER_COUNT" ]]; then
  pass "8.1b" "Image layer count ${LAYER_COUNT} is within limit (${MAX_LAYER_COUNT})"
else
  warn "8.1b" "Image layer count ${LAYER_COUNT} exceeds limit (${MAX_LAYER_COUNT})"
fi

if [[ -n "$ARTIFACT_IMAGE" ]]; then
  if [[ "$ARTIFACT_IMAGE" =~ -docker\.pkg\.dev/ ]]; then
    if docker_cli tag "$IMAGE_REF" "$ARTIFACT_IMAGE" >/dev/null 2>&1; then
      pass "8.2a" "Artifact Registry image tag format looks valid"
    else
      fail "8.2a" "Could not tag image for Artifact Registry"
    fi
  else
    fail "8.2a" "Artifact image does not look like an Artifact Registry reference"
  fi

  if command -v gcloud >/dev/null 2>&1; then
    pass "8.2b" "gcloud CLI is installed"
  else
    fail "8.2b" "gcloud CLI is not installed"
  fi

  if docker_cli manifest --help >/dev/null 2>&1; then
    ARTIFACT_REPO_REF="$ARTIFACT_IMAGE"
    if [[ "$ARTIFACT_REPO_REF" == *"@"* ]]; then
      ARTIFACT_REPO_REF="${ARTIFACT_REPO_REF%@*}"
    elif [[ "$ARTIFACT_REPO_REF" == */*:* ]]; then
      ARTIFACT_REPO_REF="${ARTIFACT_REPO_REF%:*}"
    fi
    ARTIFACT_MANIFEST_JSON="$(docker_cli manifest inspect "$ARTIFACT_IMAGE" 2>/dev/null || true)"
    if [[ -z "$ARTIFACT_MANIFEST_JSON" && -n "$DOCKER_CONFIG_FALLBACK_DIR" ]]; then
      ARTIFACT_MANIFEST_JSON="$(docker_cli_original_config manifest inspect "$ARTIFACT_IMAGE" 2>/dev/null || true)"
    fi
    if [[ -z "$ARTIFACT_MANIFEST_JSON" ]]; then
      ARTIFACT_MANIFEST_JSON="$(docker_manifest_with_alt_clients "$ARTIFACT_IMAGE" || true)"
    fi
    if [[ -z "$ARTIFACT_MANIFEST_JSON" ]]; then
      ARTIFACT_MANIFEST_JSON="$(docker_manifest_via_windows_powershell "$ARTIFACT_IMAGE" || true)"
    fi
    if [[ -z "$ARTIFACT_MANIFEST_JSON" ]]; then
      ARTIFACT_MANIFEST_JSON="$(artifact_manifest_with_gcloud_token "$ARTIFACT_IMAGE" || true)"
    fi
    if [[ -z "$ARTIFACT_MANIFEST_JSON" ]]; then
      LOCAL_ARTIFACT_REPODIGESTS="$(docker_cli image inspect --format '{{json .RepoDigests}}' "$ARTIFACT_IMAGE" 2>/dev/null || true)"
      LOCAL_ARTIFACT_ARCH="$(docker_cli image inspect --format '{{.Architecture}}' "$ARTIFACT_IMAGE" 2>/dev/null || true)"
      LOCAL_ARTIFACT_OS="$(docker_cli image inspect --format '{{.Os}}' "$ARTIFACT_IMAGE" 2>/dev/null || true)"
      if grep -Fq "\"${ARTIFACT_REPO_REF}@sha256:" <<<"$LOCAL_ARTIFACT_REPODIGESTS" && [[ "$LOCAL_ARTIFACT_ARCH" == "amd64" && "$LOCAL_ARTIFACT_OS" == "linux" ]]; then
        pass "8.2d" "Registry manifest query was unavailable in this shell, but local artifact RepoDigest is present and resolves to linux/amd64"
      else
        warn "8.2d" "Could not inspect artifact manifest for linux/amd64 (push/auth may be required)"
      fi
    elif grep -Eq '"manifests"[[:space:]]*:' <<<"$ARTIFACT_MANIFEST_JSON"; then
      if grep -Eq '"os"[[:space:]]*:[[:space:]]*"linux"' <<<"$ARTIFACT_MANIFEST_JSON" && \
         grep -Eq '"architecture"[[:space:]]*:[[:space:]]*"amd64"' <<<"$ARTIFACT_MANIFEST_JSON"; then
        pass "8.2d" "Artifact manifest list includes linux/amd64"
      else
        fail "8.2d" "Artifact manifest list does not include linux/amd64"
      fi
    elif grep -Eq '"os"[[:space:]]*:[[:space:]]*"linux"' <<<"$ARTIFACT_MANIFEST_JSON" && \
         grep -Eq '"architecture"[[:space:]]*:[[:space:]]*"amd64"' <<<"$ARTIFACT_MANIFEST_JSON"; then
      pass "8.2d" "Artifact manifest resolves to linux/amd64"
    else
      warn "8.2d" "Artifact manifest inspected, but linux/amd64 could not be confirmed"
    fi
  else
    warn "8.2d" "docker manifest subcommand not available; cannot verify linux/amd64 in registry manifest"
  fi

  if [[ -n "$CLOUD_RUN_SERVICE" && -n "$CLOUD_RUN_REGION" ]]; then
    pass "8.2c" "Cloud Run deploy inputs provided (service + region)"
  else
    warn "8.2c" "Service/region not supplied; deploy command cannot be fully validated"
  fi
else
  skip "8.2" "Artifact Registry/deploy checks skipped (pass --artifact-image [--service --region] to verify)"
fi

if contains_pattern "tapne/settings.py" 'SECURE_PROXY_SSL_HEADER' && \
   ( contains_pattern "tapne/settings.py" 'USE_X_FORWARDED_HOST' || contains_pattern "tapne/settings.py" 'CSRF_TRUSTED_ORIGINS' ); then
  pass "8.3" "Proxy/TLS handling appears present (SECURE_PROXY_SSL_HEADER + host/csrf)"
else
  warn "8.3" "Could not confirm proxy/TLS settings (check SECURE_PROXY_SSL_HEADER + USE_X_FORWARDED_HOST/CSRF_TRUSTED_ORIGINS)"
fi

if [[ -z "$IMAGE_USER" || "$IMAGE_USER" == "root" || "$IMAGE_USER" == "0" || "$IMAGE_USER" == "0:0" ]]; then
  warn "8.4" "Image default user is root-like ('${IMAGE_USER:-<empty>}'); consider running as non-root"
else
  pass "8.4" "Image default user is non-root (${IMAGE_USER})"
fi

section "9) Cloud Run-Style Smoke"

if [[ "$HEALTH_HTTP_CODE" == "200" ]]; then
  pass "9.1" "curl /runtime/health/ returned 200 in Cloud Run-style smoke run"
else
  fail "9.1" "curl /runtime/health/ failed in Cloud Run-style smoke run (HTTP ${HEALTH_HTTP_CODE})"
fi

if [[ "$HEALTH_HTTP_CODE" == "200" ]]; then
  css_head_code="$(curl -sS -I -o /dev/null -w '%{http_code}' "http://127.0.0.1:${SMOKE_PORT}/static/css/tapne.css" || true)"
  if [[ "$css_head_code" == "200" ]]; then
    pass "9.2" "curl -I /static/css/tapne.css returned 200"
  else
    fail "9.2" "curl -I /static/css/tapne.css returned ${css_head_code}"
  fi
else
  fail "9.2" "Static HEAD smoke check skipped because health check failed"
fi

if [[ "$CONTAINER_STARTED" -eq 1 ]]; then
  STOP_START=$SECONDS
  if docker_cli stop -t "$STOP_TIMEOUT" "$CONTAINER_NAME" >/dev/null 2>&1; then
    CONTAINER_STOPPED=1
    STOP_ELAPSED=$((SECONDS - STOP_START))
  else
    CONTAINER_STOPPED=0
    STOP_ELAPSED=$((SECONDS - STOP_START))
  fi

  if [[ "$CONTAINER_STOPPED" -eq 1 && "$STOP_ELAPSED" -le "$((STOP_TIMEOUT + 2))" ]]; then
    pass "0.3" "Container stopped gracefully in ${STOP_ELAPSED}s (SIGTERM window ${STOP_TIMEOUT}s)"
  else
    fail "0.3" "Container did not stop gracefully within ${STOP_TIMEOUT}s"
  fi
fi

log ""
log "== Summary =="
log "PASS: $PASS_COUNT"
log "FAIL: $FAIL_COUNT"
log "WARN: $WARN_COUNT"
log "SKIP: $SKIP_COUNT"

if [[ "$FAIL_COUNT" -gt 0 ]]; then
  log "Blocking checks failed: ${_failed_ids[*]}"
  exit 1
fi

if [[ "$WARN_COUNT" -gt 0 ]]; then
  log "Non-blocking warnings: ${_warn_ids[*]}"
fi

if [[ "$SKIP_COUNT" -gt 0 ]]; then
  log "Skipped checks: ${_skipped_ids[*]}"
fi

exit 0
