#!/usr/bin/env bash
# Bootstraps Artifact Registry and pushes the Tapne web Docker image.
# Mac equivalent of infra/push-web-image-to-artifact.ps1
#
# Usage:
#   bash infra/push-web-image-to-artifact.sh --verbose
#   bash infra/push-web-image-to-artifact.sh --no-build --verbose
#   bash infra/push-web-image-to-artifact.sh \
#     --project-id tapne-487110 --region asia-south1 \
#     --repository tapne --image-name tapne-web --image-tag cloudrun-check
set -Eeuo pipefail
export CLOUDSDK_COMPONENT_MANAGER_DISABLE_UPDATE_CHECK=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PROJECT_ID="tapne-487110"
REGION="asia-south1"
REPOSITORY="tapne"
IMAGE_NAME="tapne-web"
IMAGE_TAG="cloudrun-check"
LOCAL_IMAGE_REF=""
DOCKERFILE="infra/Dockerfile.web"
BUILD_CONTEXT="."
DISABLE_BUILD_ATTESTATIONS=1
DISABLE_CONTAINER_SCANNING=1
NO_BUILD=0
SKIP_AUTH_LOGIN=0
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
    --project-id)                       PROJECT_ID="$2";              shift 2 ;;
    --region)                           REGION="$2";                  shift 2 ;;
    --repository)                       REPOSITORY="$2";              shift 2 ;;
    --image-name)                       IMAGE_NAME="$2";              shift 2 ;;
    --image-tag)                        IMAGE_TAG="$2";               shift 2 ;;
    --local-image-ref)                  LOCAL_IMAGE_REF="$2";         shift 2 ;;
    --dockerfile)                       DOCKERFILE="$2";              shift 2 ;;
    --build-context)                    BUILD_CONTEXT="$2";           shift 2 ;;
    --no-build)                         NO_BUILD=1;                   shift   ;;
    --skip-auth-login)                  SKIP_AUTH_LOGIN=1;            shift   ;;
    --no-disable-build-attestations)    DISABLE_BUILD_ATTESTATIONS=0; shift   ;;
    --no-disable-container-scanning)    DISABLE_CONTAINER_SCANNING=0; shift   ;;
    -v|--verbose)                       VERBOSE=1;                    shift   ;;
    -h|--help)
      echo "Usage: $0 [--project-id ID] [--region R] [--repository R] [--image-name N]"
      echo "          [--image-tag T] [--no-build] [--skip-auth-login] [--verbose]"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

[[ "$VERBOSE" -eq 1 ]] && set -x

[[ -z "$LOCAL_IMAGE_REF" ]] && LOCAL_IMAGE_REF="${IMAGE_NAME}:${IMAGE_TAG}"

REGISTRY_HOST="${REGION}-docker.pkg.dev"
REMOTE_IMAGE_REF="${REGISTRY_HOST}/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${IMAGE_TAG}"
REMOTE_IMAGE_PATH="${REGISTRY_HOST}/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}"
DOCKERFILE_ABS="$REPO_ROOT/$DOCKERFILE"
BUILD_CONTEXT_ABS="$REPO_ROOT/$BUILD_CONTEXT"

[[ "$VERBOSE" -eq 1 ]] && echo "[verbose] project=$PROJECT_ID region=$REGION repo=$REPOSITORY image=$LOCAL_IMAGE_REF remote=$REMOTE_IMAGE_REF no-build=$NO_BUILD"

# ── Step 1: Preflight ─────────────────────────────────────────────────────────
step "Preflight checks"
command -v gcloud >/dev/null 2>&1 || die "gcloud CLI is not available on PATH. Install: https://cloud.google.com/sdk/docs/install"
command -v docker  >/dev/null 2>&1 || die "Docker CLI is not available on PATH."

gcloud --version >/dev/null 2>&1   || die "gcloud is installed but not functioning."
docker version --format '{{.Server.Version}}' >/dev/null 2>&1 \
  || die "Docker daemon check failed. Is Docker Desktop running?"
ok "gcloud and docker are available."

# ── Step 2: gcloud auth ───────────────────────────────────────────────────────
step "Ensuring gcloud authentication"
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

# ── Step 3: Set project ───────────────────────────────────────────────────────
step "Setting gcloud project"
gcloud config set project "$PROJECT_ID" --quiet
EFFECTIVE_PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
ok "Active project: $EFFECTIVE_PROJECT"

# ── Step 4: Enable Artifact Registry API ──────────────────────────────────────
step "Ensuring Artifact Registry API is enabled"
gcloud services enable artifactregistry.googleapis.com --project="$PROJECT_ID" --quiet
ok "Artifact Registry API is enabled."

# ── Step 5: Ensure repository exists ─────────────────────────────────────────
step "Ensuring Artifact Registry repository exists"
if gcloud artifacts repositories describe "$REPOSITORY" \
    --project="$PROJECT_ID" --location="$REGION" --format='value(name)' >/dev/null 2>&1; then
  ok "Repository already exists: $REPOSITORY"
