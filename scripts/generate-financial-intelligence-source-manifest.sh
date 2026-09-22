#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
OUTPUT=${1:-$PROJECT_ROOT/docs/evidence/financial-intelligence/SOURCE-MANIFEST-FI.json}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}
require_command git
require_command jq
require_command sha256sum

if [[ -n $(git -C "$PROJECT_ROOT" status --porcelain -- \
  .github backend database frontend infrastructure scripts tests) ]]; then
  echo "Functional paths must be clean before generating the FI source manifest." >&2
  exit 1
fi

work_dir=$(mktemp -d /tmp/boa-fi-source-manifest.XXXXXX)
trap 'rm -rf "$work_dir"' EXIT

build_tracked_scope() {
  local name=$1
  local selection=$2
  shift 2
  local list_file="$work_dir/$name.paths"
  local checksum_file="$work_dir/$name.sha256"
  (
    cd "$PROJECT_ROOT"
    git ls-files -z -- "$@" | sort -z >"$list_file"
    [[ -s "$list_file" ]]
    xargs -0 sha256sum <"$list_file" >"$checksum_file"
  )
  local digest
  digest=$(sha256sum "$checksum_file" | awk '{print $1}')
  jq -Rn \
    --arg digest "$digest" \
    --arg selection "$selection" \
    --arg algorithm "SHA-256" \
    --arg aggregateAlgorithm "SHA-256 of path-sorted sha256sum lines (<file-sha256><two spaces><relative-path><newline>)" \
    '[inputs | select(length > 0) | capture("^(?<sha256>[0-9a-f]{64})  (?<path>.*)$")] as $files |
     {digest:$digest,algorithm:$algorithm,aggregateAlgorithm:$aggregateAlgorithm,pathSelection:$selection,fileCount:($files|length),files:$files}' \
    <"$checksum_file" >"$work_dir/$name.json"
}

build_explicit_scope() {
  local name=$1
  local selection=$2
  shift 2
  local checksum_file="$work_dir/$name.sha256"
  (
    cd "$PROJECT_ROOT"
    sha256sum "$@" >"$checksum_file"
  )
  local digest
  digest=$(sha256sum "$checksum_file" | awk '{print $1}')
  jq -Rn \
    --arg digest "$digest" \
    --arg selection "$selection" \
    --arg algorithm "SHA-256" \
    --arg aggregateAlgorithm "SHA-256 of the listed sha256sum lines in declared order" \
    '[inputs | select(length > 0) | capture("^(?<sha256>[0-9a-f]{64})  (?<path>.*)$")] as $files |
     {digest:$digest,algorithm:$algorithm,aggregateAlgorithm:$aggregateAlgorithm,pathSelection:$selection,fileCount:($files|length),files:$files}' \
    <"$checksum_file" >"$work_dir/$name.json"
}

build_tracked_scope \
  runtime \
  "git ls-files -- backend database frontend/src infrastructure scripts tests; paths sorted bytewise" \
  backend database frontend/src infrastructure scripts tests
build_tracked_scope \
  migration \
  "git ls-files -- backend database infrastructure scripts tests; paths sorted bytewise" \
  backend database infrastructure scripts tests
build_explicit_scope \
  security \
  "Explicit ordered security inputs declared by scripts/validate-security-scans.sh" \
  .gitleaks.toml \
  backend/pyproject.toml \
  frontend/package-lock.json \
  infrastructure/docker-compose.yml \
  infrastructure/docker/backend.Dockerfile \
  infrastructure/docker/frontend.Dockerfile \
  scripts/common.sh \
  scripts/validate-security-scans.sh

mkdir -p "$(dirname -- "$OUTPUT")"
jq -n \
  --arg revision "$(git -C "$PROJECT_ROOT" rev-parse HEAD)" \
  --arg branch "$(git -C "$PROJECT_ROOT" branch --show-current)" \
  --arg generator "scripts/generate-financial-intelligence-source-manifest.sh" \
  --slurpfile runtime "$work_dir/runtime.json" \
  --slurpfile migration "$work_dir/migration.json" \
  --slurpfile security "$work_dir/security.json" \
  '{schemaVersion:"1.0",revision:$revision,branch:$branch,generator:$generator,sourceTree:"FUNCTIONAL_PATHS_CLEAN",scopes:{runtime:$runtime[0],migration:$migration[0],security:$security[0]}}' \
  >"$OUTPUT"

jq -e '.schemaVersion=="1.0" and .sourceTree=="FUNCTIONAL_PATHS_CLEAN" and all(.scopes[]; .fileCount > 0 and (.digest|length)==64)' "$OUTPUT" >/dev/null
printf 'PASS source_manifest=%s revision=%s\n' "$OUTPUT" "$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
