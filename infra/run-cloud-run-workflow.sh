#!/usr/bin/env bash
# Full Tapne Cloud Run deployment workflow — runs all 5 steps in sequence.
# Mac equivalent of infra/run-cloud-run-workflow.ps1
#
# Steps (in order):
#   1/5  setup-faithful-local        — Docker stack up, .env generated, health check
#   2/5  check-cloud-run-web-image   — validates local image is production-ready
#   3/5  push-web-image-to-artifact  -- push to Artifact Registry (no rebuild)
#   4/5  setup-custom-domain         — GCP load balancer, SSL cert, DNS
#   5/5  deploy-cloud-run            — Cloud SQL, VPC, GCS, secrets, deploy
#
# The image is built ONCE (in step 1) and reused across all subsequent steps.
# Steps 4 and 5 are skipped if --skip-domain / --skip-deploy are passed.
#
# Usage:
#   bash infra/run-cloud-run-workflow.sh
#   bash infra/run-cloud-run-workflow.sh \
#     --domain tapnetravel.com --www-domain www.tapnetravel.com --verbose
#   bash infra/run-cloud-run-workflow.sh \
#     --project-id tapne-487110 --region asia-south1 \
#     --image-tag cloudrun-check --skip-migrations --verbose
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Defaults ──────────────────────────────────────────────────────────────────
PROJECT_ID="tapne-487110"
REGION="asia-south1"
REPOSITORY="tapne"
IMAGE_NAME="tapne-web"
IMAGE_TAG="cloudrun-check"
SERVICE_NAME="tapne-web"
DOMAIN="tapnetravel.com"
WWW_DOMAIN="www.tapnetravel.com"
GOOGLE_MAPS_API_KEY="${GOOGLE_MAPS_API_KEY:-}"
ENABLE_DEMO_CATALOG=1
AUTO_START_DOCKER=1
SKIP_AUTH_LOGIN=0
SKIP_MIGRATIONS=0
SKIP_SMOKE_TEST=0
SKIP_DOMAIN=0
SKIP_DEPLOY=0
DISABLE_BUILD_ATTESTATIONS=1
DISABLE_CONTAINER_SCANNING=1
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
    --project-id)                     PROJECT_ID="$2";                   shift 2 ;;
    --region)                         REGION="$2";                       shift 2 ;;
    --repository)                     REPOSITORY="$2";                   shift 2 ;;
    --image-name)                     IMAGE_NAME="$2";                   shift 2 ;;
    --image-tag)                      IMAGE_TAG="$2";                    shift 2 ;;
    --service-name)                   SERVICE_NAME="$2";                 shift 2 ;;
    --domain)                         DOMAIN="$2";                       shift 2 ;;
    --www-domain)                     WWW_DOMAIN="$2";                   shift 2 ;;
    --google-maps-api-key)            GOOGLE_MAPS_API_KEY="$2";          shift 2 ;;
    --no-demo-catalog)                ENABLE_DEMO_CATALOG=0;             shift   ;;
    --enable-demo-catalog)            ENABLE_DEMO_CATALOG=1;             shift   ;;
    --no-auto-start-docker)           AUTO_START_DOCKER=0;               shift   ;;
    --skip-auth-login)                SKIP_AUTH_LOGIN=1;                 shift   ;;
    --skip-migrations)                SKIP_MIGRATIONS=1;                 shift   ;;
    --skip-smoke-test)                SKIP_SMOKE_TEST=1;                 shift   ;;
    --skip-domain)                    SKIP_DOMAIN=1;                     shift   ;;
    --skip-deploy)                    SKIP_DEPLOY=1;                     shift   ;;
    --no-disable-build-attestations)  DISABLE_BUILD_ATTESTATIONS=0;      shift   ;;
    --no-disable-container-scanning)  DISABLE_CONTAINER_SCANNING=0;      shift   ;;
    -v|--verbose)                     VERBOSE=1;                         shift   ;;
    -h|--help)
      echo "Usage: $0 [--project-id ID] [--region R] [--domain D] [--www-domain W]"
      echo "          [--image-tag T] [--skip-migrations] [--skip-smoke-test] [--verbose]"
      echo ""
      echo "Optional skip flags:"
      echo "  --skip-domain   Skip step 4 (setup-custom-domain.sh)"
      echo "  --skip-deploy   Skip steps 4+5 (domain + Cloud Run deploy)"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

