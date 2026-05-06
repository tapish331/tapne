#!/usr/bin/env bash
# Full Tapne Cloud Run deployment workflow.
# Mac equivalent of infra/run-cloud-run-workflow.ps1.
#
# Steps:
#   1/6 build-lovable-production-frontend
#   2/6 setup-faithful-local
#   3/6 check-cloud-run-web-image
#   4/6 push-web-image-to-artifact
#   5/6 setup-custom-domain
#   6/6 deploy-cloud-run
#
# Usage:
#   bash infra/run-cloud-run-workflow.sh --verbose
#   bash infra/run-cloud-run-workflow.sh \
#     --project-id tapne-487110 --region asia-south1 \
#     --domain tapnetravel.com --www-domain www.tapnetravel.com \
#     --image-tag cloudrun-check --verbose
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

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

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
step() { echo ""; printf "${CYAN}==> %s${NC}\n" "$*"; }
ok()   { printf "${GREEN}[OK] %s${NC}\n" "$*"; }
info() { printf "${YELLOW}[INFO] %s${NC}\n" "$*"; }
die()  { printf "${RED}[FAILED] %s${NC}\n" "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-id)                     PROJECT_ID="$2"; shift 2 ;;
    --region)                         REGION="$2"; shift 2 ;;
    --repository)                     REPOSITORY="$2"; shift 2 ;;
    --image-name)                     IMAGE_NAME="$2"; shift 2 ;;
    --image-tag)                      IMAGE_TAG="$2"; shift 2 ;;
    --service-name)                   SERVICE_NAME="$2"; shift 2 ;;
    --domain)                         DOMAIN="$2"; shift 2 ;;
    --www-domain)                     WWW_DOMAIN="$2"; shift 2 ;;
    --google-maps-api-key)            GOOGLE_MAPS_API_KEY="$2"; shift 2 ;;
    --no-demo-catalog)                ENABLE_DEMO_CATALOG=0; shift ;;
    --enable-demo-catalog)            ENABLE_DEMO_CATALOG=1; shift ;;
    --no-auto-start-docker)           AUTO_START_DOCKER=0; shift ;;
    --skip-auth-login)                SKIP_AUTH_LOGIN=1; shift ;;
    --skip-migrations)                SKIP_MIGRATIONS=1; shift ;;
    --skip-smoke-test)                SKIP_SMOKE_TEST=1; shift ;;
    --skip-domain)                    SKIP_DOMAIN=1; shift ;;
    --skip-deploy)                    SKIP_DEPLOY=1; shift ;;
    --no-disable-build-attestations)  DISABLE_BUILD_ATTESTATIONS=0; shift ;;
    --no-disable-container-scanning)  DISABLE_CONTAINER_SCANNING=0; shift ;;
    -v|--verbose)                     VERBOSE=1; shift ;;
    -h|--help)
      echo "Usage: $0 [--project-id ID] [--region R] [--domain D] [--www-domain W]"
      echo "          [--image-tag T] [--skip-migrations] [--skip-smoke-test] [--verbose]"
      echo ""
      echo "Optional skip flags:"
      echo "  --skip-domain   Skip step 5/6 (setup-custom-domain.sh)"
      echo "  --skip-deploy   Skip steps 5/6 and 6/6"
      exit 0
      ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[[ "$VERBOSE" -eq 1 ]] && set -x

