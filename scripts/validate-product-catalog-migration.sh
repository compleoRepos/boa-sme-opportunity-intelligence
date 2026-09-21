#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_command docker
require_command jq
require_command sha256sum
load_local_env

POSTGRES_ADMIN_USER=${POSTGRES_ADMIN_USER:-boa_admin}
POSTGRES_ADMIN_PASSWORD=${POSTGRES_ADMIN_PASSWORD:-DevOnly-Postgres-ChangeMe!}
MIGRATION_DATABASE="boa_catalog_migration_$$"
FRESH_DATABASE="boa_catalog_fresh_$$"
OUTPUT_FILE=${PRODUCT_CATALOG_MIGRATION_EVIDENCE_FILE:-$PROJECT_ROOT/docs/evidence/catalog/RESULTATS-MIGRATION-CATALOGUE.json}

mkdir -p "$(dirname -- "$OUTPUT_FILE")"
compose up --detach postgres
wait_for_healthy postgres 120
compose build customer >/tmp/boa-product-catalog-migration-build.log
compose exec -T postgres createdb --username "$POSTGRES_ADMIN_USER" "$MIGRATION_DATABASE"
compose exec -T postgres createdb --username "$POSTGRES_ADMIN_USER" "$FRESH_DATABASE"

cleanup() {
  compose exec -T postgres dropdb --if-exists --force --username "$POSTGRES_ADMIN_USER" \
    "$MIGRATION_DATABASE" >/dev/null 2>&1 || true
  compose exec -T postgres dropdb --if-exists --force --username "$POSTGRES_ADMIN_USER" \
    "$FRESH_DATABASE" >/dev/null 2>&1 || true
}
trap cleanup EXIT

alembic() {
  local database=$1
  shift
  local database_url="postgresql+psycopg://${POSTGRES_ADMIN_USER}:${POSTGRES_ADMIN_PASSWORD}@postgres:5432/${database}"
  compose run --rm --no-deps --entrypoint /bin/sh --env "DATABASE_URL=$database_url" \
    customer -ec "cd /app/database && exec alembic -c alembic.ini $*"
}

sql_database() {
  local database=$1 query=$2
  compose exec -T postgres psql --set=ON_ERROR_STOP=1 --tuples-only --no-align \
    --username "$POSTGRES_ADMIN_USER" --dbname "$database" -c "$query"
}

assert_value() {
  local label=$1 expected=$2 actual=$3
  printf '[catalog-migration] %s=%s\n' "$label" "$actual"
  [[ "$actual" == "$expected" ]]
}

studio_demo_id=11111111-1111-1111-1111-111111111111
studio_demo_version_id=11111111-1111-1111-1111-111111111112
studio_user_id=22222222-2222-2222-2222-222222222221
studio_user_version_id=22222222-2222-2222-2222-222222222222
legacy_products='["INVESTMENT_FINANCING"]'
precise_products='["BOA_CREDIT_MLTD_DIRECT"]'

alembic "$MIGRATION_DATABASE" "upgrade 0017_ml_shadow_governance"
assert_value migration_starts_at_0017 0017_ml_shadow_governance \
  "$(sql_database "$MIGRATION_DATABASE" 'SELECT version_num FROM alembic_version')"

sql_database "$MIGRATION_DATABASE" "
INSERT INTO product.products
  (id, product_code, name, category, eligibility_rules_json, target_segments_json, currencies_json, active, created_by)
VALUES
  ('33333333-3333-3333-3333-333333333331', 'INVESTMENT_FINANCING', 'Legacy investment', 'CREDIT', '{}'::json, '[\"SME\"]'::json, '[\"MAD\"]'::json, true, 'demo-data-generator'),
  ('33333333-3333-3333-3333-333333333332', 'USER_SENTINEL_PRODUCT', 'User sentinel', 'CUSTOM', '{}'::json, '[\"SME\"]'::json, '[\"MAD\"]'::json, true, 'external-import');

INSERT INTO rule.rules
  (id, rule_id, name, description, status, current_version, active_version, created_by)
VALUES
  ('$studio_demo_id', 'SYNTHETIC_GROWTH_REVIEW', 'Synthetic demo', '', 'ACTIVE', 1, 1, 'demo-data-generator'),
  ('$studio_user_id', 'USER_CONTROLLED_RULE', 'User controlled', '', 'ACTIVE', 1, 1, 'business.analyst.boa');

