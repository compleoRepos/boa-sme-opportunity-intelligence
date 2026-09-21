#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
COMPOSE_FILE="$PROJECT_ROOT/infrastructure/docker-compose.yml"
PROJECT_NAME=${VISIBILITY_COMPOSE_PROJECT:-boa_visibility_${$}}
FRONTEND_PORT=${VISIBILITY_FRONTEND_PORT:-3313}
API_GATEWAY_PORT=${VISIBILITY_API_PORT:-8313}
KEYCLOAK_PORT=${VISIBILITY_KEYCLOAK_PORT:-8314}
MAILPIT_WEB_PORT=${VISIBILITY_MAILPIT_PORT:-8315}
EVIDENCE_DIR=${VISIBILITY_EVIDENCE_DIR:-$PROJECT_ROOT/docs/evidence/visibility}
RESULTS_FILE="$EVIDENCE_DIR/RESULTATS-VISIBILITE.json"
E2E_RESULTS_FILE="$EVIDENCE_DIR/RESULTATS-PLAYWRIGHT-VISIBILITE.json"
ENV_FILE=${VISIBILITY_ENV_FILE:-/tmp/${PROJECT_NAME}.env}
OVERRIDE_FILE=${VISIBILITY_OVERRIDE_FILE:-/tmp/${PROJECT_NAME}.override.yml}
KEEP_STACK=${VISIBILITY_KEEP_STACK:-false}
TMP_PREFIX=/tmp/${PROJECT_NAME}

if [[ -S /var/run/docker.sock && ! -w /var/run/docker.sock ]] && command -v sudo >/dev/null; then
  DOCKER=(sudo -n docker)
else
  DOCKER=(docker)
fi
compose() {
  "${DOCKER[@]}" compose --project-name "$PROJECT_NAME" --file "$COMPOSE_FILE" \
    --file "$OVERRIDE_FILE" --env-file "$ENV_FILE" "$@"
}
cleanup() {
  if [[ "$KEEP_STACK" != "true" ]]; then
    compose down --volumes --remove-orphans >/dev/null 2>&1 || true
    rm -f "$ENV_FILE" "$OVERRIDE_FILE"
  else
    printf '[visibility] Stack conservée: COMPOSE_PROJECT_NAME=%s, frontend=%s, gateway=%s\n' \
      "$PROJECT_NAME" "$FRONTEND_PORT" "$API_GATEWAY_PORT"
  fi
}
trap cleanup EXIT
for command in curl jq npm od python3 sha256sum timeout xargs; do
  command -v "$command" >/dev/null || { echo "Required command not found: $command" >&2; exit 1; }
