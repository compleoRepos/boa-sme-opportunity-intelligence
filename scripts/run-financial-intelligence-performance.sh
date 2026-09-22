#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
PROJECT=${FI_COMPOSE_PROJECT:-boa_lot16_validation}
ENV_FILE=${FI_COMPOSE_ENV_FILE:-/tmp/boa_lot16_validation.env}
OVERRIDE_FILE=${FI_COMPOSE_OVERRIDE_FILE:-/tmp/boa_lot16_validation.override.yml}
EVIDENCE_DIR=${FI_EVIDENCE_DIR:-$PROJECT_ROOT/docs/evidence/financial-intelligence}
FRONTEND_ORIGIN=${FI_FRONTEND_ORIGIN:-http://127.0.0.1:3716}
KEYCLOAK_ORIGIN=${FI_KEYCLOAK_ORIGIN:-http://127.0.0.1:8717}
ITERATIONS=${FI_PERFORMANCE_ITERATIONS:-5}
SAMPLE_INTERVAL_SECONDS=${FI_RESOURCE_SAMPLE_INTERVAL_SECONDS:-2}

compose=(sudo -n docker compose --project-name "$PROJECT" --file "$PROJECT_ROOT/infrastructure/docker-compose.yml")
if [[ -f "$OVERRIDE_FILE" ]]; then
  compose+=(--file "$OVERRIDE_FILE")
fi
compose+=(--env-file "$ENV_FILE")

mkdir -p "$EVIDENCE_DIR"
raw_samples=$(mktemp)
playwright_json="$EVIDENCE_DIR/RESULTATS-PLAYWRIGHT-PERFORMANCE-FI.json"
resources_json="$EVIDENCE_DIR/RESULTATS-RESSOURCES-FI.json"
services=(financial-intelligence api-gateway customer analytics signal opportunity portfolio)
container_ids=()
for service in "${services[@]}"; do
  id=$("${compose[@]}" ps -q "$service")
  [[ -n "$id" ]]
  container_ids+=("$id")
done

sample_resources() {
  while true; do
    sampled_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    sudo -n docker stats --no-stream --format '{{json .}}' "${container_ids[@]}" \
      | jq -c --arg sampledAt "$sampled_at" '. + {sampledAt:$sampledAt}' \
      >>"$raw_samples"
    sleep "$SAMPLE_INTERVAL_SECONDS"
  done
}

sample_resources &
sampler_pid=$!
cleanup() {
  if [[ "${sampler_pid:-0}" -gt 1 ]]; then
    kill "$sampler_pid" >/dev/null 2>&1 || true
    wait "$sampler_pid" >/dev/null 2>&1 || true
  fi
  rm -f "$raw_samples"
}
trap cleanup EXIT

branch=$(git -C "$PROJECT_ROOT" branch --show-current)
revision=$(git -C "$PROJECT_ROOT" rev-parse HEAD)
code_digest=$(
  cd "$PROJECT_ROOT"
  git ls-files -z --cached --others --exclude-standard \
    backend database frontend/src infrastructure scripts tests \
    | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}'
)

(
  cd "$PROJECT_ROOT/tests/e2e"
  E2E_DEV_MODE=false \
  E2E_BASE_URL="$FRONTEND_ORIGIN" \
  E2E_KEYCLOAK_ORIGIN="$KEYCLOAK_ORIGIN" \
  FI_EVIDENCE_DIR="$EVIDENCE_DIR" \
  FI_PERFORMANCE_ITERATIONS="$ITERATIONS" \
  FI_SOURCE_BRANCH="$branch" \
  FI_SOURCE_REVISION="$revision" \
  FI_CODE_DIGEST="$code_digest" \
  FI_DIGEST_SCOPE="runtime" \
  FI_DIGEST_MANIFEST="SOURCE-MANIFEST-FI.json" \
  FI_PORTFOLIO_CONCURRENCY=${FI_PORTFOLIO_CONCURRENCY:-20} \
  ./node_modules/.bin/playwright test financial-intelligence-performance.spec.ts \
    --config playwright.config.ts --reporter=json >"$playwright_json"
)

kill "$sampler_pid" >/dev/null 2>&1 || true
wait "$sampler_pid" >/dev/null 2>&1 || true
sampler_pid=0

jq -s \
  --arg generatedAt "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg branch "$branch" \
  --arg revision "$revision" \
  --arg codeDigest "$code_digest" \
  --argjson interval "$SAMPLE_INTERVAL_SECONDS" \
  '{
    schemaVersion:"1.0",
    status:(if length > 0 then "PASS" else "FAIL" end),
    generatedAt:$generatedAt,
    source:{branch:$branch,revision:$revision,codeDigest:$codeDigest,digestScope:"runtime",digestManifest:"SOURCE-MANIFEST-FI.json",digestAlgorithm:"SHA-256 of path-sorted sha256sum lines"},
    sampleIntervalSeconds:$interval,
    sampleCount:length,
    services:(group_by(.Name) | map({
      container:.[0].Name,
      samples:length,
      maxCpuPercent:(map(.CPUPerc | rtrimstr("%") | tonumber) | max),
      maxMemoryPercent:(map(.MemPerc | rtrimstr("%") | tonumber) | max),
      peakMemoryUsage:(max_by(.MemPerc | rtrimstr("%") | tonumber).MemUsage)
    })),
    limitations:[
      "Mesure mono-noeud Docker Compose sur donnees synthetiques.",
      "Les valeurs CPU et memoire ne constituent pas un SLO BOA.",
      "Tous les seuils sont une HYPOTHESE A VALIDER AVEC BOA."
    ]
  }' "$raw_samples" >"$resources_json"

jq -e '.status == "PASS" and (.results | length) == 4 and all(.results[]; .thresholdStatus == "PASS")' \
  "$EVIDENCE_DIR/RESULTATS-PERFORMANCE-FI.json" >/dev/null
jq -e '.status == "PASS" and .sampleCount > 0 and (.services | length) == 7' \
  "$resources_json" >/dev/null

echo "[fi-performance] PASS: $EVIDENCE_DIR/RESULTATS-PERFORMANCE-FI.json"
echo "[fi-performance] PASS: $resources_json"
