#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_command docker
require_command jq
load_local_env

OUTPUT_FILE=${OPERATIONAL_EVIDENCE_FILE:-$PROJECT_ROOT/docs/evidence/operations/RESULTATS-READINESS-OPERATIONNELLE.json}
RUN_ID="operational-readiness-$(date -u +%Y%m%dT%H%M%SZ)-$$"
CORRELATION_ID="${RUN_ID}-correlation"
POSTGRES_WAS_STOPPED=false
mkdir -p "$(dirname -- "$OUTPUT_FILE")"

recover_postgres() {
  if [[ "$POSTGRES_WAS_STOPPED" == true ]]; then
    compose start postgres >/dev/null 2>&1 || true
    wait_for_healthy postgres 120 >/dev/null 2>&1 || true
  fi
}
trap recover_postgres EXIT

request_from_customer() {
  local path=$1 correlation=${2:-$CORRELATION_ID}
  compose exec -T customer python - "$path" "$correlation" <<'PY'
import json
import sys
import urllib.error
import urllib.request

path, correlation_id = sys.argv[1:]
request = urllib.request.Request(
    f"http://127.0.0.1:8080{path}",
    headers={"X-Correlation-ID": correlation_id},
)
try:
    response = urllib.request.urlopen(request, timeout=10)
except urllib.error.HTTPError as exc:
    response = exc
body = response.read().decode("utf-8")
print(
    json.dumps(
        {
            "status": response.status,
            "correlationId": response.headers.get("X-Correlation-ID"),
            "body": body,
        },
        separators=(",", ":"),
    )
)
PY
}

metric_value() {
  local payload=$1 metric=$2
  printf '%s\n' "$payload" | jq -r '.body' | awk -v name="$metric" '$1 ~ ("^" name "\\{") {print $2}'
}

compose up --detach --build postgres keycloak customer
wait_for_healthy postgres 120
wait_for_healthy keycloak 180
wait_for_healthy customer 180

log_since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
metrics_before=$(request_from_customer /metrics "${CORRELATION_ID}-metrics-before")
requests_before=$(metric_value "$metrics_before" boa_http_requests_total)
[[ "$requests_before" =~ ^[0-9]+$ ]]

health=$(request_from_customer /health "$CORRELATION_ID")
ready_initial=$(request_from_customer /ready "${CORRELATION_ID}-ready-initial")
[[ $(jq -r '.status' <<<"$health") -eq 200 ]]
[[ $(jq -r '.status' <<<"$ready_initial") -eq 200 ]]
[[ $(jq -r '.correlationId' <<<"$health") == "$CORRELATION_ID" ]]
[[ $(jq -r '.body | fromjson | .status' <<<"$health") == healthy ]]
[[ $(jq -r '.body | fromjson | .status' <<<"$ready_initial") == ready ]]

metrics_after=$(request_from_customer /metrics "${CORRELATION_ID}-metrics-after")
requests_after=$(metric_value "$metrics_after" boa_http_requests_total)
[[ "$requests_after" =~ ^[0-9]+$ ]]
[[ "$requests_after" -gt "$requests_before" ]]

log_matches=$(compose logs --no-color --since "$log_since" customer | grep -c "$CORRELATION_ID" || true)
[[ "$log_matches" -ge 1 ]]

compose stop postgres >/dev/null
POSTGRES_WAS_STOPPED=true
failure_started_ns=$(date +%s%N)
readiness_down=$(request_from_customer /ready "${CORRELATION_ID}-db-down")
health_down=$(request_from_customer /health "${CORRELATION_ID}-health-db-down")
[[ $(jq -r '.status' <<<"$readiness_down") -eq 503 ]]
[[ $(jq -r '.body | fromjson | .code' <<<"$readiness_down") == DATABASE_UNAVAILABLE ]]
[[ $(jq -r '.status' <<<"$health_down") -eq 200 ]]

compose start postgres >/dev/null
wait_for_healthy postgres 120
POSTGRES_WAS_STOPPED=false

ready_recovered=''
for _attempt in $(seq 1 30); do
  ready_recovered=$(request_from_customer /ready "${CORRELATION_ID}-recovered")
  if [[ $(jq -r '.status' <<<"$ready_recovered") -eq 200 ]]; then
    break
  fi
  sleep 1
done
failure_finished_ns=$(date +%s%N)
[[ $(jq -r '.status' <<<"$ready_recovered") -eq 200 ]]
[[ $(jq -r '.body | fromjson | .status' <<<"$ready_recovered") == ready ]]
recovery_duration_ms=$(((failure_finished_ns - failure_started_ns) / 1000000))

base_commit=$(git -C "$PROJECT_ROOT" rev-parse HEAD)
source_digest=$(
  cd "$PROJECT_ROOT"
  sha256sum \
    backend/src/boa_oi/platform.py \
    infrastructure/docker-compose.yml \
    infrastructure/docker/backend.Dockerfile \
    scripts/common.sh \
    scripts/validate-operational-readiness.sh \
    | sha256sum | awk '{print $1}'
)
backend_base_image=$(awk '/^FROM / {print $2; exit}' "$PROJECT_ROOT/infrastructure/docker/backend.Dockerfile")
generated_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

jq -n \
  --arg runId "$RUN_ID" \
  --arg generatedAt "$generated_at" \
  --arg baseCommit "$base_commit" \
  --arg sourceDigest "$source_digest" \
  --arg backendBaseImage "$backend_base_image" \
  --arg correlationId "$CORRELATION_ID" \
  --argjson logMatches "$log_matches" \
  --argjson requestsBefore "$requests_before" \
  --argjson requestsAfter "$requests_after" \
  --argjson recoveryDurationMs "$recovery_duration_ms" \
  '{runId:$runId,generatedAt:$generatedAt,status:"PASS",scope:"LOCAL_SYNTHETIC_OPERATIONAL_READINESS",sourceRevision:{baseCommit:$baseCommit,sourceDigest:$sourceDigest,backendBaseImage:$backendBaseImage},checks:{healthEndpoint:"PASS",readyWithDatabase:"PASS",structuredCorrelationLog:"PASS",correlationHeader:"PASS",requestMetricIncrement:"PASS",readinessFailsWhenDatabaseStops:"PASS",livenessRemainsHealthyWhenDatabaseStops:"PASS",readinessRecoversAfterDatabaseRestart:"PASS"},observations:{correlationId:$correlationId,matchingLogLines:$logMatches,requestsBefore:$requestsBefore,requestsAfter:$requestsAfter,recoveryDurationMs:$recoveryDurationMs},limitations:["Panne PostgreSQL locale contrôlée sur données synthétiques; aucun trafic ou objectif BOA réel.","La durée de récupération observée ne constitue ni SLO, ni RTO, ni engagement de disponibilité.","La preuve valide logs corrélés, métriques minimales, liveness/readiness et récupération DB; centralisation, alerting externe, traces distribuées, HA et SIEM restent NON IMPLEMENTES.","Les seuils et responsabilités d alerte restent A VALIDER AVEC BOA."]}' >"$OUTPUT_FILE"

echo "[operational-readiness] PASS: $OUTPUT_FILE"