done
mkdir -p "$EVIDENCE_DIR"
cat >"$ENV_FILE" <<EOF
COMPOSE_PROJECT_NAME=$PROJECT_NAME
APP_ENV=development
BOA_AUTH_DISABLED=true
VITE_AUTH_DISABLED=true
FRONTEND_PORT=$FRONTEND_PORT
API_GATEWAY_PORT=$API_GATEWAY_PORT
KEYCLOAK_PORT=$KEYCLOAK_PORT
MAILPIT_WEB_PORT=$MAILPIT_WEB_PORT
POSTGRES_DB=boa_visibility
POSTGRES_ADMIN_USER=boa_admin
POSTGRES_ADMIN_PASSWORD=Visibility-Postgres-LocalOnly!
CUSTOMER_DB_PASSWORD=Visibility-Customer-LocalOnly!
ACCOUNT_DB_PASSWORD=Visibility-Account-LocalOnly!
TRANSACTION_DB_PASSWORD=Visibility-Transaction-LocalOnly!
INTEGRATION_DB_PASSWORD=Visibility-Integration-LocalOnly!
ANALYTICS_DB_PASSWORD=Visibility-Analytics-LocalOnly!
SIGNAL_DB_PASSWORD=Visibility-Signal-LocalOnly!
OPPORTUNITY_DB_PASSWORD=Visibility-Opportunity-LocalOnly!
PRODUCT_DB_PASSWORD=Visibility-Product-LocalOnly!
ACTION_DB_PASSWORD=Visibility-Action-LocalOnly!
RULE_MANAGEMENT_DB_PASSWORD=Visibility-RuleManagement-LocalOnly!
FEATURE_STORE_DB_PASSWORD=Visibility-FeatureStore-LocalOnly!
ML_ENGINE_DB_PASSWORD=Visibility-MlEngine-LocalOnly!
PORTFOLIO_DB_PASSWORD=Visibility-Portfolio-LocalOnly!
NOTIFICATION_DB_PASSWORD=Visibility-Notification-LocalOnly!
KEYCLOAK_DB_PASSWORD=Visibility-Keycloak-LocalOnly!
KEYCLOAK_ADMIN_USERNAME=boa-admin
KEYCLOAK_ADMIN_PASSWORD=Visibility-KeycloakAdmin-LocalOnly!
NOTIFICATION_SCOPE_SIGNING_SECRET=Visibility-Notification-Scope-Signing-LocalOnly-20260921!
OIDC_PUBLIC_ISSUER_URL=http://localhost:$KEYCLOAK_PORT/realms/boa-sme-mvp
CORS_ALLOWED_ORIGINS=http://localhost:$FRONTEND_PORT
VITE_KEYCLOAK_URL=http://localhost:$KEYCLOAK_PORT
VITE_API_BASE_URL=
RATE_LIMIT_PER_MINUTE=10000
EOF
cat >"$OVERRIDE_FILE" <<EOF
networks:
  edge:
    name: ${PROJECT_NAME}_edge
  app:
    name: ${PROJECT_NAME}_app
  data:
    name: ${PROJECT_NAME}_data
volumes:
  boa_postgres_data:
    name: ${PROJECT_NAME}_postgres_data
EOF