else
  info "Repository '$REPOSITORY' not found in $REGION. Creating..."
  gcloud artifacts repositories create "$REPOSITORY" \
    --project="$PROJECT_ID" \
    --repository-format=docker \
    --location="$REGION" \
    --description="Tapne container images" \
    --quiet
  ok "Repository created: $REPOSITORY"
fi

# ── Step 6: Disable container scanning ───────────────────────────────────────
if [[ "$DISABLE_CONTAINER_SCANNING" -eq 1 ]]; then
  step "Ensuring Container Registry vulnerability scanning is disabled"

  # Try repo-level flag first (newer gcloud SDK)
  if gcloud artifacts repositories update --help 2>/dev/null | grep -q -- '--disable-vulnerability-scanning'; then
    gcloud artifacts repositories update "$REPOSITORY" \
      --project="$PROJECT_ID" \
      --location="$REGION" \
      --disable-vulnerability-scanning \
      --quiet 2>/dev/null || true
    ok "Repository-level vulnerability scanning disabled."
  fi

  SCANNING_SVC="containerscanning.googleapis.com"
  IS_ENABLED="$(gcloud services list --enabled --project="$PROJECT_ID" \
    --filter="config.name=$SCANNING_SVC" --format='value(config.name)' 2>/dev/null || true)"
  if [[ -n "$IS_ENABLED" ]]; then
    gcloud services disable "$SCANNING_SVC" --project="$PROJECT_ID" --quiet 2>/dev/null || true
    ok "Container Registry vulnerability scanning API disabled."
  else
    ok "Container Registry vulnerability scanning API is already disabled."
  fi
fi

# ── Step 7: Configure Docker auth ────────────────────────────────────────────
step "Configuring Docker auth for Artifact Registry"
gcloud auth configure-docker "$REGISTRY_HOST" --quiet
ok "Docker auth configured for $REGISTRY_HOST"

# ── Step 8: Build or verify local image ───────────────────────────────────────
if [[ "$NO_BUILD" -eq 0 ]]; then
  [[ -f "$DOCKERFILE_ABS" ]] || die "Dockerfile not found: $DOCKERFILE_ABS"

  step "Building local web image: $LOCAL_IMAGE_REF"

  BUILD_EXTRA_ARGS=()
  if [[ "$DISABLE_BUILD_ATTESTATIONS" -eq 1 ]]; then
    export BUILDX_NO_DEFAULT_ATTESTATIONS=1
    if docker build --help 2>/dev/null | grep -q -- '--provenance'; then
      BUILD_EXTRA_ARGS+=("--provenance=false")
    fi
    if docker build --help 2>/dev/null | grep -q -- '--sbom'; then
      BUILD_EXTRA_ARGS+=("--sbom=false")
    fi
  fi

  docker build "${BUILD_EXTRA_ARGS[@]}" \
    -f "$DOCKERFILE_ABS" \
    -t "$LOCAL_IMAGE_REF" \
    "$BUILD_CONTEXT_ABS"
  ok "Built local image: $LOCAL_IMAGE_REF"
else
  step "Skipping build (--no-build)"
  docker image inspect "$LOCAL_IMAGE_REF" >/dev/null 2>&1 \
    || die "Local image '$LOCAL_IMAGE_REF' not found and --no-build was set."
  ok "Using existing local image: $LOCAL_IMAGE_REF"
fi

# ── Step 9: Check existing remote tag ────────────────────────────────────────
step "Checking existing remote tag"
EXISTING_DIGEST="$(gcloud artifacts docker tags list "$REMOTE_IMAGE_PATH" \
    --project="$PROJECT_ID" \
    --filter="tag:$IMAGE_TAG" \
    --format='value(version)' 2>/dev/null | head -1 || true)"
if [[ -n "$EXISTING_DIGEST" ]]; then
  info "Remote tag already exists and will be replaced: $REMOTE_IMAGE_REF"
else
  info "Remote tag does not exist yet: $REMOTE_IMAGE_REF"
fi

# ── Step 10: Tag and push ─────────────────────────────────────────────────────
step "Tagging and pushing image"
docker tag "$LOCAL_IMAGE_REF" "$REMOTE_IMAGE_REF"
docker push "$REMOTE_IMAGE_REF"
ok "Pushed image: $REMOTE_IMAGE_REF"

# ── Step 11: Post-push manifest verification ──────────────────────────────────
step "Post-push verification"
MANIFEST_JSON="$(docker manifest inspect "$REMOTE_IMAGE_REF" 2>/dev/null || true)"
if [[ -n "$MANIFEST_JSON" ]]; then
  if echo "$MANIFEST_JSON" | grep -q '"amd64"'; then
    ok "Manifest includes linux/amd64."
  else
    echo "[WARN] Manifest was read but linux/amd64 was not explicitly detected." >&2
  fi
else
  echo "[WARN] Could not inspect pushed manifest. Push already succeeded." >&2
fi

echo ""
echo -e "${CYAN}Remote image ref:${NC}"
echo "  $REMOTE_IMAGE_REF"
echo ""
ok "Artifact Registry setup + web image upload completed."