INSERT INTO rule.rule_versions
  (id, rule_id, version, status, name, description, scope_json, logic, configuration_json, checksum, created_by)
VALUES
  ('$studio_demo_version_id', '$studio_demo_id', 1, 'ACTIVE', 'Synthetic demo', '', '{}'::jsonb, 'AND',
   '{\"conditions\":[{\"metric\":\"INFLOW_GROWTH\",\"operator\":\">\",\"value\":0.2}],\"recommendation\":{\"opportunityType\":\"GROWTH_FINANCING\",\"products\":$legacy_products}}'::jsonb,
   repeat('a', 64), 'demo-data-generator'),
  ('$studio_user_version_id', '$studio_user_id', 1, 'ACTIVE', 'User controlled', '', '{}'::jsonb, 'AND',
   '{\"conditions\":[{\"metric\":\"INFLOW_GROWTH\",\"operator\":\">\",\"value\":0.2}],\"recommendation\":{\"opportunityType\":\"USER_CASE\",\"products\":$legacy_products}}'::jsonb,
   repeat('b', 64), 'business.analyst.boa');

INSERT INTO rule.rule_actions
  (id, rule_version_id, position, opportunity_type_code, product_codes_json, horizon_code)
VALUES
  ('11111111-1111-1111-1111-111111111113', '$studio_demo_version_id', 0, 'GROWTH_FINANCING', '$legacy_products'::jsonb, '1-3_MONTHS'),
  ('22222222-2222-2222-2222-222222222223', '$studio_user_version_id', 0, 'USER_CASE', '$legacy_products'::jsonb, '1-3_MONTHS');

INSERT INTO opportunity.opportunity_rules
  (id, opportunity_type, version, configuration_json, active, created_by)
VALUES
  ('44444444-4444-4444-4444-444444444441', 'INVESTMENT_FINANCING', '1', '{\"recommended_product_codes\":[\"INVESTMENT_FINANCING\",\"WORKING_CAPITAL_FACILITY\"]}'::json, true, 'demo-data-generator'),
  ('44444444-4444-4444-4444-444444444442', 'TRADE_FINANCE', '1', '{\"recommended_product_codes\":[\"TRADE_FINANCE\"]}'::json, true, 'demo-data-generator'),
  ('44444444-4444-4444-4444-444444444443', 'CASH_INVESTMENT', '1', '{\"recommended_product_codes\":[\"CASH_MANAGEMENT\",\"TERM_DEPOSIT\",\"LIQUIDITY_INVESTMENT\"]}'::json, true, 'demo-data-generator'),
  ('44444444-4444-4444-4444-444444444444', 'FINANCIAL_STRESS_SIGNAL', '1', '{\"recommended_product_codes\":[\"CASH_MANAGEMENT\",\"WORKING_CAPITAL_FACILITY\"]}'::json, true, 'demo-data-generator'),
  ('44444444-4444-4444-4444-444444444445', 'USER_CASE', '1', '{\"recommended_product_codes\":[\"INVESTMENT_FINANCING\"]}'::json, true, 'business.analyst.boa');
" >/dev/null

user_before=$(sql_database "$MIGRATION_DATABASE" "SELECT md5(rv.configuration_json::text||rv.checksum||a.product_codes_json::text) FROM rule.rule_versions rv JOIN rule.rule_actions a ON a.rule_version_id=rv.id WHERE rv.id='$studio_user_version_id';")

alembic "$MIGRATION_DATABASE" "upgrade 0018_product_catalog"
assert_value upgrade_to_0018 0018_product_catalog \
  "$(sql_database "$MIGRATION_DATABASE" 'SELECT version_num FROM alembic_version')"
assert_value product_columns_added 3 \
  "$(sql_database "$MIGRATION_DATABASE" "SELECT count(*) FROM information_schema.columns WHERE table_schema='product' AND table_name='products' AND column_name IN ('family','description','source_url');")"
assert_value legacy_family_backfilled INVESTMENT_FINANCING \
  "$(sql_database "$MIGRATION_DATABASE" "SELECT family FROM product.products WHERE product_code='INVESTMENT_FINANCING';")"
assert_value external_product_unclassified UNCLASSIFIED \
  "$(sql_database "$MIGRATION_DATABASE" "SELECT family FROM product.products WHERE product_code='USER_SENTINEL_PRODUCT';")"
