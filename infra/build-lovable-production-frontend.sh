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

refresh_instructions() {
  echo "Run 'pwsh -File infra/refresh-lovable-build-lock.ps1' (or 'bash infra/refresh-lovable-build-lock.sh') to regenerate the external build lock from lovable/package.json."
}

json_field() {
  node -e 'const fs = require("fs"); const meta = JSON.parse(fs.readFileSync(process.argv[1], "utf8")); const value = meta[process.argv[2]]; if (value === undefined || value === null) { process.exit(2); } process.stdout.write(String(value));' "$1" "$2"
}

sha256_file() {
  node -e 'const fs = require("fs"); const crypto = require("crypto"); process.stdout.write(crypto.createHash("sha256").update(fs.readFileSync(process.argv[1])).digest("hex"));' "$1"
}

assert_lovable_build_lock() {
  local package_json_path="$1"
  local lock_path="$2"
  local metadata_path="$3"
  local instructions
  instructions="$(refresh_instructions)"

  [[ -f "$lock_path" ]] || { echo "Missing external Lovable build lock: $lock_path. $instructions" >&2; exit 1; }
  [[ -f "$metadata_path" ]] || { echo "Missing external Lovable build lock metadata: $metadata_path. $instructions" >&2; exit 1; }

  local expected_hash
  expected_hash="$(json_field "$metadata_path" "package_json_sha256" 2>/dev/null || true)"
  [[ -n "$expected_hash" ]] || {
    echo "External Lovable build lock metadata does not contain package_json_sha256: $metadata_path. $instructions" >&2
    exit 1
  }
  expected_hash="$(printf '%s' "$expected_hash" | tr '[:upper:]' '[:lower:]')"

  local actual_hash
  actual_hash="$(sha256_file "$package_json_path")"
  if [[ "$actual_hash" != "$expected_hash" ]]; then
    echo "Lovable build lock is stale for $package_json_path. Expected package.json sha256 $expected_hash, actual $actual_hash. $instructions" >&2
    exit 1
  fi
}

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

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)    REPO_ROOT="$2";    shift 2 ;;
    --lovable-root) LOVABLE_ROOT="$2"; shift 2 ;;
    --output-dir)   OUTPUT_DIR="$2";   shift 2 ;;
    --skip-install) SKIP_INSTALL=1;    shift   ;;
    -v|--verbose)   VERBOSE=1;         shift   ;;
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
FRONTEND_SPA_ROOT="$REPO_ROOT/frontend_spa"
EXTERNAL_BUILD_LOCK="$REPO_ROOT/infra/lovable-build.package-lock.json"
EXTERNAL_BUILD_LOCK_METADATA="$REPO_ROOT/infra/lovable-build.lock-metadata.json"
ISOLATED_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/tapne-lovable-build.XXXXXX")"
ISOLATED_LOVABLE_ROOT="$ISOLATED_ROOT/lovable"
ISOLATED_FRONTEND_SPA_ROOT="$ISOLATED_ROOT/frontend_spa"
ISOLATED_CONFIG_PATH="$ISOLATED_FRONTEND_SPA_ROOT/vite.production.config.ts"
ISOLATED_VITE="$ISOLATED_LOVABLE_ROOT/node_modules/.bin/vite"
LOVABLE_GIT_STATUS_BEFORE=""

trap cleanup EXIT

# ── Preflight ─────────────────────────────────────────────────────────────────
[[ -d "$LOVABLE_ROOT" ]]      || { echo "Lovable source directory not found: $LOVABLE_ROOT" >&2; exit 1; }
[[ -d "$FRONTEND_SPA_ROOT" ]] || { echo "frontend_spa directory not found: $FRONTEND_SPA_ROOT" >&2; exit 1; }
[[ -f "$LOVABLE_PACKAGE_JSON" ]] || { echo "Lovable package.json not found: $LOVABLE_PACKAGE_JSON" >&2; exit 1; }
command -v node >/dev/null 2>&1 || { echo "node is required but not found on PATH" >&2; exit 1; }
command -v npm  >/dev/null 2>&1 || { echo "npm is required but not found on PATH" >&2; exit 1; }
[[ -d "$LOVABLE_ROOT/.git" ]] && LOVABLE_GIT_STATUS_BEFORE="$(git -C "$LOVABLE_ROOT" status --porcelain=v1)"

assert_lovable_build_lock "$LOVABLE_PACKAGE_JSON" "$EXTERNAL_BUILD_LOCK" "$EXTERNAL_BUILD_LOCK_METADATA"

copy_tree "$LOVABLE_ROOT" "$ISOLATED_LOVABLE_ROOT" .git node_modules dist dist-ssr
copy_tree "$FRONTEND_SPA_ROOT" "$ISOLATED_FRONTEND_SPA_ROOT" .git node_modules dist dist-ssr
cp "$EXTERNAL_BUILD_LOCK" "$ISOLATED_LOVABLE_ROOT/package-lock.json"

if [[ "$SKIP_INSTALL" -eq 0 ]]; then
  echo "==> Installing npm dependencies in isolated workspace"
  cd "$ISOLATED_LOVABLE_ROOT"
  npm ci
else
  [[ -d "$LOVABLE_ROOT/node_modules" ]] || {
    echo "SkipInstall requires lovable/node_modules to already exist" >&2
    exit 1
  }
  ln -s "$LOVABLE_ROOT/node_modules" "$ISOLATED_LOVABLE_ROOT/node_modules"
fi

# ── Build ─────────────────────────────────────────────────────────────────────
echo "==> Building production frontend"
[[ -d "$OUTPUT_DIR" ]] && rm -rf "$OUTPUT_DIR"

"$ISOLATED_VITE" build \
  "--config=$ISOLATED_CONFIG_PATH" \
  "--outDir=$OUTPUT_DIR"

# ── Verify ────────────────────────────────────────────────────────────────────
[[ -f "$OUTPUT_DIR/index.html" ]] \
  || { echo "Build succeeded but index.html is missing in $OUTPUT_DIR" >&2; exit 1; }

if [[ -d "$LOVABLE_ROOT/.git" ]]; then
  LOVABLE_GIT_STATUS_AFTER="$(git -C "$LOVABLE_ROOT" status --porcelain=v1)"
  [[ "$LOVABLE_GIT_STATUS_BEFORE" == "$LOVABLE_GIT_STATUS_AFTER" ]] \
    || { echo "Build mutated the Lovable worktree. git status before and after the build did not match." >&2; exit 1; }
fi

echo "[OK] Built Lovable frontend from $LOVABLE_ROOT into $OUTPUT_DIR without writing inside the checked-out lovable/"