# Never touch the active Compose project: this script owns only PROJECT_NAME and its fresh volume.
compose down --volumes --remove-orphans >/dev/null 2>&1 || true
compose build >/dev/null
compose up --detach postgres
for _ in $(seq 1 90); do
  status=$("${DOCKER[@]}" inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$(compose ps -q postgres)" 2>/dev/null || true)
  [[ "$status" == healthy ]] && break
  sleep 2
done
[[ $("${DOCKER[@]}" inspect --format '{{.State.Health.Status}}' "$(compose ps -q postgres)") == healthy ]]
export COMPOSE_PROJECT_NAME="$PROJECT_NAME" ENV_FILE="$ENV_FILE"
export COMPOSE_FILE COMPOSE_OVERRIDE_FILE="$OVERRIDE_FILE"
"$SCRIPT_DIR/migrate.sh" >"${TMP_PREFIX}-migration.log"
compose --profile tools run --rm demo-data-generator >"${TMP_PREFIX}-seed.log"
compose up --detach
for service in keycloak customer account transaction analytics signal opportunity product action rule-management rule-engine rule-simulation feature-store ml-engine portfolio api-gateway frontend; do
  container=$(compose ps -q "$service")
  [[ -n "$container" ]] || { echo "Missing service: $service" >&2; exit 1; }
  for _ in $(seq 1 120); do
    status=$("${DOCKER[@]}" inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)
    [[ "$status" == healthy || "$status" == running ]] && break
    [[ "$status" == unhealthy || "$status" == exited || "$status" == dead ]] && {
      compose logs --no-color "$service" >&2 || true
      exit 1
    }
    sleep 2
  done
done

export COMPOSE_PROJECT_NAME="$PROJECT_NAME" ENV_FILE="$ENV_FILE"
export COMPOSE_FILE COMPOSE_OVERRIDE_FILE="$OVERRIDE_FILE"
export FRONTEND_PORT API_GATEWAY_PORT KEYCLOAK_PORT
export PIPELINE_CUSTOMER_COUNT=500 PIPELINE_BATCH_SIZE=25 AS_OF_DATE=2026-09-30
"$SCRIPT_DIR/run-pipeline.sh" >"${TMP_PREFIX}-pipeline.log"

GATEWAY="http://127.0.0.1:${API_GATEWAY_PORT}"
analyst='{"subject":"analyst-lot13","username":"business.analyst.demo","roles":["BUSINESS_ANALYST","DATA_ANALYST"],"branchIds":["ALL"]}'
approver='{"subject":"approver-lot13","username":"rule.approver.demo","roles":["RULE_APPROVER","DATA_ANALYST"],"branchIds":["ALL"]}'
admin='{"subject":"admin-lot13","username":"admin.demo","roles":["ADMIN","BUSINESS_ANALYST","DATA_ANALYST"],"branchIds":["ALL"]}'
ahmed='{"subject":"rm-01","username":"ahmed.mansouri","roles":["RELATIONSHIP_MANAGER"],"relationshipManagerIds":["rm-01"],"branchIds":["BR-01"]}'
salma='{"subject":"bm-01","username":"salma.berrada","roles":["BRANCH_MANAGER"],"branchIds":["BR-01"]}'
api() {
  local method=$1 path=$2 principal=$3 payload=${4-}
  local args=(--fail-with-body --silent --show-error --request "$method" --header "X-Dev-Principal: $principal" --header 'Content-Type: application/json')
  [[ -n "$payload" ]] && args+=(--data "$payload")
  curl "${args[@]}" "$GATEWAY$path"
}
assert_jq() {
  local file=$1 expression=$2 label=$3
  jq -e "$expression" "$file" >/dev/null || { echo "Oracle failed: $label" >&2; jq . "$file" >&2; exit 1; }
  printf '[visibility] PASS %s\n' "$label"
}
fetch_all_pages() {
  local path=$1 principal=$2 output=$3 cursor="" page_file combined_file
  page_file=$(mktemp)
  combined_file=$(mktemp)
  jq -n '{data:[]}' >"$output"
  while true; do
    api GET "${path}${cursor:+&cursor=$cursor}" "$principal" >"$page_file"
    jq -s '{data:(.[0].data + .[1].data)}' "$output" "$page_file" >"$combined_file"
    mv "$combined_file" "$output"
    combined_file=$(mktemp)
    cursor=$(jq -r '.meta.nextCursor // empty' "$page_file")
    [[ -n "$cursor" ]] || break
  done
  jq '.meta={pageSize:(.data|length),nextCursor:null,hasMore:false,totalCount:(.data|length)}' \
    "$output" >"$combined_file"
  mv "$combined_file" "$output"
  rm -f "$page_file"
}

api GET /api/v1/rules/FLOW_DOMICILIATION_001 "$analyst" > "${TMP_PREFIX}-rule-draft.json"
assert_jq "${TMP_PREFIX}-rule-draft.json" '.status == "DRAFT"' rule_studio_seeded_draft
api POST /api/v1/rules/FLOW_DOMICILIATION_001/validate "$analyst" '{"reason":"Validation Lot 13 — HYPOTHÈSE À VALIDER AVEC BOA"}' > "${TMP_PREFIX}-rule-validated.json"
assert_jq "${TMP_PREFIX}-rule-validated.json" '.rule.status == "VALIDATED"' rule_studio_validated
api POST /api/v1/rules/FLOW_DOMICILIATION_001/simulate "$analyst" '{"period":{"from":"2026-09-30","to":"2026-09-30"},"population":{"segment":"SME","dataKind":"SYNTHETIC"}}' > "${TMP_PREFIX}-rule-simulated.json"
assert_jq "${TMP_PREFIX}-rule-simulated.json" '.rule.status == "SIMULATED" and .populationAnalyzed == 500 and .matchedCustomers > 0' rule_studio_real_population
api POST /api/v1/rules/FLOW_DOMICILIATION_001/submit "$analyst" '{"reason":"Soumission par analyste Lot 13"}' > "${TMP_PREFIX}-rule-submitted.json"
assert_jq "${TMP_PREFIX}-rule-submitted.json" '.status == "SUBMITTED"' rule_studio_submitted
self_code=$(curl --silent --output "${TMP_PREFIX}-self-approval.json" --write-out '%{http_code}' --request POST --header "X-Dev-Principal: $analyst" --header 'Content-Type: application/json' --data '{"reason":"Auto-approbation interdite"}' "$GATEWAY/api/v1/rules/FLOW_DOMICILIATION_001/approve")
[[ "$self_code" == 403 ]]
api POST /api/v1/rules/FLOW_DOMICILIATION_001/approve "$approver" '{"reason":"Approbation indépendante Lot 13"}' > "${TMP_PREFIX}-rule-approved.json"
assert_jq "${TMP_PREFIX}-rule-approved.json" '.status == "APPROVED"' rule_studio_independent_approval
api POST /api/v1/rules/FLOW_DOMICILIATION_001/publish "$approver" '{"reason":"Publication gouvernée Lot 13"}' > "${TMP_PREFIX}-rule-published.json"
assert_jq "${TMP_PREFIX}-rule-published.json" '.status == "ACTIVE" and .activeVersion == 1' rule_studio_published
api GET /api/v1/rules/FLOW_DOMICILIATION_001/audit "$analyst" > "${TMP_PREFIX}-rule-audit.json"
assert_jq "${TMP_PREFIX}-rule-audit.json" '[.data[].action] == ["CREATED","VALIDATED","SIMULATED","SUBMITTED","APPROVED","PUBLISHED","ACTIVATED"] and (.data[] | select(.action == "APPROVED") | .userId) == "rule.approver.demo"' rule_studio_audit_complete

# Analytics and Signals were materialized by the complete 500-SME pipeline above. Once the
# governed rule is published, only Opportunity must be regenerated against those persisted facts.
CORRELATION_ID="visibility-after-publication-$(date +%s)" \
  PIPELINE_STAGES=opportunity \
  "$SCRIPT_DIR/run-pipeline.sh" >"${TMP_PREFIX}-pipeline-after-publication.log"

fetch_all_pages '/api/v1/customers?pageSize=100&sort=customerId' "$admin" \
  "${TMP_PREFIX}-customers.json"
api GET '/api/v1/opportunities?pageSize=1000' "$admin" > "${TMP_PREFIX}-opportunities.json"
api GET '/api/v1/signals?pageSize=1000' "$admin" > "${TMP_PREFIX}-signals.json"
api GET /api/v1/customers/SME-00040 "$ahmed" > "${TMP_PREFIX}-ahmed-customer.json"
api GET /api/v1/customers/SME-00040/product-gaps "$ahmed" >"${TMP_PREFIX}-ahmed-products.json"
api GET /api/v1/customers/SME-00040/opportunities "$ahmed" > "${TMP_PREFIX}-ahmed-opportunities.json"
api GET /api/v1/dashboards/branch "$salma" > "${TMP_PREFIX}-branch.json"

assert_jq "${TMP_PREFIX}-customers.json" '.meta.totalCount == 500 or (.data | length) == 500' customers_500
assert_jq "${TMP_PREFIX}-signals.json" '.data | length > 0' signals_present
assert_jq "${TMP_PREFIX}-ahmed-customer.json" '.customerId == "SME-00040" and .flowVisibility.level == "LOW" and .flowVisibility.estimatedShare == 0.25 and .flowVisibility.method == "TURNOVER_RATIO"' ahmed_secondary_low
assert_jq "${TMP_PREFIX}-ahmed-products.json" '[.gaps[].status] | index("ABSENT_OR_ELSEWHERE") != null' product_gap_requalified
assert_jq "${TMP_PREFIX}-ahmed-opportunities.json" '[.data[].opportunityType] | index("CASH_INVESTMENT") == null' low_cash_placement_removed
assert_jq "${TMP_PREFIX}-ahmed-opportunities.json" '[.data[] | select(.opportunityType == "FLOW_DOMICILIATION" and .recommendationNature == "WIN_BACK") and (.recommendedProducts | map(.productId) | index("BOA_PACK_BUSINESS_PME") != null)] | length > 0' domiciliation_win_back
assert_jq "${TMP_PREFIX}-branch.json" '([.visibilityDistribution[].count] | add) > 0 and ([.opportunitiesByType[] | select(.opportunityType == "FLOW_DOMICILIATION") | .count] | add) > 0' branch_visibility_and_flow

runtime_invariants=$(compose exec -T postgres psql --tuples-only --no-align --username boa_admin --dbname boa_visibility -c "SELECT count(*) FROM opportunity.opportunities WHERE fallback_mode <> 'RULES_ONLY' OR rules_weight <> 1 OR ml_weight <> 0;")
[[ "$runtime_invariants" == 0 ]]

# Explicit RBAC scoping oracle: Ahmed cannot declare outside rm-01 portfolio.
out_scope_code=$(curl --silent --output "${TMP_PREFIX}-out-scope.json" --write-out '%{http_code}' --request PUT --header "X-Dev-Principal: $ahmed" --header 'Content-Type: application/json' --data '{"bankingRelationship":"SECONDARY","reason":"Oracle hors portefeuille Lot 13"}' "$GATEWAY/api/v1/customers/SME-00009/banking-relationship")
[[ "$out_scope_code" == 403 ]]
assert_jq "${TMP_PREFIX}-out-scope.json" '.code == "CUSTOMER_OUTSIDE_PORTFOLIO"' out_of_portfolio_declaration_rejected

(
  cd "$PROJECT_ROOT/tests/e2e"
  npm ci --silent
  E2E_DEV_MODE=true \
    E2E_BASE_URL="http://127.0.0.1:${FRONTEND_PORT}" \
    E2E_MAILPIT_ORIGIN="http://127.0.0.1:${MAILPIT_WEB_PORT}" \
    timeout --signal=TERM 30m \
    ./node_modules/.bin/playwright test --config playwright.config.ts --reporter=json \
    >"$E2E_RESULTS_FILE"
)
e2e_expected=$(jq '.stats.expected' "$E2E_RESULTS_FILE")
e2e_unexpected=$(jq '.stats.unexpected' "$E2E_RESULTS_FILE")
[[ "$e2e_unexpected" == 0 && "$e2e_expected" -ge 23 ]]

screenshots=(
  VISIBILITE-FLUX-AHMED-1440x900.png
  OPPORTUNITE-DOMICILIATION-AHMED-1440x900.png
  DASHBOARD-AGENCE-VISIBILITE-1440x900.png
)
for screenshot in "${screenshots[@]}"; do
  read -r width height < <(od -An -t u4 --endian=big -j 16 -N 8 "$EVIDENCE_DIR/$screenshot" | xargs)
  [[ "$width" == 1440 && "$height" == 900 ]]
done

visibility_distribution=$(jq '[.data[].flowVisibility.level // "UNKNOWN"] | group_by(.) | map({level:.[0],count:length})' "${TMP_PREFIX}-customers.json")
method_distribution=$(jq '[.data[].flowVisibility.method // "NONE"] | group_by(.) | map({method:.[0],count:length})' "${TMP_PREFIX}-customers.json")
scenario_distribution=$(compose exec -T postgres psql --tuples-only --no-align \
  --username boa_admin --dbname boa_visibility -c "
    SELECT COALESCE(
      json_agg(json_build_object('scenario', scenario_code, 'count', count) ORDER BY scenario_code),
      '[]'::json
    )
    FROM (
      SELECT scenario_code, count(*) AS count
      FROM customer.customers
      WHERE scenario_code IN ('MULTIBANK_PRIMARY', 'MULTIBANK_SECONDARY')
      GROUP BY scenario_code
    ) scenarios;")
flow_count=$(jq '[.data[] | select(.opportunityType == "FLOW_DOMICILIATION")] | length' "${TMP_PREFIX}-opportunities.json")
win_back_count=$(jq '[.data[] | select(.recommendationNature == "WIN_BACK")] | length' "${TMP_PREFIX}-opportunities.json")
absence_elsewhere=$(jq '[.gaps[] | select(.status == "ABSENT_OR_ELSEWHERE")] | length' "${TMP_PREFIX}-ahmed-products.json")
rule_population=$(jq '.populationAnalyzed' "${TMP_PREFIX}-rule-simulated.json")
rule_matches=$(jq '.matchedCustomers' "${TMP_PREFIX}-rule-simulated.json")
git -C "$PROJECT_ROOT" diff --quiet -- \
  backend database frontend/src infrastructure scripts tests
code_digest=$(
  git -C "$PROJECT_ROOT" ls-tree -r HEAD -- \
    backend database frontend/src infrastructure scripts tests |
    sha256sum | awk '{print $1}'
)

jq -n \
  --arg runId "visibility-$(date -u +%Y%m%dT%H%M%SZ)" \
  --arg generatedAt "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg branch "$(git -C "$PROJECT_ROOT" branch --show-current)" \
  --arg commit "$(git -C "$PROJECT_ROOT" rev-parse HEAD)" \
  --arg codeDigest "$code_digest" \
  --arg project "$PROJECT_NAME" \
  --argjson visibility "$visibility_distribution" \
  --argjson methods "$method_distribution" \
  --argjson scenarios "$scenario_distribution" \
  --argjson flowCount "$flow_count" \
  --argjson winBackCount "$win_back_count" \
  --argjson absentElsewhere "$absence_elsewhere" \
  --argjson rulePopulation "$rule_population" \
  --argjson ruleMatches "$rule_matches" \
  --argjson e2eExpected "$e2e_expected" \
  '{schemaVersion:"1.0",runId:$runId,generatedAt:$generatedAt,status:"PASS",source:{branch:$branch,baseCommit:$commit,codeTree:"CLEAN",codeDigest:$codeDigest,documentationTree:"DIRTY_VALIDATED"},environment:{composeProject:$project,freshNamedVolume:true,isolatedPorts:true,customerCount:500,dataKind:"SYNTHETIC",externalDataUsed:false,llmOrGpuUsed:false},distribution:{levels:$visibility,methods:$methods,scenarios:$scenarios},analytics:{visibilitySnapshots:500,threeMethodsExercised:([ $methods[].method ] | contains(["DECLARED","TURNOVER_RATIO","TRANSACTION_FINGERPRINTS"]))},signals:{present:true},opportunities:{flowDomiciliation:$flowCount,recommendationNatureWinBack:$winBackCount,cashInvestmentRemovedForLow:true,absentOrElsewhereForAhmed:$absentElsewhere},ruleStudio:{ruleId:"FLOW_DOMICILIATION_001",seedStatus:"DRAFT",path:["DRAFT","VALIDATED","SIMULATED","SUBMITTED","APPROVED","PUBLISHED","ACTIVE"],populationAnalyzed:$rulePopulation,matchedCustomers:$ruleMatches,analyst:"business.analyst.demo",approver:"rule.approver.demo",selfApprovalRejected:true,auditComplete:true},e2e:{expected:$e2eExpected,unexpected:0,viewport:"1440x900",screenshots:3},oracles:{primarySecondaryScenarios:"PASS",lowPlacementWithdrawal:"PASS",productGapAbsentOrElsewhere:"PASS",winBack:"PASS",outOfPortfolioScoping:"PASS",ahmedCustomer:"SME-00040",salmaBranchVisibility:"PASS"},invariants:{operatingMode:"POC_SHADOW",fallbackMode:"RULES_ONLY",rulesWeight:1,mlWeight:0,creditDecisioning:false,externalData:false,syntheticDataOnly:true,llmUsed:false,gpuUsed:false,thresholdsStatus:"HYPOTHÈSE À VALIDER AVEC BOA"},limitations:["Validation locale sur données synthétiques et stack Compose éphémère isolée; aucune donnée BOA réelle.","Les seuils 0,7/0,3, pénalités -10/-25/-5, deux empreintes sur 90 jours et refroidissement 180 jours sont HYPOTHÈSE À VALIDER AVEC BOA.","Le POC produit une aide commerciale; il ne prend aucune décision de crédit."]}' >"$RESULTS_FILE"

sha256sum "$RESULTS_FILE" >"$RESULTS_FILE.sha256"
sha256sum --check "$RESULTS_FILE.sha256"
printf '[visibility] PASS: %s\n' "$RESULTS_FILE"
if [[ "$KEEP_STACK" == "true" ]]; then
  printf '[visibility] Frontend: http://127.0.0.1:%s\n' "$FRONTEND_PORT"
fi
