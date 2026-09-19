#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_command jq
require_command grep

sql() {
  compose exec -T postgres psql \
    --username "${POSTGRES_ADMIN_USER:-boa_admin}" \
    --dbname "${POSTGRES_DB:-boa_sme}" \
    --tuples-only --no-align --set=ON_ERROR_STOP=1 \
    --command "$1"
}

assert_sql_true() {
  local label=$1 query=$2 value
  value=$(sql "$query")
  if [[ "$value" != "t" ]]; then
    printf 'FAIL %s (result=%s)\n' "$label" "$value" >&2
    return 1
  fi
  printf 'PASS %s\n' "$label"
}

printf '%s\n' 'Validating healthy runtime services...'
for service in postgres keycloak customer analytics signal rule-engine feature-store ml-engine opportunity portfolio api-gateway frontend; do
  wait_for_healthy "$service" 30
  printf 'PASS health:%s\n' "$service"
done

assert_sql_true '500 feature vectors materialized' \
  "select count(distinct customer_id) >= 500 from feature_store.feature_materializations where as_of_date='2026-09-30';"
assert_sql_true '500 propensity scores persisted' \
  "select count(distinct customer_id) >= 500 from ml.propensity_scores where as_of_date='2026-09-30';"
assert_sql_true 'Rule Studio and Signal lineage present in Feature Store' \
  "select exists(select 1 from feature_store.feature_materializations f where f.as_of_date='2026-09-30' and f.values_json ? 'confirmed_signal_ratio' and f.values_json ? 'published_rule_match_strength' and exists(select 1 from jsonb_array_elements(f.sources_json) s where s->>'sourceType'='RULE_STUDIO' and jsonb_array_length(s->'activeRuleVersions') > 0) and exists(select 1 from jsonb_array_elements(f.sources_json) s where s->>'sourceType'='SIGNAL_SERVICE' and jsonb_array_length(s->'signalReferences') > 0));"
assert_sql_true 'ML propensity influences persisted opportunity priority' \
  "select exists(select 1 from opportunity.opportunities o where o.engine_version like '%ml-rerank-poc-v1%' and exists(select 1 from jsonb_array_elements(o.priority_components_json::jsonb) c where c->>'name'='sales_propensity_ml' and c ? 'model_version' and c ? 'feature_version' and c ? 'training_dataset_version' and c ? 'trace_id'));"
assert_sql_true 'Prediction trace carries model, feature, dataset and POC mode' \
  "select exists(select 1 from ml.propensity_scores p where p.as_of_date='2026-09-30' and p.model_version<>'' and p.feature_set_version<>'' and p.training_dataset_version<>'' and p.deployment_mode='POC_ASSISTIVE');"
assert_sql_true 'Commercial outcomes materialized as future labels only' \
  "select exists(select 1 from ml.outcome_label_snapshots where snapshot_version='synthetic-commercial-outcomes-v1');"
assert_sql_true 'Feature Store and ML Engine have no cross-schema feature read grants' \
  "select not has_schema_privilege('feature_store_service','customer','USAGE') and not has_schema_privilege('feature_store_service','analytics','USAGE') and not has_schema_privilege('feature_store_service','signal','USAGE') and not has_schema_privilege('feature_store_service','rule','USAGE') and not has_schema_privilege('ml_engine_service','feature_store','USAGE');"

printf '%s\n' 'Validating forbidden runtime dependencies...'
if grep -Eiq 'openai|anthropic|langchain|llama|cuda|torch|tensorflow|bedrock|sagemaker' \
  "$PROJECT_ROOT/backend/pyproject.toml" \
  "$PROJECT_ROOT/frontend/package.json" \
  "$PROJECT_ROOT/infrastructure/docker-compose.yml"; then
  printf '%s\n' 'FAIL forbidden LLM/GPU/cloud dependency found' >&2
  exit 1
fi
printf '%s\n' 'PASS no LLM/GPU/cloud runtime dependency'

ml_container=$(compose ps -q ml-engine)
device_requests=$(docker_cli inspect "$ml_container" --format '{{json .HostConfig.DeviceRequests}}')
[[ "$device_requests" == "null" || "$device_requests" == "[]" ]] || {
  printf 'FAIL ML Engine requests a device: %s\n' "$device_requests" >&2
  exit 1
}
printf '%s\n' 'PASS ML Engine requests no GPU/device'
printf '%s\n' 'ML integration validation completed.'
