#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_command docker
require_command curl
require_command jq
load_local_env

KEYCLOAK_PORT=${KEYCLOAK_PORT:-8081}
PIPELINE_CLIENT_SECRET=${PIPELINE_CLIENT_SECRET:-DevOnly-PipelineClient-ChangeMe!}
CORRELATION_ID=${CORRELATION_ID:-pipeline-$(date -u +%Y%m%dT%H%M%SZ)-$$}
OIDC_PUBLIC_ISSUER_URL=${OIDC_PUBLIC_ISSUER_URL:-http://localhost:${KEYCLOAK_PORT}/realms/boa-sme-mvp}
TOKEN_URL="${OIDC_PUBLIC_ISSUER_URL%/}/protocol/openid-connect/token"

token=""
refresh_token() {
  token=$(curl --fail --silent --show-error \
    --data-urlencode grant_type=client_credentials \
    --data-urlencode client_id=pipeline-runner \
    --data-urlencode "client_secret=${PIPELINE_CLIENT_SECRET}" \
    "$TOKEN_URL" | jq -er '.access_token')
}

echo "Obtaining short-lived pipeline token..."
refresh_token

post_internal() {
  local service="$1" path="$2" payload="${3-}"
  local key=${4:-${path//\//-}}
  [[ -n "$payload" ]] || payload='{}'
  # Chaque étape peut dépasser la courte durée de vie du jeton de démonstration.
  # Un jeton frais par appel évite qu'Opportunity hérite de celui utilisé avant Analytics/Signals.
  refresh_token
  echo "POST ${service}${path}"
  compose exec -T "$service" curl --fail-with-body --silent --show-error \
    --request POST \
    --header "Authorization: Bearer ${token}" \
    --header "X-Correlation-ID: ${CORRELATION_ID}" \
    --header "Idempotency-Key: ${CORRELATION_ID}-${service}-${key}" \
    --header 'Content-Type: application/json' \
    --data "$payload" \
    "http://127.0.0.1:8080${path}"
  printf '\n'
}

as_of=${AS_OF_DATE:-2026-09-30}
customer_count=${PIPELINE_CUSTOMER_COUNT:-500}
pipeline_stages=",${PIPELINE_STAGES:-analytics,signal,opportunity},"
customer_ids=$(jq -nc --argjson count "$customer_count" '[range(1; $count + 1) | "SME-" + (tostring | ("00000" + .)[-5:])]')

stage_enabled() {
  [[ "$pipeline_stages" == *",$1,"* ]]
}

if [[ "${IMPORT_VIA_ADAPTER:-false}" == "true" ]]; then
  refresh_token
  post_internal banking-integration "/internal/v1/imports/all" "$(jq -nc --arg from '2025-10-01' --arg to "$as_of" --argjson count "$customer_count" '{fromDate:$from,toDate:$to,customerCount:$count}')"
fi

batch_size=${PIPELINE_BATCH_SIZE:-25}
for ((start=0; start<customer_count; start+=batch_size)); do
  ids=$(jq -c --argjson start "$start" --argjson size "$batch_size" '.[$start:$start+$size]' <<<"$customer_ids")
  analytics_payload=$(jq -nc --argjson ids "$ids" --arg asOf "$as_of" '{customerIds:$ids,asOf:$asOf,periods:["7D","30D","90D","180D","365D"]}')
  signal_payload=$(jq -nc --argjson ids "$ids" --arg asOf "$as_of" '{customerIds:$ids,asOf:$asOf,periods:["90D"]}')
  opportunity_payload=$(jq -nc --argjson ids "$ids" --arg asOf "$as_of" '{customerIds:$ids,asOf:$asOf}')
  if stage_enabled analytics; then
    post_internal analytics "/internal/v1/analytics/recompute" "$analytics_payload" "batch-${start}"
  fi
  if stage_enabled signal; then
    post_internal signal "/internal/v1/signals/evaluate" "$signal_payload" "batch-${start}"
  fi
  if stage_enabled opportunity; then
    post_internal opportunity "/internal/v1/opportunities/generate" "$opportunity_payload" "batch-${start}"
  fi
done
echo "Pipeline submitted successfully (correlationId=${CORRELATION_ID})."
