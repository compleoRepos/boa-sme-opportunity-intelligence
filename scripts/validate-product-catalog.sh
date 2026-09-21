#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"
require_command curl
require_command jq
require_command sha256sum
load_local_env

OUTPUT_FILE=${PRODUCT_CATALOG_OUTPUT_FILE:-$PROJECT_ROOT/docs/evidence/catalog/RESULTATS-CATALOGUE-PRODUITS.json}
KEYCLOAK_PORT=${KEYCLOAK_PORT:-8081}
PIPELINE_CLIENT_SECRET=${PIPELINE_CLIENT_SECRET:-DevOnly-PipelineClient-ChangeMe!}
CUSTOMER_REF=${PRODUCT_CATALOG_CUSTOMER_REF:-SME-00035}
AS_OF_DATE=${PRODUCT_CATALOG_AS_OF_DATE:-2026-09-30}
RUN_ID="product-catalog-$(date -u +%Y%m%dT%H%M%SZ)-$$"
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

assert_true() {
  local label=$1 value=$2
  if [[ "$value" != "true" ]]; then
    printf 'FAIL %s (result=%s)\n' "$label" "$value" >&2
    return 1
  fi
  printf 'PASS %s\n' "$label"
}

mkdir -p "$(dirname -- "$OUTPUT_FILE")"
source_files=(
  backend/src/boa_oi/catalog.py
  backend/src/boa_oi/analytics_api.py
  backend/src/boa_oi/signal_api.py
  backend/src/boa_oi/feature_store_api.py
  backend/src/boa_oi/ml/service.py
  backend/src/boa_oi/models/entities.py
  backend/src/boa_oi/platform.py
  backend/src/boa_oi/product_api.py
  backend/src/boa_oi/rule_management_api.py
  backend/src/boa_oi/rule_engine_api.py
  backend/src/boa_oi/rules/domain.py
  backend/src/boa_oi/rules/service.py
  backend/src/boa_oi/opportunity_api.py
  backend/src/boa_oi/technical/reference.py
  database/migrations/versions/0001_initial.py
  database/migrations/versions/0018_product_catalog.py
  database/seed/generate.py
  database/seed/rule-studio.json
  database/seed/rules.yaml
  frontend/src/pages/ProductsPage.tsx
  frontend/src/features/rules/RuleBlocks.tsx
  scripts/validate-product-catalog.sh
)
source_digest=$(
  cd "$PROJECT_ROOT"
  sha256sum "${source_files[@]}" | sha256sum | awk '{print $1}'
)

compose up -d --build analytics signal feature-store ml-engine product rule-management rule-engine opportunity api-gateway >/tmp/boa-product-catalog-services.log 2>&1
for service in keycloak postgres analytics signal feature-store ml-engine product rule-management rule-engine opportunity api-gateway; do
  wait_for_healthy "$service" 300
done
refresh_token
product_readiness=$(compose exec -T product curl --fail-with-body --silent --show-error \
  'http://localhost:8080/ready')

invalid_rule_payload=$(jq -nc --arg ruleId "CATALOG-INVALID-${RUN_ID}" '{ruleId:$ruleId,name:"Validation catalogue négative",conditions:[{metric:"INFLOW_GROWTH",operator:">",value:0.1}],recommendation:{opportunityType:"TEST",products:["INVESTMENT_FINANCING"]}}')
invalid_rule_body=$(mktemp)
invalid_ownership_body=$(mktemp)
trap 'rm -f "$invalid_rule_body" "$invalid_ownership_body"' EXIT
invalid_rule_status=$(compose exec -T rule-management curl --silent --show-error \
  --output /tmp/invalid-rule-response.json \
  --write-out '%{http_code}' \
  --request POST \
  --header "Authorization: Bearer ${token}" \
  --header 'Content-Type: application/json' \
  --data "$invalid_rule_payload" \
  'http://localhost:8080/internal/v1/rules')
compose exec -T rule-management cat /tmp/invalid-rule-response.json >"$invalid_rule_body"
compose exec -T rule-management rm -f /tmp/invalid-rule-response.json
invalid_rule_rejected=$(jq --arg status "$invalid_rule_status" '$status == "422" and .code == "RULE_VALIDATION_FAILED"' "$invalid_rule_body")

invalid_ownership_payload=$(jq -nc --arg customer "$CUSTOMER_REF" '{externalBatchId:"catalog-invalid-ownership",products:[],ownerships:[{customerId:$customer,productId:"BOA_UNGOVERNED",status:"ACTIVE",openedOn:"2026-01-01"}]}')
invalid_ownership_status=$(compose exec -T product curl --silent --show-error \
  --output /tmp/invalid-ownership-response.json \
  --write-out '%{http_code}' \
  --request POST \
  --header "Authorization: Bearer ${token}" \
  --header "Idempotency-Key: ${RUN_ID}-invalid-ownership" \
  --header 'Content-Type: application/json' \
  --data "$invalid_ownership_payload" \
  'http://localhost:8080/internal/v1/imports/products')
