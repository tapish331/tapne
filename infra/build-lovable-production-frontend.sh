#!/usr/bin/env bash
# Build the Lovable SPA into artifacts/lovable-production-dist without
# writing into the checked-out lovable/ tree. Mac equivalent of
# infra/build-lovable-production-frontend.ps1.
#
# Usage:
#   bash infra/build-lovable-production-frontend.sh
#   bash infra/build-lovable-production-frontend.sh --skip-install
#   bash infra/build-lovable-production-frontend.sh --lovable-root /tmp/tapne-lovable-refresh
#   bash infra/build-lovable-production-frontend.sh --output-dir /custom/path --verbose
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SKIP_INSTALL=0
OUTPUT_DIR=""
LOVABLE_ROOT=""
VERBOSE=0

cleanup() {
  rm -rf "$ISOLATED_ROOT"
}

copy_tree() {
  local source="$1"
  local destination="$2"
  shift 2
  mkdir -p "$destination"
  local -a excludes=()
  for pattern in "$@"; do
    excludes+=(--exclude="$pattern")
  done
  (
    cd "$source"
    tar "${excludes[@]}" -cf - .
  ) | (
    cd "$destination"
    tar -xf -
  )
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)    REPO_ROOT="$2";    shift 2 ;;
    --lovable-root) LOVABLE_ROOT="$2"; shift 2 ;;
    --output-dir)   OUTPUT_DIR="$2";   shift 2 ;;
    --skip-install) SKIP_INSTALL=1;    shift ;;
    -v|--verbose)   VERBOSE=1;         shift ;;
    -h|--help)
      echo "Usage: $0 [--repo-root DIR] [--output-dir DIR] [--skip-install] [--verbose]"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

[[ "$VERBOSE" -eq 1 ]] && set -x

[[ -z "$OUTPUT_DIR" ]] && OUTPUT_DIR="$REPO_ROOT/artifacts/lovable-production-dist"
[[ "$OUTPUT_DIR" != /* ]] && OUTPUT_DIR="$REPO_ROOT/$OUTPUT_DIR"

[[ -z "$LOVABLE_ROOT" ]] && LOVABLE_ROOT="$REPO_ROOT/lovable"
[[ "$LOVABLE_ROOT" != /* ]] && LOVABLE_ROOT="$REPO_ROOT/$LOVABLE_ROOT"
LOVABLE_PACKAGE_JSON="$LOVABLE_ROOT/package.json"
ISOLATED_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/tapne-lovable-build.XXXXXX")"
ISOLATED_LOVABLE_ROOT="$ISOLATED_ROOT/lovable"
ISOLATED_VITE="$ISOLATED_LOVABLE_ROOT/node_modules/.bin/vite"
LOVABLE_GIT_STATUS_BEFORE=""

trap cleanup EXIT

[[ -d "$LOVABLE_ROOT" ]] || { echo "Lovable source directory not found: $LOVABLE_ROOT" >&2; exit 1; }
[[ -f "$LOVABLE_PACKAGE_JSON" ]] || { echo "Lovable package.json not found: $LOVABLE_PACKAGE_JSON" >&2; exit 1; }
command -v node >/dev/null 2>&1 || { echo "node is required but not found on PATH" >&2; exit 1; }
command -v npm  >/dev/null 2>&1 || { echo "npm is required but not found on PATH" >&2; exit 1; }
[[ -d "$LOVABLE_ROOT/.git" ]] && LOVABLE_GIT_STATUS_BEFORE="$(git -C "$LOVABLE_ROOT" status --porcelain=v1)"

copy_tree "$LOVABLE_ROOT" "$ISOLATED_LOVABLE_ROOT" .git node_modules dist dist-ssr

if [[ "$SKIP_INSTALL" -eq 0 ]]; then
  echo "==> Installing npm dependencies in isolated workspace"
  cd "$ISOLATED_LOVABLE_ROOT"
  if ! npm ci --no-audit --no-fund; then
    echo "==> npm ci failed in isolated workspace; falling back to npm install because lovable/package-lock.json is out of sync" >&2
    npm install --no-audit --no-fund
  fi
else
  [[ -d "$LOVABLE_ROOT/node_modules" ]] || {
    echo "SkipInstall requires lovable/node_modules to already exist" >&2
    exit 1
  }
  ln -s "$LOVABLE_ROOT/node_modules" "$ISOLATED_LOVABLE_ROOT/node_modules"
fi

echo "==> Building production frontend"
[[ -d "$OUTPUT_DIR" ]] && rm -rf "$OUTPUT_DIR"

cd "$ISOLATED_LOVABLE_ROOT"
"$ISOLATED_VITE" build "--outDir=$OUTPUT_DIR"

[[ -f "$OUTPUT_DIR/index.html" ]] \
  || { echo "Build succeeded but index.html is missing in $OUTPUT_DIR" >&2; exit 1; }

if [[ -d "$LOVABLE_ROOT/.git" ]]; then
  LOVABLE_GIT_STATUS_AFTER="$(git -C "$LOVABLE_ROOT" status --porcelain=v1)"
  [[ "$LOVABLE_GIT_STATUS_BEFORE" == "$LOVABLE_GIT_STATUS_AFTER" ]] \
    || { echo "Build mutated the Lovable worktree. git status before and after the build did not match." >&2; exit 1; }
fi

echo "[OK] Built Lovable frontend from $LOVABLE_ROOT into $OUTPUT_DIR without writing inside the checked-out lovable/"
