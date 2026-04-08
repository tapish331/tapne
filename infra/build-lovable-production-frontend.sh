#!/usr/bin/env bash
# Build the Lovable SPA into artifacts/lovable-production-dist.
# Mac equivalent of infra/build-lovable-production-frontend.ps1
#
# Usage:
#   bash infra/build-lovable-production-frontend.sh
#   bash infra/build-lovable-production-frontend.sh --skip-install
#   bash infra/build-lovable-production-frontend.sh --output-dir /custom/path --verbose
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SKIP_INSTALL=0
OUTPUT_DIR=""
VERBOSE=0

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)    REPO_ROOT="$2";   shift 2 ;;
    --output-dir)   OUTPUT_DIR="$2";  shift 2 ;;
    --skip-install) SKIP_INSTALL=1;   shift   ;;
    -v|--verbose)   VERBOSE=1;        shift   ;;
    -h|--help)
      echo "Usage: $0 [--repo-root DIR] [--output-dir DIR] [--skip-install] [--verbose]"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

[[ "$VERBOSE" -eq 1 ]] && set -x

[[ -z "$OUTPUT_DIR" ]] && OUTPUT_DIR="$REPO_ROOT/artifacts/lovable-production-dist"

LOVABLE_ROOT="$REPO_ROOT/lovable"
FRONTEND_SPA_ROOT="$REPO_ROOT/frontend_spa"

# ── Preflight ─────────────────────────────────────────────────────────────────
[[ -d "$LOVABLE_ROOT" ]]     || { echo "Lovable source directory not found: $LOVABLE_ROOT" >&2; exit 1; }
[[ -d "$FRONTEND_SPA_ROOT" ]] || { echo "frontend_spa directory not found: $FRONTEND_SPA_ROOT" >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "npm is required but not found on PATH" >&2; exit 1; }

# ── Install ───────────────────────────────────────────────────────────────────
cd "$LOVABLE_ROOT"

if [[ "$SKIP_INSTALL" -eq 0 ]]; then
  echo "==> Installing npm dependencies"
  npm install --package-lock=false
fi

# ── Build ─────────────────────────────────────────────────────────────────────
echo "==> Building production frontend"
[[ -d "$OUTPUT_DIR" ]] && rm -rf "$OUTPUT_DIR"

npx vite build \
  "--config=../frontend_spa/vite.production.config.ts" \
  "--outDir=$OUTPUT_DIR"

# ── Verify ────────────────────────────────────────────────────────────────────
[[ -f "$OUTPUT_DIR/index.html" ]] \
  || { echo "Build succeeded but index.html is missing in $OUTPUT_DIR" >&2; exit 1; }

echo "[OK] Built Lovable frontend into $OUTPUT_DIR"
