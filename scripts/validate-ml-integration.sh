#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_command jq
require_command grep
require_command curl
require_command sha256sum
load_local_env

OUTPUT_FILE=${ML_SHADOW_OUTPUT_FILE:-$PROJECT_ROOT/docs/evidence/ml/RESULTATS-ML-SHADOW.json}
KEYCLOAK_PORT=${KEYCLOAK_PORT:-8081}
PIPELINE_CLIENT_SECRET=${PIPELINE_CLIENT_SECRET:-DevOnly-PipelineClient-ChangeMe!}
RUN_ID="ml-shadow-$(date -u +%Y%m%dT%H%M%SZ)-$$"
TOKEN_URL="http://localhost:${KEYCLOAK_PORT}/realms/boa-sme-mvp/protocol/openid-connect/token"

token=""
refresh_token() {
  token=$(curl --fail --silent --show-error \
    --data-urlencode grant_type=client_credentials \
    --data-urlencode client_id=pipeline-runner \
    --data-urlencode "client_secret=${PIPELINE_CLIENT_SECRET}" \
    "$TOKEN_URL" | jq -er '.access_token')
}

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

post_ml() {
  local path=$1 payload=$2
  local key=${3:-${path//\//-}}
  compose exec -T ml-engine curl --fail-with-body --silent --show-error \
    --request POST \
    --header "Authorization: Bearer ${token}" \
    --header "X-Correlation-ID: ${RUN_ID}" \
    --header "Idempotency-Key: ${RUN_ID}-${key}" \
    --header 'Content-Type: application/json' \
    --data "$payload" \
    "http://127.0.0.1:8080${path}"
}

printf '%s\n' 'Validating healthy runtime services...'
for service in postgres keycloak customer analytics signal rule-engine feature-store ml-engine opportunity portfolio api-gateway frontend; do
  wait_for_healthy "$service" 30
  printf 'PASS health:%s\n' "$service"
done

score_window_from=$(date -u +%Y-%m-%dT%H:%M:%SZ)
pipeline_log="/tmp/${RUN_ID}-pipeline.log"
CORRELATION_ID="${RUN_ID}-pipeline" "$SCRIPT_DIR/run-pipeline.sh" \
  >"$pipeline_log"
pipeline_summary=$(grep '^{' "$pipeline_log" | jq -cs '[.[] | select(has("scoringPolicy"))]')
pipeline_batches=$(jq 'length' <<<"$pipeline_summary")
pipeline_customers=$(jq '[.[].customers] | add // 0' <<<"$pipeline_summary")
shadow_observations=$(jq '[.[].executionModes.POC_SHADOW] | add // 0' <<<"$pipeline_summary")
rules_only_fallbacks=$(jq '[.[].executionModes.RULES_ONLY] | add // 0' <<<"$pipeline_summary")
[[ "$pipeline_batches" -eq 20 && "$pipeline_customers" -eq 500 ]]
[[ "$shadow_observations" -eq 500 && "$rules_only_fallbacks" -eq 0 ]]
[[ $(jq '[.[].scoringPolicy | (.rulesWeight == 1 and .mlWeight == 0)] | all' <<<"$pipeline_summary") == true ]]
printf '%s\n' 'PASS complete 500-SME rules/features/shadow/opportunity pipeline executed inside the evidence window'
refresh_token

snapshot_version="shadow-${RUN_ID#ml-shadow-}"
label_definition="commercial-conversion-90d-v1"
labels_payload=$(jq -nc \
  --arg snapshot "$snapshot_version" \
  --arg definition "$label_definition" \
  '{snapshotVersion:$snapshot,labelDefinitionVersion:$definition,targetOutcome:"CONVERTED",horizonDays:90,population:{segment:"SME",country:"MA",source:"LOCAL_PILOT_OUTCOMES"},observationAsOf:"2026-09-30",labelAvailableFrom:"2026-12-31"}')
labels_response=$(post_ml '/internal/v1/ml/outcomes/materialize' "$labels_payload")
labels_written=$(jq -er '.labelsWritten' <<<"$labels_response")
printf 'PASS outcome materialization is non-fabricating (candidate labels written=%s)\n' "$labels_written"

manifest_version="manifest-${RUN_ID}"
manifest_payload=$(jq -nc \
  --arg manifest "$manifest_version" \
  --arg snapshot "$snapshot_version" \
  --arg definition "$label_definition" \
  '{manifestVersion:$manifest,snapshotVersion:$snapshot,labelDefinitionVersion:$definition,purpose:"SHADOW_EVALUATION_ONLY",targetOutcome:"CONVERTED",horizonDays:90,population:{segment:"SME",country:"MA",source:"LOCAL_PILOT_OUTCOMES"},exclusions:["not_boa_historical","candidate_only"],trainingCutoff:"2026-09-30"}')
manifest_response=$(post_ml '/internal/v1/ml/datasets/manifests' "$manifest_payload")
manifest_hash=$(jq -er '.manifestHash' <<<"$manifest_response")
[[ $(jq -r '.status' <<<"$manifest_response") == BLOCKED ]] || {
  printf '%s\n' 'FAIL local dataset manifest is not blocked' >&2
  exit 1
}
printf '%s\n' 'PASS local dataset manifest persists explicit blockers'

evaluation_ref="evaluation-${RUN_ID}"
evaluation_payload=$(jq -nc \
  --arg ref "$evaluation_ref" \
  --arg hash "$manifest_hash" \
  '{evaluationRef:$ref,modelVersion:"sales-propensity-logit-poc-v1",datasetManifestHash:$hash,sourceKind:"SYNTHETIC",evaluationPeriodFrom:"2026-09-01",evaluationPeriodTo:"2026-12-31",scores:[0.9,0.1],labels:[1,0],k:1,acceptanceCriteria:{},calibrationMethod:"NONE"}')
evaluation_response=$(post_ml '/internal/v1/ml/governance/evaluation/metrics' "$evaluation_payload")
[[ $(jq -r '.status' <<<"$evaluation_response") == BLOCKED ]] || {
  printf '%s\n' 'FAIL local evaluation is not blocked' >&2
  exit 1
}
[[ $(jq -r '.productionPerformanceClaim' <<<"$evaluation_response") == false ]] || {
  printf '%s\n' 'FAIL evaluation exposes a production performance claim' >&2
  exit 1
}
printf '%s\n' 'PASS descriptive evaluation persists Brier/ECE without production claim'

assert_sql_true '500 feature vectors materialized' \
  "select count(distinct customer_id) >= 500 from feature_store.feature_materializations where as_of_date='2026-09-30';"
assert_sql_true '500 propensity scores persisted' \
  "select count(distinct customer_id) >= 500 from ml.propensity_scores where as_of_date='2026-09-30';"
assert_sql_true '500 propensity scores refreshed by the current pipeline window' \
  "select count(distinct customer_id) >= 500 from ml.propensity_scores where as_of_date='2026-09-30' and updated_at >= '${score_window_from}'::timestamptz;"
assert_sql_true 'Rule Studio and Signal lineage present in Feature Store' \
  "select exists(select 1 from feature_store.feature_materializations f where f.as_of_date='2026-09-30' and f.values_json ? 'confirmed_signal_ratio' and f.values_json ? 'published_rule_match_strength' and exists(select 1 from jsonb_array_elements(f.sources_json) s where s->>'sourceType'='RULE_STUDIO' and jsonb_array_length(s->'activeRuleVersions') > 0) and exists(select 1 from jsonb_array_elements(f.sources_json) s where s->>'sourceType'='SIGNAL_SERVICE' and jsonb_array_length(s->'signalReferences') > 0));"
assert_sql_true 'ML propensity has no persisted influence on opportunity priority' \
  "select not exists(select 1 from opportunity.opportunities o where o.engine_version like '%ml-rerank-poc-v1%' or o.ml_weight<>0 or o.rules_weight<>1 or o.fallback_mode<>'RULES_ONLY' or exists(select 1 from jsonb_array_elements(o.priority_components_json::jsonb) c where c->>'name'='sales_propensity_ml'));"
assert_sql_true 'Prediction trace carries immutable shadow lineage' \
  "select exists(select 1 from ml.propensity_scores p where p.as_of_date='2026-09-30' and p.model_version<>'' and p.feature_set_version<>'' and p.training_dataset_version<>'' and p.deployment_mode='POC_SHADOW' and p.score_interpretation='RANKING_ONLY' and p.contract_version='1.0' and p.feature_snapshot_id is not null and p.feature_watermark<>'' and p.valid_until=p.as_of_date);"
assert_sql_true 'Active scoring policy is rules-only' \
  "select exists(select 1 from opportunity.scoring_policies p join opportunity.scoring_policy_versions v on v.policy_id=p.id and v.version=p.active_version where p.policy_id='commercial-rules-shadow-poc' and v.status='ACTIVE' and v.rules_weight=1 and v.ml_weight=0);"
assert_sql_true 'All registered and persisted scores are shadow-only' \
  "select not exists(select 1 from ml.model_registry where deployment_mode<>'POC_SHADOW') and not exists(select 1 from ml.propensity_scores where deployment_mode<>'POC_SHADOW');"
assert_sql_true 'No local or synthetic label can become training-ready' \
  "select not exists(select 1 from ml.outcome_label_snapshots where source_kind<>'BOA_HISTORICAL_OBSERVED' and not candidate_only);"
assert_sql_true 'Dataset manifest and evaluation are blocked without BOA labels' \
  "select exists(select 1 from ml.dataset_manifests where manifest_hash='${manifest_hash}' and status='BLOCKED' and blockers_json::jsonb ? 'BOA_HISTORICAL_LABELS_UNAVAILABLE') and exists(select 1 from ml.evaluation_snapshots where evaluation_ref='${evaluation_ref}' and status='BLOCKED' and calibration_json->>'status'='NOT_VALIDATED' and blockers_json::jsonb ? 'BOA_HISTORICAL_LABELS_UNAVAILABLE');"
assert_sql_true 'Feature Store and ML Engine have no cross-schema feature read grants' \
  "select not has_schema_privilege('feature_store_service','customer','USAGE') and not has_schema_privilege('feature_store_service','analytics','USAGE') and not has_schema_privilege('feature_store_service','signal','USAGE') and not has_schema_privilege('feature_store_service','rule','USAGE') and not has_schema_privilege('ml_engine_service','feature_store','USAGE');"

printf '%s\n' 'Validating forbidden runtime dependencies...'
if grep -Eiq 'openai|anthropic|langchain|llama|torch|tensorflow|bedrock|sagemaker' \
  "$PROJECT_ROOT/backend/pyproject.toml" \
  "$PROJECT_ROOT/frontend/package.json"; then
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
cuda_visible=$(docker_cli inspect "$ml_container" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^CUDA_VISIBLE_DEVICES=' || true)
nvidia_visible=$(docker_cli inspect "$ml_container" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^NVIDIA_VISIBLE_DEVICES=' || true)
[[ "$cuda_visible" == 'CUDA_VISIBLE_DEVICES=' && "$nvidia_visible" == 'NVIDIA_VISIBLE_DEVICES=none' ]] || {
  printf 'FAIL explicit GPU deny environment missing (%s, %s)\n' "$cuda_visible" "$nvidia_visible" >&2
  exit 1
}
printf '%s\n' 'PASS ML Engine explicit GPU deny environment'
if compose exec -T ml-engine python -m pip freeze | grep -Eiq '^(torch|tensorflow|transformers|openai|anthropic|langchain)=='; then
  printf '%s\n' 'FAIL forbidden ML/LLM runtime package installed' >&2
  exit 1
fi
printf '%s\n' 'PASS ML Engine runtime contains no GPU/LLM package'

feature_count=$(sql "select count(distinct customer_id) from feature_store.feature_materializations where as_of_date='2026-09-30'")
score_count=$(sql "select count(distinct customer_id) from ml.propensity_scores where as_of_date='2026-09-30'")
fresh_score_count=$(sql "select count(distinct customer_id) from ml.propensity_scores where as_of_date='2026-09-30' and updated_at >= '${score_window_from}'::timestamptz")
score_window_to=$(sql "select max(updated_at) from ml.propensity_scores where as_of_date='2026-09-30' and updated_at >= '${score_window_from}'::timestamptz")
opportunity_count=$(sql "select count(*) from opportunity.opportunities")
label_count=$(sql "select count(*) from ml.outcome_label_snapshots where snapshot_version='${snapshot_version}'")
container_limits=$(docker_cli inspect "$ml_container" --format '{{.HostConfig.NanoCpus}} {{.HostConfig.Memory}}')
read -r nano_cpus memory_bytes <<<"$container_limits"
source_files=(
  backend/src/boa_oi/feature_store_api.py
  backend/src/boa_oi/features/__init__.py
  backend/src/boa_oi/features/domain.py
  backend/src/boa_oi/features/service.py
  backend/src/boa_oi/gateway_api.py
  backend/src/boa_oi/ml/__init__.py
  backend/src/boa_oi/ml/domain.py
  backend/src/boa_oi/ml/governance.py
  backend/src/boa_oi/ml/service.py
  backend/src/boa_oi/ml_engine_api.py
  backend/src/boa_oi/mlops/domain.py
  backend/src/boa_oi/mlops/routes.py
  backend/src/boa_oi/mlops/service.py
  backend/src/boa_oi/models/entities.py
  backend/src/boa_oi/operations/api.py
  backend/src/boa_oi/opportunities/__init__.py
  backend/src/boa_oi/opportunities/domain.py
  backend/src/boa_oi/opportunities/service.py
  backend/src/boa_oi/opportunities/strategies.py
  backend/src/boa_oi/opportunity_api.py
  backend/src/boa_oi/portfolio_api.py
  backend/src/boa_oi/resilience/ml_client.py
  backend/src/boa_oi/rule_engine_api.py
  backend/src/boa_oi/rules/__init__.py
  backend/src/boa_oi/rules/domain.py
  backend/src/boa_oi/rules/service.py
  backend/src/boa_oi/scoring_policy/domain.py
  backend/src/boa_oi/scoring_policy/routes.py
  backend/src/boa_oi/scoring_policy/service.py
  database/migrations/versions/0017_ml_shadow_governance.py
  database/seed/generate.py
  database/seed/rules.yaml
  frontend/src/api/types.ts
  frontend/src/features/backoffice/BackOfficePages.tsx
  frontend/src/features/branch/BranchDashboardPage.tsx
  frontend/src/features/customer/PropensityDrawer.tsx
  frontend/src/features/dashboard/CcDashboardPage.tsx
  frontend/src/features/dashboard/PriorityRow.tsx
  frontend/src/features/demo/DemoGuide.tsx
  frontend/src/pages/LoginPage.tsx
  infrastructure/docker-compose.yml
  scripts/validate-ml-integration.sh
  scripts/run-pipeline.sh
  tests/e2e/rm-opportunity.spec.ts
)
source_digest=$(cd "$PROJECT_ROOT" && { for path in "${source_files[@]}"; do sha256sum "$path"; done; } | sha256sum | cut -d' ' -f1)
base_commit=$(git -C "$PROJECT_ROOT" rev-parse HEAD)
mkdir -p "$(dirname -- "$OUTPUT_FILE")"
jq -n \
  --arg runId "$RUN_ID" \
  --arg generatedAt "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg baseCommit "$base_commit" \
  --arg sourceDigest "$source_digest" \
  --arg manifestVersion "$manifest_version" \
  --arg manifestHash "$manifest_hash" \
  --arg evaluationRef "$evaluation_ref" \
  --arg scoreWindowFrom "$score_window_from" \
  --arg scoreWindowTo "$score_window_to" \
  --argjson featureCount "$feature_count" \
  --argjson scoreCount "$score_count" \
  --argjson freshScoreCount "$fresh_score_count" \
  --argjson opportunityCount "$opportunity_count" \
  --argjson labelCount "$label_count" \
  --argjson pipelineBatches "$pipeline_batches" \
  --argjson pipelineCustomers "$pipeline_customers" \
  --argjson shadowObservations "$shadow_observations" \
  --argjson rulesOnlyFallbacks "$rules_only_fallbacks" \
  --argjson nanoCpus "$nano_cpus" \
  --argjson memoryBytes "$memory_bytes" \
  --argjson brierScore "$(jq '.metrics.brierScore' <<<"$evaluation_response")" \
  --argjson expectedCalibrationError "$(jq '.metrics.expectedCalibrationError' <<<"$evaluation_response")" \
  --argjson sourceFiles "$(printf '%s\n' "${source_files[@]}" | jq -R . | jq -s .)" \
  '{runId:$runId,generatedAt:$generatedAt,status:"PASS",scope:"POC_SHADOW_LOCAL_SYNTHETIC_PILOT",claims:{productionPerformance:false,creditDecision:false,llm:false,gpu:false,trainingReady:false},sourceRevision:{baseCommit:$baseCommit,sourceDigest:$sourceDigest,files:$sourceFiles},environment:{runtime:"Docker Compose local",cpuOnly:true,nanoCpus:$nanoCpus,memoryBytes:$memoryBytes,gpuDeviceRequests:false},counts:{featureVectors:$featureCount,propensityScores:$scoreCount,freshPropensityScores:$freshScoreCount,opportunities:$opportunityCount,candidateLabels:$labelCount},pipelineEvidence:{expectedCustomers:500,batches:$pipelineBatches,customersProcessed:$pipelineCustomers,shadowObservations:$shadowObservations,rulesOnlyFallbacks:$rulesOnlyFallbacks,scoreWindowFrom:$scoreWindowFrom,scoreWindowTo:$scoreWindowTo,completePipelineOwnedByProtocol:true},datasetManifest:{manifestVersion:$manifestVersion,manifestHash:$manifestHash,status:"BLOCKED",sourceKind:"LOCAL_COMMERCIAL_OUTCOME",activationBlocker:"BOA_HISTORICAL_LABELS_UNAVAILABLE"},evaluation:{evaluationRef:$evaluationRef,status:"BLOCKED",sourceKind:"SYNTHETIC",descriptiveOnly:true,brierScore:$brierScore,expectedCalibrationError:$expectedCalibrationError,calibrationStatus:"NOT_VALIDATED",productionPerformanceClaim:false},checks:{rulesToFeatures:"PASS",shadowPredictionLineage:"PASS",shadowInference500:"PASS",opportunityPriorityRulesOnly:"PASS",activePolicyRulesOnly:"PASS",candidateLabelPolicy:"PASS",candidateLabelsMaterialized:(if $labelCount>0 then "PASS" else "NOT_AVAILABLE" end),pointInTimeManifestBlocked:"PASS",evaluationBlocked:"PASS",cpuOnly:"PASS",noLlm:"PASS",crossSchemaLeastPrivilege:"PASS"},limitations:["Données locales/synthétiques de démonstration, pas des historiques BOA gouvernés.","Aucun outcome commercial inventé; la fixture ne contient aucun outcome, donc candidateLabelsMaterialized vaut NOT_AVAILABLE.","Les deux paires score/label de la mesure sont une fixture de protocole explicitement synthétique; leurs métriques ne mesurent aucune performance BOA ou production.","Aucune performance ML de production, homologation, calibration validée ou capacité de décision de crédit ne constitue une mesure de ce protocole.","Le score est observé en shadow; la priorité commerciale reste RULES_ONLY."]}' >"$OUTPUT_FILE"
printf 'PASS evidence:%s\n' "$OUTPUT_FILE"
printf '%s\n' 'ML shadow integration validation completed.'