compose exec -T product cat /tmp/invalid-ownership-response.json >"$invalid_ownership_body"
compose exec -T product rm -f /tmp/invalid-ownership-response.json
invalid_ownership_rejected=$(jq --arg status "$invalid_ownership_status" '$status == "422" and .code == "UNKNOWN_CATALOG_PRODUCT"' "$invalid_ownership_body")

catalog=$(curl --fail-with-body --silent --show-error \
  --header "Authorization: Bearer ${token}" \
  'http://localhost:8080/api/v1/products?pageSize=100')
trade_catalog=$(curl --fail-with-body --silent --show-error \
  --header "Authorization: Bearer ${token}" \
  'http://localhost:8080/api/v1/products?pageSize=100&family=TRADE_FINANCE')
gaps=$(compose exec -T product curl --fail-with-body --silent --show-error \
  --header "Authorization: Bearer ${token}" \
  "http://localhost:8080/internal/v1/customers/${CUSTOMER_REF}/product-gaps")

payload=$(jq -nc --arg customer "$CUSTOMER_REF" --arg asOf "$AS_OF_DATE" \
  '{customerIds:[$customer],asOf:$asOf}')
analytics_payload=$(jq -nc --arg customer "$CUSTOMER_REF" --arg asOf "$AS_OF_DATE" \
  '{customerIds:[$customer],asOf:$asOf,periods:["7D","30D","90D","180D","365D"]}')
signal_payload=$(jq -nc --arg customer "$CUSTOMER_REF" --arg asOf "$AS_OF_DATE" \
  '{customerIds:[$customer],asOf:$asOf,periods:["90D"]}')
analytics=$(compose exec -T analytics curl --fail-with-body --silent --show-error \
  --request POST \
  --header "Authorization: Bearer ${token}" \
  --header 'Content-Type: application/json' \
  --header "X-Correlation-ID: ${RUN_ID}" \
  --header "Idempotency-Key: ${RUN_ID}-analytics" \
  --data "$analytics_payload" \
  'http://localhost:8080/internal/v1/analytics/recompute')
signals=$(compose exec -T signal curl --fail-with-body --silent --show-error \
  --request POST \
  --header "Authorization: Bearer ${token}" \
  --header 'Content-Type: application/json' \
  --header "X-Correlation-ID: ${RUN_ID}" \
  --header "Idempotency-Key: ${RUN_ID}-signals" \
  --data "$signal_payload" \
  'http://localhost:8080/internal/v1/signals/evaluate')
generation=$(compose exec -T opportunity curl --fail-with-body --silent --show-error \
  --request POST \
  --header "Authorization: Bearer ${token}" \
  --header 'Content-Type: application/json' \
  --header "X-Correlation-ID: ${RUN_ID}" \
  --header "Idempotency-Key: ${RUN_ID}-generate" \
  --data "$payload" \
  'http://localhost:8080/internal/v1/opportunities/generate')

catalog_count=$(jq '.data | length' <<<"$catalog")
family_count=$(jq '[.data[].family] | unique | length' <<<"$catalog")
trade_count=$(jq '.data | length' <<<"$trade_catalog")
trade_filter_valid=$(jq '[.data[] | select(.family != "TRADE_FINANCE")] | length == 0' <<<"$trade_catalog")
metadata_complete=$(jq '[.data[] | select((.description | length) == 0 or (.sourceUrl | type) != "string" or (.sourceUrl | startswith("https://www.bankofafrica.ma/") | not))] | length == 0' <<<"$catalog")
nullable_total=$(jq '.meta.totalCount == null' <<<"$catalog")
gap_trade_count=$(jq '[.gaps[] | select(.product.family == "TRADE_FINANCE")] | length' <<<"$gaps")
gap_products_precise=$(jq '[.gaps[] | select(.product.family == "TRADE_FINANCE" and (.product.productId | startswith("BOA_") | not))] | length == 0' <<<"$gaps")
generation_complete=$(jq '.status == "COMPLETED" and .customers == 1 and .scoringPolicy.rulesWeight == 1 and .scoringPolicy.mlWeight == 0' <<<"$generation")
analytics_complete=$(jq '(.status == "COMPLETED" or .status == "ACCEPTED") and .customers == 1 and ((.processed + .skipped) == 1)' <<<"$analytics")
signals_complete=$(jq '(.status == "COMPLETED" or .status == "ACCEPTED") and .customers == 1' <<<"$signals")