trim() {
  printf '%s' "$1" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

lower() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

read_dotenv_value() {
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

resolve_artifact_http_path() {
  local value="$1"
  value="$(trim "$value")"
  [[ -n "$value" ]] || die "Artifact asset path is empty."
  case "$value" in
    http://*|https://*) value="/${value#*://*/}" ;;
  esac
  [[ "$value" == /* ]] || value="/${value#./}"
  printf '%s\n' "$value"
}

get_frontend_smoke_asset_paths() {
  local index_path="$1"
  [[ -f "$index_path" ]] || die "Frontend artifact index.html was not found: $index_path"
  python3 - "$index_path" <<'PY'
import html.parser
import sys
from urllib.parse import urlparse

class Parser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.css = ""
        self.js = ""

    def handle_starttag(self, tag, attrs):
        attrs = {k.lower(): v for k, v in attrs if k}
        if tag.lower() == "link" and attrs.get("rel", "").lower() == "stylesheet" and not self.css:
            self.css = attrs.get("href", "")
        if tag.lower() == "script" and attrs.get("type", "").lower() == "module" and not self.js:
            self.js = attrs.get("src", "")

def normalize(value):
    value = (value or "").strip()
    if not value:
        raise SystemExit("empty asset path")
    parsed = urlparse(value)
    if parsed.scheme:
        value = parsed.path + (("?" + parsed.query) if parsed.query else "")
    if not value.startswith("/"):
        value = "/" + value.lstrip("./")
    return value

parser = Parser()
with open(sys.argv[1], "r", encoding="utf-8") as fh:
    parser.feed(fh.read())
if not parser.css:
    raise SystemExit("Could not find a stylesheet href in %s" % sys.argv[1])
if not parser.js:
    raise SystemExit("Could not find a module script src in %s" % sys.argv[1])
print(normalize(parser.css))
print(normalize(parser.js))
PY
}

LOCAL_IMAGE_REF="${IMAGE_NAME}:${IMAGE_TAG}"
ARTIFACT_IMAGE_REF="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${IMAGE_TAG}"
FRONTEND_ARTIFACT_INDEX="$REPO_ROOT/artifacts/lovable-production-dist/index.html"

DOMAINS=()
for candidate in "$DOMAIN" "$WWW_DOMAIN"; do
  normalized="$(lower "$(trim "$candidate")")"
  [[ -z "$normalized" ]] && continue
  found=0
  for existing in "${DOMAINS[@]}"; do
    [[ "$existing" == "$normalized" ]] && found=1 && break
  done
  [[ "$found" -eq 0 ]] && DOMAINS+=("$normalized")
done
[[ "${#DOMAINS[@]}" -gt 0 ]] || die "At least one non-empty domain is required."

CANONICAL_HOST="${DOMAINS[0]}"
DJANGO_ALLOWED_HOSTS="$(IFS=','; printf '%s' "${DOMAINS[*]}")"
CSRF_TRUSTED_ORIGINS=""
for domain in "${DOMAINS[@]}"; do
  [[ -n "$CSRF_TRUSTED_ORIGINS" ]] && CSRF_TRUSTED_ORIGINS+=","
  CSRF_TRUSTED_ORIGINS+="https://${domain}"
done

DOTENV="$REPO_ROOT/.env"
if [[ -z "$GOOGLE_MAPS_API_KEY" ]]; then
  GOOGLE_MAPS_API_KEY="$(read_dotenv_value "$DOTENV" "GOOGLE_MAPS_API_KEY" || true)"
fi
if [[ -z "$GOOGLE_MAPS_API_KEY" ]]; then
  GOOGLE_MAPS_API_KEY="${GOOGLE_PLACES_API_KEY:-}"
fi
if [[ -z "$GOOGLE_MAPS_API_KEY" ]]; then
  GOOGLE_MAPS_API_KEY="$(read_dotenv_value "$DOTENV" "GOOGLE_PLACES_API_KEY" || true)"
fi
[[ -n "$GOOGLE_MAPS_API_KEY" ]] && export GOOGLE_MAPS_API_KEY

if [[ -z "${GOOGLE_CLIENT_ID:-}" ]]; then
  GOOGLE_CLIENT_ID="$(read_dotenv_value "$DOTENV" "GOOGLE_CLIENT_ID" || true)"
  [[ -n "$GOOGLE_CLIENT_ID" ]] && export GOOGLE_CLIENT_ID
fi
if [[ -z "${GOOGLE_CLIENT_SECRET:-}" ]]; then
  GOOGLE_CLIENT_SECRET="$(read_dotenv_value "$DOTENV" "GOOGLE_CLIENT_SECRET" || true)"
  [[ -n "$GOOGLE_CLIENT_SECRET" ]] && export GOOGLE_CLIENT_SECRET
fi

BUILD_FRONTEND_SCRIPT="$SCRIPT_DIR/build-lovable-production-frontend.sh"
SETUP_LOCAL_SCRIPT="$SCRIPT_DIR/setup-faithful-local.sh"
CHECK_IMAGE_SCRIPT="$SCRIPT_DIR/check-cloud-run-web-image.sh"
PUSH_IMAGE_SCRIPT="$SCRIPT_DIR/push-web-image-to-artifact.sh"
CUSTOM_DOMAIN_SCRIPT="$SCRIPT_DIR/setup-custom-domain.sh"
DEPLOY_SCRIPT="$SCRIPT_DIR/deploy-cloud-run.sh"

for script in "$BUILD_FRONTEND_SCRIPT" "$SETUP_LOCAL_SCRIPT" "$CHECK_IMAGE_SCRIPT" "$PUSH_IMAGE_SCRIPT"; do
  [[ -f "$script" ]] || die "Required script not found: $script"
done
[[ "$SKIP_DOMAIN" -eq 1 || "$SKIP_DEPLOY" -eq 1 || -f "$CUSTOM_DOMAIN_SCRIPT" ]] || die "Required script not found: $CUSTOM_DOMAIN_SCRIPT"
[[ "$SKIP_DEPLOY" -eq 1 || -f "$DEPLOY_SCRIPT" ]] || die "Required script not found: $DEPLOY_SCRIPT"

run_step() {
  local label="$1"; shift
  local script="$1"; shift
  local start end elapsed
  step "$label"
  [[ -f "$script" ]] || die "Script not found for step '$label': $script"
  start="$(date +%s)"
  bash "$script" "$@"
  end="$(date +%s)"
  elapsed=$((end - start))
  ok "$label completed in $(printf '%02d:%02d:%02d' $((elapsed/3600)) $(((elapsed%3600)/60)) $((elapsed%60)))"
}

format_elapsed() {
  local seconds="$1"
  printf '%02d:%02d:%02d' $((seconds/3600)) $(((seconds%3600)/60)) $((seconds%60))
}

if [[ "$VERBOSE" -eq 1 ]]; then
  echo ""
  echo "[verbose] ProjectId=$PROJECT_ID Region=$REGION Repository=$REPOSITORY"
  echo "[verbose] Image=$IMAGE_NAME Tag=$IMAGE_TAG Service=$SERVICE_NAME"
  echo "[verbose] Domains=${DOMAINS[*]}"
  echo "[verbose] LocalImageRef=$LOCAL_IMAGE_REF"
  echo "[verbose] ArtifactImageRef=$ARTIFACT_IMAGE_REF"
  echo "[verbose] CanonicalHost=$CANONICAL_HOST"
  echo "[verbose] SkipDomain=$SKIP_DOMAIN SkipDeploy=$SKIP_DEPLOY"
  echo "[verbose] GoogleMapsApiKeySet=$([[ -n "$GOOGLE_MAPS_API_KEY" ]] && echo true || echo false)"
  echo "[verbose] GoogleOAuthSet=$([[ -n "${GOOGLE_CLIENT_ID:-}" && -n "${GOOGLE_CLIENT_SECRET:-}" ]] && echo true || echo false)"
  echo "[verbose] EnableDemoCatalog=$([[ "$ENABLE_DEMO_CATALOG" -eq 1 ]] && echo true || echo false)"
fi

BUILD_ARGS=(--repo-root "$REPO_ROOT")
[[ "$VERBOSE" -eq 1 ]] && BUILD_ARGS+=(--verbose)

SETUP_ARGS=(--web-image-ref "$LOCAL_IMAGE_REF")
[[ "$AUTO_START_DOCKER" -eq 0 ]] && SETUP_ARGS+=(--no-auto-start-docker)
[[ "$DISABLE_BUILD_ATTESTATIONS" -eq 0 ]] && SETUP_ARGS+=(--no-disable-build-attestations)
[[ "$VERBOSE" -eq 1 ]] && SETUP_ARGS+=(--verbose)

CHECK_ARGS=(
  --no-build
  --image "$LOCAL_IMAGE_REF"
  --artifact-image "$ARTIFACT_IMAGE_REF"
  --service "$SERVICE_NAME"
  --region "$REGION"
)
[[ "$VERBOSE" -eq 1 ]] && CHECK_ARGS+=(--verbose)

PUSH_ARGS=(
  --project-id "$PROJECT_ID"
  --region "$REGION"
  --repository "$REPOSITORY"
  --image-name "$IMAGE_NAME"
  --image-tag "$IMAGE_TAG"
  --no-build
)
[[ "$DISABLE_BUILD_ATTESTATIONS" -eq 0 ]] && PUSH_ARGS+=(--no-disable-build-attestations)
[[ "$DISABLE_CONTAINER_SCANNING" -eq 0 ]] && PUSH_ARGS+=(--no-disable-container-scanning)
[[ "$SKIP_AUTH_LOGIN" -eq 1 ]] && PUSH_ARGS+=(--skip-auth-login)
[[ "$VERBOSE" -eq 1 ]] && PUSH_ARGS+=(--verbose)

DOMAIN_ARGS=(
  --project-id "$PROJECT_ID"
  --region "$REGION"
  --service-name "$SERVICE_NAME"
  --domain "$DOMAIN"
  --www-domain "$WWW_DOMAIN"
)
[[ "$SKIP_AUTH_LOGIN" -eq 1 ]] && DOMAIN_ARGS+=(--skip-auth-login)
[[ "$VERBOSE" -eq 1 ]] && DOMAIN_ARGS+=(--verbose)

WORKFLOW_START="$(date +%s)"

run_step "1/6 build-lovable-production-frontend" "$BUILD_FRONTEND_SCRIPT" "${BUILD_ARGS[@]}"

SMOKE_ASSET_LINES="$(get_frontend_smoke_asset_paths "$FRONTEND_ARTIFACT_INDEX")"
SMOKE_CSS_PATH="$(printf '%s\n' "$SMOKE_ASSET_LINES" | sed -n '1p')"
SMOKE_JS_PATH="$(printf '%s\n' "$SMOKE_ASSET_LINES" | sed -n '2p')"
[[ -n "$SMOKE_CSS_PATH" && -n "$SMOKE_JS_PATH" ]] || die "Could not resolve frontend smoke asset paths."
[[ "$VERBOSE" -eq 1 ]] && echo "[verbose] Smoke assets: CSS=$SMOKE_CSS_PATH JS=$SMOKE_JS_PATH"

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
  --smoke-css-path "$SMOKE_CSS_PATH"
  --smoke-js-path "$SMOKE_JS_PATH"
)
[[ -n "$GOOGLE_MAPS_API_KEY" ]] && DEPLOY_ARGS+=(--google-maps-api-key "$GOOGLE_MAPS_API_KEY")
[[ "$ENABLE_DEMO_CATALOG" -eq 0 ]] && DEPLOY_ARGS+=(--no-demo-catalog)
[[ "$DISABLE_CONTAINER_SCANNING" -eq 0 ]] && DEPLOY_ARGS+=(--no-disable-container-scanning)
[[ "$SKIP_AUTH_LOGIN" -eq 1 ]] && DEPLOY_ARGS+=(--skip-auth-login)
[[ "$SKIP_MIGRATIONS" -eq 1 ]] && DEPLOY_ARGS+=(--skip-migrations)
[[ "$SKIP_SMOKE_TEST" -eq 1 ]] && DEPLOY_ARGS+=(--skip-smoke-test)
[[ "$VERBOSE" -eq 1 ]] && DEPLOY_ARGS+=(--verbose)

run_step "2/6 setup-faithful-local" "$SETUP_LOCAL_SCRIPT" "${SETUP_ARGS[@]}"
run_step "3/6 check-cloud-run-web-image" "$CHECK_IMAGE_SCRIPT" "${CHECK_ARGS[@]}"
run_step "4/6 push-web-image-to-artifact" "$PUSH_IMAGE_SCRIPT" "${PUSH_ARGS[@]}"

if [[ "$SKIP_DOMAIN" -eq 0 && "$SKIP_DEPLOY" -eq 0 ]]; then
  run_step "5/6 setup-custom-domain" "$CUSTOM_DOMAIN_SCRIPT" "${DOMAIN_ARGS[@]}"
else
  info "Skipping step 5/6 setup-custom-domain (--skip-domain or --skip-deploy)."
fi

if [[ "$SKIP_DEPLOY" -eq 0 ]]; then
  run_step "6/6 deploy-cloud-run" "$DEPLOY_SCRIPT" "${DEPLOY_ARGS[@]}"
else
  info "Skipping step 6/6 deploy-cloud-run (--skip-deploy)."
fi

WORKFLOW_END="$(date +%s)"
TOTAL_ELAPSED=$((WORKFLOW_END - WORKFLOW_START))

echo ""
printf "${CYAN}Workflow summary:${NC}\n"
echo "  Local image:     $LOCAL_IMAGE_REF"
echo "  Artifact image:  $ARTIFACT_IMAGE_REF"
echo "  Canonical host:  $CANONICAL_HOST"
echo "  Total duration:  $(format_elapsed "$TOTAL_ELAPSED")"
echo ""
ok "All workflow steps completed successfully."
