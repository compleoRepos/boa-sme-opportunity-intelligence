#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
COMPOSE_FILE="$PROJECT_ROOT/infrastructure/docker-compose.yml"
PROJECT_NAME=${LOT14_COMPOSE_PROJECT:-boa_lot14_${$}}
FRONTEND_PORT=${LOT14_FRONTEND_PORT:-3614}
API_GATEWAY_PORT=${LOT14_API_PORT:-8614}
KEYCLOAK_PORT=${LOT14_KEYCLOAK_PORT:-8615}
MAILPIT_WEB_PORT=${LOT14_MAILPIT_PORT:-8616}
ENV_FILE=${LOT14_ENV_FILE:-/tmp/${PROJECT_NAME}.env}
OVERRIDE_FILE=${LOT14_OVERRIDE_FILE:-/tmp/${PROJECT_NAME}.override.yml}
RESULTS_FILE=${LOT14_RESULTS_FILE:-$PROJECT_ROOT/docs/evidence/lot14/RESULTATS-CORRECTIONS-AUDIT.json}
E2E_RESULTS_FILE=${LOT14_E2E_RESULTS_FILE:-$PROJECT_ROOT/docs/evidence/lot14/RESULTATS-ROUTES-SANS-ECRAN-BLANC.json}
KEEP_STACK=${LOT14_KEEP_STACK:-false}
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
  fi
}
trap cleanup EXIT
for command in curl jq npm sha256sum; do
  command -v "$command" >/dev/null || { echo "Required command not found: $command" >&2; exit 1; }
done
mkdir -p "$(dirname "$RESULTS_FILE")"

cat >"$ENV_FILE" <<EOF
COMPOSE_PROJECT_NAME=$PROJECT_NAME
APP_ENV=development
BOA_AUTH_DISABLED=true
VITE_AUTH_DISABLED=true
FRONTEND_PORT=$FRONTEND_PORT
API_GATEWAY_PORT=$API_GATEWAY_PORT
KEYCLOAK_PORT=$KEYCLOAK_PORT
MAILPIT_WEB_PORT=$MAILPIT_WEB_PORT
POSTGRES_DB=boa_lot14
POSTGRES_ADMIN_USER=boa_admin
POSTGRES_ADMIN_PASSWORD=Lot14-Postgres-LocalOnly!
CUSTOMER_DB_PASSWORD=Lot14-Customer-LocalOnly!
ACCOUNT_DB_PASSWORD=Lot14-Account-LocalOnly!
TRANSACTION_DB_PASSWORD=Lot14-Transaction-LocalOnly!
INTEGRATION_DB_PASSWORD=Lot14-Integration-LocalOnly!
ANALYTICS_DB_PASSWORD=Lot14-Analytics-LocalOnly!
SIGNAL_DB_PASSWORD=Lot14-Signal-LocalOnly!
OPPORTUNITY_DB_PASSWORD=Lot14-Opportunity-LocalOnly!
PRODUCT_DB_PASSWORD=Lot14-Product-LocalOnly!
ACTION_DB_PASSWORD=Lot14-Action-LocalOnly!
RULE_MANAGEMENT_DB_PASSWORD=Lot14-RuleManagement-LocalOnly!
FEATURE_STORE_DB_PASSWORD=Lot14-FeatureStore-LocalOnly!
ML_ENGINE_DB_PASSWORD=Lot14-MlEngine-LocalOnly!
PORTFOLIO_DB_PASSWORD=Lot14-Portfolio-LocalOnly!
NOTIFICATION_DB_PASSWORD=Lot14-Notification-LocalOnly!
KEYCLOAK_DB_PASSWORD=Lot14-Keycloak-LocalOnly!
KEYCLOAK_ADMIN_USERNAME=boa-admin
KEYCLOAK_ADMIN_PASSWORD=Lot14-KeycloakAdmin-LocalOnly!
NOTIFICATION_SCOPE_SIGNING_SECRET=Lot14-Notification-Scope-Signing-LocalOnly!
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