active_legacy=$(sql "SELECT count(*) FROM product.products WHERE active AND product_code IN ('INVESTMENT_FINANCING','WORKING_CAPITAL_FACILITY','OVERDRAFT','TRADE_FINANCE','CASH_MANAGEMENT','TERM_DEPOSIT','LIQUIDITY_INVESTMENT');")
trade_recommendation_count=$(sql "SELECT count(*) FROM opportunity.opportunities o JOIN customer.customers c ON c.id=o.customer_id CROSS JOIN LATERAL json_array_elements(o.recommended_products_json) p WHERE c.customer_ref='${CUSTOMER_REF}' AND o.opportunity_type='TRADE_FINANCE' AND o.status IN ('OPEN','ACCEPTED','CONTACTED') AND p->>'productId' LIKE 'BOA_%';")
invalid_recommendation_count=$(sql "SELECT count(*) FROM opportunity.opportunities o JOIN customer.customers c ON c.id=o.customer_id CROSS JOIN LATERAL json_array_elements(o.recommended_products_json) p LEFT JOIN product.products product ON product.product_code=p->>'productId' AND product.active WHERE c.customer_ref='${CUSTOMER_REF}' AND o.status IN ('OPEN','ACCEPTED','CONTACTED') AND ((p->>'productId') NOT LIKE 'BOA_%' OR product.id IS NULL);")
non_rules_only_count=$(sql "SELECT count(*) FROM opportunity.opportunities o JOIN customer.customers c ON c.id=o.customer_id WHERE c.customer_ref='${CUSTOMER_REF}' AND o.status IN ('OPEN','ACCEPTED','CONTACTED') AND (o.rules_weight <> 1 OR o.ml_weight <> 0 OR o.fallback_mode <> 'RULES_ONLY');")
legacy_rule_products=$(sql "SELECT count(*) FROM rule.rule_versions rv JOIN rule.rules r ON r.id=rv.rule_id CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(rv.configuration_json::jsonb#>'{recommendation,products}','[]'::jsonb)) AS item(code) WHERE r.status='ACTIVE' AND rv.status='ACTIVE' AND item.code = ANY(ARRAY['INVESTMENT_FINANCING','WORKING_CAPITAL_FACILITY','TRADE_FINANCE','CASH_MANAGEMENT','TERM_DEPOSIT','LIQUIDITY_INVESTMENT']);")
unknown_rule_products=$(sql "SELECT count(*) FROM rule.rule_versions rv JOIN rule.rules r ON r.id=rv.rule_id CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(rv.configuration_json::jsonb#>'{recommendation,products}','[]'::jsonb)) AS item(code) WHERE r.status='ACTIVE' AND rv.status='ACTIVE' AND NOT EXISTS (SELECT 1 FROM product.products p WHERE p.product_code=item.code AND p.active);")
rule_version_width=$(sql "SELECT character_maximum_length FROM information_schema.columns WHERE table_schema='opportunity' AND table_name='opportunities' AND column_name='rule_version';")
migration_version=$(sql 'SELECT version_num FROM alembic_version;')
recommendations=$(sql "SELECT COALESCE(jsonb_agg(jsonb_build_object('opportunityType',o.opportunity_type,'ruleVersion',o.rule_version,'products',o.recommended_products_json::jsonb) ORDER BY o.opportunity_type),'[]'::jsonb)::text FROM opportunity.opportunities o JOIN customer.customers c ON c.id=o.customer_id WHERE c.customer_ref='${CUSTOMER_REF}' AND o.status IN ('OPEN','ACCEPTED','CONTACTED') AND json_array_length(o.recommended_products_json) > 0;")

