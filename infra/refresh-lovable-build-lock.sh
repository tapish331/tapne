#!/usr/bin/env bash
# Regenerate the repo-owned external package lock for the Lovable build.
#
# The canonical lock lives under infra/ so repo-owned build automation can
# stay deterministic without modifying the checked-out lovable/ tree.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

GENERATOR_IMAGE="node:22-slim"
GENERATOR_COMMAND="npm install --package-lock-only --ignore-scripts --no-audit --no-fund"
LOVABLE_ROOT="$REPO_ROOT/lovable"
LOVABLE_PACKAGE_JSON="$LOVABLE_ROOT/package.json"
OUTPUT_LOCK="$REPO_ROOT/infra/lovable-build.package-lock.json"
OUTPUT_METADATA="$REPO_ROOT/infra/lovable-build.lock-metadata.json"
WORK_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/tapne-lovable-lock.XXXXXX")"
WORKSPACE="$WORK_ROOT/workspace"
LOVABLE_GIT_STATUS_BEFORE=""

cleanup() {
  rm -rf "$WORK_ROOT"
}
trap cleanup EXIT

sha256_file() {
  node -e 'const fs = require("fs"); const crypto = require("crypto"); process.stdout.write(crypto.createHash("sha256").update(fs.readFileSync(process.argv[1])).digest("hex"));' "$1"
}

[[ -f "$LOVABLE_PACKAGE_JSON" ]] || { echo "Lovable package.json not found: $LOVABLE_PACKAGE_JSON" >&2; exit 1; }
command -v node   >/dev/null 2>&1 || { echo "node is required but not found on PATH" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "docker is required but not found on PATH" >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "docker is installed but the daemon is not reachable." >&2; exit 1; }
[[ -d "$LOVABLE_ROOT/.git" ]] && LOVABLE_GIT_STATUS_BEFORE="$(git -C "$LOVABLE_ROOT" status --porcelain=v1)"

mkdir -p "$WORKSPACE"
cp "$LOVABLE_PACKAGE_JSON" "$WORKSPACE/package.json"

docker run --rm \
  -v "$WORKSPACE:/workspace" \
  -w /workspace \
  "$GENERATOR_IMAGE" \
  sh -lc "$GENERATOR_COMMAND && npm --version > /workspace/.npm-version"

[[ -f "$WORKSPACE/package-lock.json" ]] || { echo "The generator workspace did not produce package-lock.json" >&2; exit 1; }
[[ -f "$WORKSPACE/.npm-version" ]]     || { echo "The generator workspace did not record npm version information" >&2; exit 1; }

cp "$WORKSPACE/package-lock.json" "$OUTPUT_LOCK"

PACKAGE_JSON_SHA256="$(sha256_file "$LOVABLE_PACKAGE_JSON")"
NPM_VERSION="$(tr -d '\r\n' < "$WORKSPACE/.npm-version")"
GENERATED_AT_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

cat > "$OUTPUT_METADATA" <<EOF
{
  "lock_format_version": 1,
  "package_json_path": "lovable/package.json",
  "lockfile_path": "infra/lovable-build.package-lock.json",
  "package_json_sha256": "$PACKAGE_JSON_SHA256",
  "generator_image": "$GENERATOR_IMAGE",
  "generator_command": "$GENERATOR_COMMAND",
  "npm_version": "$NPM_VERSION",
  "generated_at_utc": "$GENERATED_AT_UTC"
}
EOF

if [[ -d "$LOVABLE_ROOT/.git" ]]; then
  LOVABLE_GIT_STATUS_AFTER="$(git -C "$LOVABLE_ROOT" status --porcelain=v1)"
  [[ "$LOVABLE_GIT_STATUS_BEFORE" == "$LOVABLE_GIT_STATUS_AFTER" ]] \
    || { echo "Refreshing the external Lovable build lock mutated the Lovable worktree." >&2; exit 1; }
fi

echo "Refreshed $OUTPUT_LOCK and $OUTPUT_METADATA from $LOVABLE_PACKAGE_JSON without writing inside lovable/"