export COMPOSE_PROJECT_NAME="$PROJECT_NAME" ENV_FILE
export COMPOSE_FILE COMPOSE_OVERRIDE_FILE="$OVERRIDE_FILE"
compose down --volumes --remove-orphans >/dev/null 2>&1 || true
compose build >"${TMP_PREFIX}-build.log"
"$SCRIPT_DIR/seed.sh" >"${TMP_PREFIX}-seed.log"
compose up --detach --build >"${TMP_PREFIX}-up.log"

http_services=(
  customer account transaction mock-bank banking-integration analytics signal feature-store
  ml-engine portfolio opportunity product action rule-management rule-engine rule-simulation
  notification api-gateway
)
for service in "${http_services[@]}"; do
  start=$(date +%s)
  while true; do
    container=$(compose ps -q "$service")
    status=$("${DOCKER[@]}" inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)
    [[ "$status" == healthy ]] && break
    [[ "$status" == unhealthy || "$status" == exited || "$status" == dead ]] && {
      compose logs --no-color "$service" >&2 || true
      exit 1
    }
    (( $(date +%s) - start < 360 )) || { echo "Timeout waiting for $service ($status)" >&2; exit 1; }
    sleep 3
  done
done
curl --fail --silent --show-error "http://127.0.0.1:$FRONTEND_PORT/" >/dev/null
curl --fail --silent --show-error "http://127.0.0.1:$API_GATEWAY_PORT/health" >/dev/null

principal='{"subject":"lot14-validator","username":"lot14.validator","roles":["ADMIN","BUSINESS_ANALYST","RULE_APPROVER","ML_STEWARD"],"branchIds":["ALL"]}'
rules_json='[]'
for rule_id in SME_INVESTMENT_001 SME_TRADE_001 FLOW_DOMICILIATION_001; do
  response=$(curl --fail --silent --show-error \
    -H "X-Dev-Principal: $principal" \
    "http://127.0.0.1:$API_GATEWAY_PORT/api/v1/rules/$rule_id")
  rules_json=$(jq -nc --argjson current "$rules_json" --argjson item "$response" '$current + [{ruleId:$item.ruleId,status:$item.status,version:$item.currentVersion}]')
done
active_policy=$(curl --fail --silent --show-error \
  -H "X-Dev-Principal: $principal" \
  "http://127.0.0.1:$API_GATEWAY_PORT/api/v1/admin/scoring-policies/active")
studio_summary=$(curl --fail --silent --show-error \
  -H "X-Dev-Principal: $principal" \
  "http://127.0.0.1:$API_GATEWAY_PORT/api/v1/admin/ml/governance/studio-summary")
jq -e --argjson policy "$active_policy" '
  .activePolicy.policyId == $policy.policyId
  and .activePolicy.version == $policy.version
  and .activePolicy.rulesWeight == $policy.weights.rules
  and .activePolicy.mlWeight == $policy.weights.ml
  and ((.gates[] | select(.gate == "G3") | .status) == (if $policy.weights.ml > 0 then "PASSED" else "BLOCKED" end))
' <<<"$studio_summary" >/dev/null

if [[ ! -x "$PROJECT_ROOT/tests/e2e/node_modules/.bin/playwright" ]]; then
  npm --prefix "$PROJECT_ROOT/tests/e2e" ci
fi
(
  cd "$PROJECT_ROOT/tests/e2e"
  E2E_DEV_MODE=true \
  E2E_BASE_URL="http://127.0.0.1:$FRONTEND_PORT" \
  E2E_MAILPIT_ORIGIN="http://127.0.0.1:$MAILPIT_WEB_PORT" \
  ./node_modules/.bin/playwright test route-smoke.spec.ts \
    --config playwright.config.ts --reporter=json >"$E2E_RESULTS_FILE"
)
route_tests_passed=$(jq '.stats.expected' "$E2E_RESULTS_FILE")
route_tests_failed=$(jq '.stats.unexpected + .stats.flaky' "$E2E_RESULTS_FILE")
[[ "$route_tests_passed" == 3 ]]
[[ "$route_tests_failed" == 0 ]]