[[ "$VERBOSE" -eq 1 ]] && set -x

# ── Derived values ────────────────────────────────────────────────────────────
LOCAL_IMAGE_REF="${IMAGE_NAME}:${IMAGE_TAG}"
ARTIFACT_IMAGE_REF="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${IMAGE_TAG}"

# Canonical host is the primary (non-www) domain
CANONICAL_HOST="$DOMAIN"

# Build allowed-hosts and CSRF origins from all non-empty domains
ALL_DOMAINS=()
[[ -n "$DOMAIN" ]]     && ALL_DOMAINS+=("$DOMAIN")
[[ -n "$WWW_DOMAIN" ]] && ALL_DOMAINS+=("$WWW_DOMAIN")

DJANGO_ALLOWED_HOSTS="$(IFS=','; echo "${ALL_DOMAINS[*]}")"
CSRF_TRUSTED_ORIGINS="$(printf 'https://%s,' "${ALL_DOMAINS[@]}" | sed 's/,$//')"

# Read GOOGLE_MAPS_API_KEY from .env if not already set
if [[ -z "$GOOGLE_MAPS_API_KEY" ]]; then
  ENV_FILE="$REPO_ROOT/.env"
  if [[ -f "$ENV_FILE" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      line="${line#"${line%%[![:space:]]*}"}"
      [[ -z "$line" || "$line" == '#'* ]] && continue
      [[ "$line" == export\ * ]] && line="${line#export }"
      key="${line%%=*}"
      val="${line#*=}"
      val="${val%\"}" ; val="${val#\"}"
      val="${val%\'}" ; val="${val#\'}"
      if [[ "$key" == "GOOGLE_MAPS_API_KEY" || "$key" == "GOOGLE_PLACES_API_KEY" ]]; then
        [[ -n "$val" ]] && GOOGLE_MAPS_API_KEY="$val"
        [[ "$key" == "GOOGLE_MAPS_API_KEY" ]] && break
      fi
    done < "$ENV_FILE"
  fi
fi
[[ -n "$GOOGLE_MAPS_API_KEY" ]] && export GOOGLE_MAPS_API_KEY

# ── Script paths ──────────────────────────────────────────────────────────────
SETUP_LOCAL_SCRIPT="$SCRIPT_DIR/setup-faithful-local.sh"
CHECK_IMAGE_SCRIPT="$SCRIPT_DIR/check-cloud-run-web-image.sh"
PUSH_IMAGE_SCRIPT="$SCRIPT_DIR/push-web-image-to-artifact.sh"
CUSTOM_DOMAIN_SCRIPT="$SCRIPT_DIR/setup-custom-domain.sh"
DEPLOY_SCRIPT="$SCRIPT_DIR/deploy-cloud-run.sh"

for s in "$SETUP_LOCAL_SCRIPT" "$CHECK_IMAGE_SCRIPT" "$PUSH_IMAGE_SCRIPT"; do
  [[ -f "$s" ]] || die "Required script not found: $s"
done
[[ "$SKIP_DOMAIN" -eq 0 && "$SKIP_DEPLOY" -eq 0 ]] && [[ -f "$CUSTOM_DOMAIN_SCRIPT" ]] || true
[[ "$SKIP_DEPLOY" -eq 0 ]]                         && [[ -f "$DEPLOY_SCRIPT" ]]         || true

# ── Helpers ───────────────────────────────────────────────────────────────────
STEP_RESULTS=()
STEP_TIMINGS=()

run_step() {
  local step_label="$1"; shift
  local script="$1";     shift
  local args=("$@")

  step "$step_label"
  [[ -f "$script" ]] || die "Script not found for step '$step_label': $script"

  local t_start
  t_start=$(date +%s)
  bash "$script" "${args[@]+"${args[@]}"}"
  local rc=$?
  local t_end
  t_end=$(date +%s)
  local elapsed=$(( t_end - t_start ))

  STEP_RESULTS+=("$step_label")
  STEP_TIMINGS+=("$elapsed")

  [[ "$rc" -eq 0 ]] || die "Step '$step_label' failed with exit code $rc."
  ok "$step_label completed in $(printf '%02d:%02d:%02d' $((elapsed/3600)) $(((elapsed%3600)/60)) $((elapsed%60)))"
}

format_elapsed() {
  local s=$1
  printf '%02d:%02d:%02d' $((s/3600)) $(((s%3600)/60)) $((s%60))
}

# ── Verbose summary ───────────────────────────────────────────────────────────
if [[ "$VERBOSE" -eq 1 ]]; then
  echo ""
  echo "[verbose] ProjectId=${PROJECT_ID} Region=${REGION} Repository=${REPOSITORY}"
  echo "[verbose] Image=${IMAGE_NAME} Tag=${IMAGE_TAG} Service=${SERVICE_NAME}"
  echo "[verbose] Domain=${DOMAIN} WwwDomain=${WWW_DOMAIN}"
  echo "[verbose] LocalImageRef=${LOCAL_IMAGE_REF}"
  echo "[verbose] ArtifactImageRef=${ARTIFACT_IMAGE_REF}"
  echo "[verbose] CanonicalHost=${CANONICAL_HOST}"
  echo "[verbose] SkipDomain=${SKIP_DOMAIN} SkipDeploy=${SKIP_DEPLOY}"
  echo "[verbose] GoogleMapsApiKeySet=$([[ -n "$GOOGLE_MAPS_API_KEY" ]] && echo true || echo false)"
  echo "[verbose] EnableDemoCatalog=$([[ "$ENABLE_DEMO_CATALOG" -eq 1 ]] && echo true || echo false)"
fi

# ── Build shared args ─────────────────────────────────────────────────────────
SETUP_ARGS=(--web-image-ref "$LOCAL_IMAGE_REF")
[[ "$AUTO_START_DOCKER" -eq 0 ]]      && SETUP_ARGS+=(--no-auto-start-docker)
[[ "$DISABLE_BUILD_ATTESTATIONS" -eq 0 ]] && SETUP_ARGS+=(--no-disable-build-attestations)
[[ "$VERBOSE" -eq 1 ]]                && SETUP_ARGS+=(--verbose)

CHECK_ARGS=(--no-build --image "$LOCAL_IMAGE_REF" --artifact-image "$ARTIFACT_IMAGE_REF"
            --service "$SERVICE_NAME" --region "$REGION")
[[ "$VERBOSE" -eq 1 ]] && CHECK_ARGS+=(--verbose)

PUSH_ARGS=(
  --project-id "$PROJECT_ID"
  --region "$REGION"
  --repository "$REPOSITORY"
  --image-name "$IMAGE_NAME"
  --image-tag "$IMAGE_TAG"
  --no-build
)
[[ "$DISABLE_BUILD_ATTESTATIONS" -eq 0 ]]  && PUSH_ARGS+=(--no-disable-build-attestations)
[[ "$DISABLE_CONTAINER_SCANNING" -eq 0 ]]  && PUSH_ARGS+=(--no-disable-container-scanning)
[[ "$SKIP_AUTH_LOGIN" -eq 1 ]]             && PUSH_ARGS+=(--skip-auth-login)
[[ "$VERBOSE" -eq 1 ]]                     && PUSH_ARGS+=(--verbose)

DOMAIN_ARGS=(
  --project-id "$PROJECT_ID"
  --region "$REGION"
  --service-name "$SERVICE_NAME"
  --domain "$DOMAIN"
)
[[ -n "$WWW_DOMAIN" ]]    && DOMAIN_ARGS+=(--www-domain "$WWW_DOMAIN")
[[ "$SKIP_AUTH_LOGIN" -eq 1 ]] && DOMAIN_ARGS+=(--skip-auth-login)
[[ "$VERBOSE" -eq 1 ]]    && DOMAIN_ARGS+=(--verbose)

DEPLOY_ARGS=(
  --project-id "$PROJECT_ID"
  --region "$REGION"
  --repository "$REPOSITORY"
  --image-name "$IMAGE_NAME"
  --image-tag "$IMAGE_TAG"
  --service-name "$SERVICE_NAME"
  --no-build-and-push
  --django-allowed-hosts "$DJANGO_ALLOWED_HOSTS"
  --csrf-trusted-origins "$CSRF_TRUSTED_ORIGINS"
  --canonical-host "$CANONICAL_HOST"
  --smoke-base-url "https://${CANONICAL_HOST}"
  --uptime-check-host "$CANONICAL_HOST"
  --cloud-run-ingress "internal-and-cloud-load-balancing"
)
[[ -n "$GOOGLE_MAPS_API_KEY" ]] && DEPLOY_ARGS+=(--google-maps-api-key "$GOOGLE_MAPS_API_KEY")
[[ "$ENABLE_DEMO_CATALOG" -eq 0 ]] && DEPLOY_ARGS+=(--no-demo-catalog)
[[ "$DISABLE_CONTAINER_SCANNING" -eq 0 ]] && DEPLOY_ARGS+=(--no-disable-container-scanning)
[[ "$SKIP_AUTH_LOGIN" -eq 1 ]]  && DEPLOY_ARGS+=(--skip-auth-login)
[[ "$SKIP_MIGRATIONS" -eq 1 ]]  && DEPLOY_ARGS+=(--skip-migrations)
[[ "$SKIP_SMOKE_TEST" -eq 1 ]]  && DEPLOY_ARGS+=(--skip-smoke-test)
[[ "$VERBOSE" -eq 1 ]]          && DEPLOY_ARGS+=(--verbose)

# ── Execute steps ─────────────────────────────────────────────────────────────
WORKFLOW_START=$(date +%s)

run_step "1/5 setup-faithful-local"       "$SETUP_LOCAL_SCRIPT"    "${SETUP_ARGS[@]}"
run_step "2/5 check-cloud-run-web-image"  "$CHECK_IMAGE_SCRIPT"    "${CHECK_ARGS[@]}"
run_step "3/5 push-web-image-to-artifact" "$PUSH_IMAGE_SCRIPT"     "${PUSH_ARGS[@]}"

if [[ "$SKIP_DOMAIN" -eq 0 && "$SKIP_DEPLOY" -eq 0 ]]; then
  [[ -f "$CUSTOM_DOMAIN_SCRIPT" ]] || die "Custom domain script not found: $CUSTOM_DOMAIN_SCRIPT"
  run_step "4/5 setup-custom-domain"      "$CUSTOM_DOMAIN_SCRIPT"  "${DOMAIN_ARGS[@]}"
else
  info "Skipping step 4/5 setup-custom-domain (--skip-domain or --skip-deploy)."
fi

if [[ "$SKIP_DEPLOY" -eq 0 ]]; then
  [[ -f "$DEPLOY_SCRIPT" ]] || die "Deploy script not found: $DEPLOY_SCRIPT"
  run_step "5/5 deploy-cloud-run"         "$DEPLOY_SCRIPT"         "${DEPLOY_ARGS[@]}"
else
  info "Skipping step 5/5 deploy-cloud-run (--skip-deploy)."
fi

WORKFLOW_END=$(date +%s)
TOTAL_ELAPSED=$(( WORKFLOW_END - WORKFLOW_START ))

# ── Workflow summary ──────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}Workflow summary:${NC}"
echo "  Local image:    $LOCAL_IMAGE_REF"
echo "  Artifact image: $ARTIFACT_IMAGE_REF"
echo "  Canonical host: $CANONICAL_HOST"
echo "  Total duration: $(format_elapsed $TOTAL_ELAPSED)"
echo ""
ok "All workflow steps completed successfully."