assert_value rule_version_width_upgraded 80 \
  "$(sql_database "$MIGRATION_DATABASE" "SELECT character_maximum_length FROM information_schema.columns WHERE table_schema='opportunity' AND table_name='opportunities' AND column_name='rule_version';")"
assert_value demo_studio_configuration_upgraded "$precise_products" \
  "$(sql_database "$MIGRATION_DATABASE" "SELECT configuration_json::jsonb#>'{recommendation,products}' FROM rule.rule_versions WHERE id='$studio_demo_version_id';")"
assert_value demo_studio_action_upgraded "$precise_products" \
  "$(sql_database "$MIGRATION_DATABASE" "SELECT product_codes_json FROM rule.rule_actions WHERE rule_version_id='$studio_demo_version_id';")"
studio_configuration=$(sql_database "$MIGRATION_DATABASE" "SELECT configuration_json::text FROM rule.rule_versions WHERE id='$studio_demo_version_id';")
stored_checksum=$(sql_database "$MIGRATION_DATABASE" "SELECT checksum FROM rule.rule_versions WHERE id='$studio_demo_version_id';")
calculated_checksum=$(printf '%s' "$(jq -cS . <<<"$studio_configuration")" | sha256sum | awk '{print $1}')
assert_value demo_studio_checksum_recomputed "$calculated_checksum" "$stored_checksum"
assert_value technical_demo_rules_upgraded 4 \
  "$(sql_database "$MIGRATION_DATABASE" "SELECT count(*) FROM opportunity.opportunity_rules WHERE created_by='demo-data-generator' AND version='1' AND ((opportunity_type='INVESTMENT_FINANCING' AND configuration_json::jsonb->'recommended_product_codes'='[\"BOA_CREDIT_MLTD_DIRECT\",\"BOA_BAIL_ENTREPRISE\",\"BOA_ISTITMAR_MAROC_PME\"]'::jsonb) OR (opportunity_type='TRADE_FINANCE' AND configuration_json::jsonb->'recommended_product_codes'='[\"BOA_CREDIT_DOCUMENTAIRE\",\"BOA_FINANCEMENT_IMPORTATIONS\",\"BOA_PREFINANCEMENT_EXPORT\"]'::jsonb) OR (opportunity_type='CASH_INVESTMENT' AND configuration_json::jsonb->'recommended_product_codes'='[\"BOA_DEPOT_A_TERME\",\"BOA_BON_DE_CAISSE\",\"BOA_OPCVM\"]'::jsonb) OR (opportunity_type='FINANCIAL_STRESS_SIGNAL' AND configuration_json::jsonb->'recommended_product_codes'='[\"BOA_PACK_BUSINESS_PME\",\"BOA_CREDIT_CAMPAGNE\"]'::jsonb));")"
user_after_upgrade=$(sql_database "$MIGRATION_DATABASE" "SELECT md5(rv.configuration_json::text||rv.checksum||a.product_codes_json::text) FROM rule.rule_versions rv JOIN rule.rule_actions a ON a.rule_version_id=rv.id WHERE rv.id='$studio_user_version_id';")
assert_value user_rule_preserved_on_upgrade "$user_before" "$user_after_upgrade"
assert_value user_opportunity_rule_preserved_on_upgrade "$legacy_products" \
  "$(sql_database "$MIGRATION_DATABASE" "SELECT configuration_json::jsonb->'recommended_product_codes' FROM opportunity.opportunity_rules WHERE opportunity_type='USER_CASE';")"

alembic "$MIGRATION_DATABASE" "downgrade 0017_ml_shadow_governance"
assert_value downgrade_to_0017 0017_ml_shadow_governance \
  "$(sql_database "$MIGRATION_DATABASE" 'SELECT version_num FROM alembic_version')"
assert_value catalog_columns_removed 0 \
  "$(sql_database "$MIGRATION_DATABASE" "SELECT count(*) FROM information_schema.columns WHERE table_schema='product' AND table_name='products' AND column_name IN ('family','description','source_url');")"
assert_value rule_version_width_restored 30 \
  "$(sql_database "$MIGRATION_DATABASE" "SELECT character_maximum_length FROM information_schema.columns WHERE table_schema='opportunity' AND table_name='opportunities' AND column_name='rule_version';")"