assert_true 'catalogue actif de 28 produits' "$([[ "$catalog_count" == 28 ]] && echo true || echo false)"
assert_true 'Product Service ready avec catalogue gouverné complet' "$(jq -e '.status == "ready"' <<<"$product_readiness" >/dev/null && echo true || echo false)"
assert_true 'sept familles présentes' "$([[ "$family_count" == 7 ]] && echo true || echo false)"
assert_true 'six produits Trade Finance filtrés' "$([[ "$trade_count" == 6 ]] && echo true || echo false)"
assert_true 'filtre famille strict' "$trade_filter_valid"
assert_true 'descriptions et sources officielles renseignées' "$metadata_complete"
assert_true 'pagination sans COUNT exact' "$nullable_total"
assert_true 'lacunes Trade Finance calculées sur six produits' "$([[ "$gap_trade_count" == 6 ]] && echo true || echo false)"
assert_true 'lacunes exprimées par codes produit précis' "$gap_products_precise"
assert_true 'métriques Analytics présentes ou recalculées pour la fixture' "$analytics_complete"
assert_true 'signaux recalculés pour la fixture' "$signals_complete"
assert_true 'génération Opportunity terminée en rules-only' "$generation_complete"
assert_true 'au moins une recommandation Trade Finance précise' "$([[ "$trade_recommendation_count" -ge 1 ]] && echo true || echo false)"
assert_true 'aucune recommandation active orpheline ou générique' "$([[ "$invalid_recommendation_count" == 0 ]] && echo true || echo false)"
assert_true 'aucune règle active avec ancien code produit générique' "$([[ "$legacy_rule_products" == 0 ]] && echo true || echo false)"
assert_true 'aucune règle active avec code produit catalogue inconnu' "$([[ "$unknown_rule_products" == 0 ]] && echo true || echo false)"
assert_true 'Rule Studio rejette un code produit catalogue inconnu' "$invalid_rule_rejected"
assert_true 'Product Service rejette une détention avec code produit inconnu' "$invalid_ownership_rejected"
assert_true 'aucune opportunité commerciale influencée par le ML' "$([[ "$non_rules_only_count" == 0 ]] && echo true || echo false)"
assert_true 'anciens codes famille désactivés' "$([[ "$active_legacy" == 0 ]] && echo true || echo false)"
assert_true 'migration 0018 active' "$([[ "$migration_version" == 0018_product_catalog ]] && echo true || echo false)"
assert_true 'rule_version élargi à 80 caractères' "$([[ "$rule_version_width" == 80 ]] && echo true || echo false)"

jq -n \
  --arg runId "$RUN_ID" \
  --arg generatedAt "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg baseCommit "$(git rev-parse HEAD)" \
  --arg sourceDigest "$source_digest" \
  --arg customerRef "$CUSTOMER_REF" \
  --arg asOf "$AS_OF_DATE" \
  --arg migrationVersion "$migration_version" \
  --argjson sourceFiles "$(printf '%s\n' "${source_files[@]}" | jq -R . | jq -s .)" \
  --argjson catalogue "$catalog" \
  --argjson tradeCatalogue "$trade_catalog" \
  --argjson gaps "$gaps" \
  --argjson analytics "$analytics" \
  --argjson signals "$signals" \
  --argjson generation "$generation" \
  --argjson recommendations "$recommendations" \
  '{
    runId:$runId,
    generatedAt:$generatedAt,
    status:"PASS",
    sourceRevision:{baseCommit:$baseCommit,sourceDigest:$sourceDigest,files:$sourceFiles},
    scope:{fixture:"synthetic",customerRef:$customerRef,asOf:$asOf,migrationVersion:$migrationVersion},
    counts:{activeProducts:($catalogue.data|length),families:([$catalogue.data[].family]|unique|length),tradeFinanceProducts:($tradeCatalogue.data|length),tradeFinanceGaps:([$gaps.gaps[]|select(.product.family=="TRADE_FINANCE")]|length)},
    pipeline:{analytics:$analytics,signals:$signals},
    generation:{status:$generation.status,opportunities:$generation.opportunities,created:$generation.created,refreshed:$generation.refreshed,scoringPolicy:$generation.scoringPolicy,executionModes:$generation.executionModes},
    opportunityRecommendations:$recommendations,
    checks:{catalogue28:true,productServiceReady:true,families7:true,officialSourceUrlsPresent:true,familyFilter:true,cursorPaginationWithoutExactCount:true,tradeFinanceGapByFamily:true,preciseProductsOnly:true,activeRulesWithoutLegacyProductCodes:true,activeRulesWithoutUnknownProductCodes:true,ruleStudioUnknownProductRejected:true,unknownOwnershipProductRejected:true,analyticsCurrent:true,signalsRecomputed:true,legacyFamiliesInactive:true,rulesOnlyPriority:true,mlWeightZero:true,migration0018:true,ruleVersionWidth80:true},
    limitations:[
      "Fixture et détentions entièrement synthétiques : ce run ne mesure ni adéquation commerciale BOA, ni taux de conversion, ni performance de production.",
      "Les pages publiques attestent la présence et la nature générale des produits ; ciblages, éligibilité, tarification et disponibilité restent HYPOTHÈSE À VALIDER AVEC BOA.",
      "Le ML reste POC_SHADOW CPU-only, sans influence sur la priorité ou les recommandations ; aucune décision de crédit ne résulte du système.",
      "Le script vidéo optionnel reste non exécuté et ne constitue pas une preuve de production."
    ]
  }' >"$OUTPUT_FILE"

printf 'CATALOG_INTEGRATION_PASS artifact=%s\n' "$OUTPUT_FILE"