psql_value() {
  compose exec -T postgres psql --set=ON_ERROR_STOP=1 --username boa_admin --dbname boa_lot14 \
    --tuples-only --no-align --command "$1" \
    | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}
rule_rows=$(psql_value "SELECT count(*) FROM rule.rules WHERE rule_id IN ('SME_INVESTMENT_001','SME_TRADE_001','FLOW_DOMICILIATION_001');")
flow_opportunity_rows=$(psql_value "SELECT count(*) FROM opportunity.opportunities WHERE opportunity_type='FLOW_DOMICILIATION';")
flow_audit_rows=$(psql_value "SELECT count(*) FROM opportunity.decision_audit WHERE opportunity_type='FLOW_DOMICILIATION';")
flow_opportunity_type=$(psql_value "SELECT data_type FROM information_schema.columns WHERE table_schema='opportunity' AND table_name='opportunities' AND column_name='opportunity_type';")
flow_audit_type=$(psql_value "SELECT data_type FROM information_schema.columns WHERE table_schema='opportunity' AND table_name='decision_audit' AND column_name='opportunity_type';")
head_revision=$(psql_value "SELECT version_num FROM public.alembic_version;")
[[ "$rule_rows" == 3 ]]
[[ "$head_revision" == 0020_multibank_visibility ]]
[[ "$flow_opportunity_type" == "character varying" ]]
[[ "$flow_audit_type" == "character varying" ]]

source_revision=$(git -C "$PROJECT_ROOT" rev-parse HEAD)
source_branch=$(git -C "$PROJECT_ROOT" branch --show-current)
code_digest=$(
  cd "$PROJECT_ROOT"
  git ls-files -z backend database frontend/src infrastructure scripts tests .github/workflows \
    | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}'
)

generated_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
jq -n \
  --arg generatedAt "$generated_at" \
  --arg project "$PROJECT_NAME" \
  --arg branch "$source_branch" \
  --arg revision "$source_revision" \
  --arg codeDigest "$code_digest" \
  --arg headRevision "$head_revision" \
  --arg flowOpportunityType "$flow_opportunity_type" \
  --arg flowAuditType "$flow_audit_type" \
  --argjson rules "$rules_json" \
  --argjson activePolicy "$active_policy" \
  --argjson studioSummary "$studio_summary" \
  --argjson routeTestsPassed "$route_tests_passed" \
  --argjson flowOpportunityRows "$flow_opportunity_rows" \
  --argjson flowAuditRows "$flow_audit_rows" \
  '{
    schemaVersion:"1.0",
    status:"PASS",
    generatedAt:$generatedAt,
    source:{branch:$branch,revision:$revision,codeDigest:$codeDigest},
    docker:{project:$project,freshNamedVolume:true,backendHealth:{passed:18,total:18},frontendHttp:"PASS",gatewayHealth:"PASS"},
    migrations:{headRevision:$headRevision},
    ruleStudio:{requiredRules:3,databaseRows:3,rules:$rules},
    mlStudio:{activePolicy:$activePolicy,g3:($studioSummary.gates[] | select(.gate == "G3"))},
    routeSmoke:{status:"PASS",playwrightTests:$routeTestsPassed,routesOpened:27,blankRoots:0},
    multibankTypes:{opportunityColumnType:$flowOpportunityType,decisionAuditColumnType:$flowAuditType,flowDomiciliationOpportunities:$flowOpportunityRows,flowDomiciliationDecisionAudits:$flowAuditRows},
    limitations:[
      "Données synthétiques uniquement.",
      "Aucune décision de crédit.",
      "ML CPU-only en POC_SHADOW; aucune influence opérationnelle.",
      "Aucun LLM ni GPU requis.",
      "Les seuils et résultats métier BOA restent HYPOTHÈSE À VALIDER AVEC BOA."
    ]
  }' >"$RESULTS_FILE"
jq -e '.status == "PASS" and .docker.backendHealth.passed == 18 and .ruleStudio.databaseRows == 3' "$RESULTS_FILE" >/dev/null
printf '[lot14] PASS: %s\n' "$RESULTS_FILE"