assert_value demo_studio_configuration_restored "$legacy_products" \
  "$(sql_database "$MIGRATION_DATABASE" "SELECT configuration_json::jsonb#>'{recommendation,products}' FROM rule.rule_versions WHERE id='$studio_demo_version_id';")"
assert_value demo_studio_action_restored "$legacy_products" \
  "$(sql_database "$MIGRATION_DATABASE" "SELECT product_codes_json FROM rule.rule_actions WHERE rule_version_id='$studio_demo_version_id';")"
user_after_downgrade=$(sql_database "$MIGRATION_DATABASE" "SELECT md5(rv.configuration_json::text||rv.checksum||a.product_codes_json::text) FROM rule.rule_versions rv JOIN rule.rule_actions a ON a.rule_version_id=rv.id WHERE rv.id='$studio_user_version_id';")
assert_value user_rule_preserved_on_downgrade "$user_before" "$user_after_downgrade"

alembic "$MIGRATION_DATABASE" "upgrade 0018_product_catalog"
assert_value reupgrade_to_0018 0018_product_catalog \
  "$(sql_database "$MIGRATION_DATABASE" 'SELECT version_num FROM alembic_version')"
assert_value demo_studio_reupgraded "$precise_products" \
  "$(sql_database "$MIGRATION_DATABASE" "SELECT configuration_json::jsonb#>'{recommendation,products}' FROM rule.rule_versions WHERE id='$studio_demo_version_id';")"

alembic "$FRESH_DATABASE" "upgrade head"
assert_value fresh_upgrade_to_0018 0018_product_catalog \
  "$(sql_database "$FRESH_DATABASE" 'SELECT version_num FROM alembic_version')"
assert_value fresh_product_columns 3 \
  "$(sql_database "$FRESH_DATABASE" "SELECT count(*) FROM information_schema.columns WHERE table_schema='product' AND table_name='products' AND column_name IN ('family','description','source_url');")"
assert_value fresh_rule_version_width 80 \
  "$(sql_database "$FRESH_DATABASE" "SELECT character_maximum_length FROM information_schema.columns WHERE table_schema='opportunity' AND table_name='opportunities' AND column_name='rule_version';")"

source_digest=$(
  cd "$PROJECT_ROOT"
  sha256sum \
    backend/src/boa_oi/models/entities.py \
    database/migrations/versions/0001_initial.py \
    database/migrations/versions/0018_product_catalog.py \
    scripts/validate-product-catalog-migration.sh \
    | sha256sum | awk '{print $1}'
)

jq -n \
  --arg runId "product-catalog-migration-$(date -u +%Y%m%dT%H%M%SZ)" \
  --arg generatedAt "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg baseCommit "$(git -C "$PROJECT_ROOT" rev-parse HEAD)" \
  --arg sourceDigest "$source_digest" \
  --arg migrationDatabase "$MIGRATION_DATABASE" \
  --arg freshDatabase "$FRESH_DATABASE" \
  '{
    runId:$runId,
    generatedAt:$generatedAt,
    status:"PASS",
    scope:"LOCAL_SYNTHETIC_POSTGRESQL_MIGRATION",
    sourceRevision:{baseCommit:$baseCommit,sourceDigest:$sourceDigest},
    environment:{migrationDatabase:$migrationDatabase,freshDatabase:$freshDatabase,temporaryDatabasesRemovedOnExit:true},
    checks:{
      freshUpgrade0001To0018:"PASS",
      existingUpgrade0017To0018:"PASS",
      downgrade0018To0017:"PASS",
      reupgrade0017To0018:"PASS",
      productMetadataColumns:"PASS",
      ruleVersionWidth80:"PASS",
      legacyFamilyBackfill:"PASS",
      knownSyntheticTechnicalRulesMigrated:"PASS",
      knownSyntheticRuleStudioMigratedWithChecksum:"PASS",
      userControlledRulesNotRewritten:"PASS"
    },
    limitations:[
      "Bases PostgreSQL Docker temporaires et fixtures synthétiques uniquement.",
      "La migration transforme exclusivement les règles connues créées par demo-data-generator; elle ne réécrit aucune règle utilisateur ou BOA.",
      "Les règles existantes avec un code produit inconnu restent intactes; les nouvelles écritures et la consommation Opportunity échouent désormais explicitement au lieu de masquer le code."
    ]
  }' >"$OUTPUT_FILE"

printf '[catalog-migration] PASS: %s\n' "$OUTPUT_FILE"
