#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
DATABASE_DIR="$PROJECT_ROOT/database"
POSTGRES_IMAGE=${POSTGRES_IMAGE:-postgres:16.15-alpine@sha256:3c5c8892d184f738f4fe282d14ddaa613a38f00f4189d2d94725ebe6f2909ddb}
POSTGRES_ADMIN_USER=${POSTGRES_ADMIN_USER:-boa_admin}
POSTGRES_ADMIN_PASSWORD=${POSTGRES_ADMIN_PASSWORD:-VisibilityMigration-LocalOnly!}
CONTAINER_NAME="boa-visibility-migration-${$}"
EXISTING_DATABASE="boa_visibility_existing_${$}"
FRESH_DATABASE="boa_visibility_fresh_${$}"
ADMIN_ONLY_DATABASE="boa_visibility_admin_only_${$}"
OUTPUT_FILE=${VISIBILITY_MIGRATION_EVIDENCE_FILE:-$PROJECT_ROOT/docs/evidence/visibility/RESULTATS-MIGRATION-VISIBILITE.json}
CHECKSUM_FILE="${OUTPUT_FILE}.sha256"
HOST_PORT=""

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'Required command not found: %s\n' "$1" >&2
    return 1
  }
}

for command in alembic docker jq python3 sha256sum; do
  require_command "$command"
done

if [[ -S /var/run/docker.sock && ! -w /var/run/docker.sock ]] && command -v sudo >/dev/null; then
  DOCKER=(sudo -n docker)
else
  DOCKER=(docker)
fi

cleanup() {
  "${DOCKER[@]}" rm --force "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

assert_value() {
  local label=$1 expected=$2 actual=$3
  printf '[visibility-migration] %s=%s\n' "$label" "$actual"
  [[ "$actual" == "$expected" ]]
}

sql() {
  local database=$1 query=$2
  "${DOCKER[@]}" exec "$CONTAINER_NAME" psql \
    --set=ON_ERROR_STOP=1 --tuples-only --no-align \
    --username "$POSTGRES_ADMIN_USER" --dbname "$database" -c "$query"
}

alembic_run() {
  local database=$1
  shift
  local database_url="postgresql+psycopg://${POSTGRES_ADMIN_USER}:${POSTGRES_ADMIN_PASSWORD}@127.0.0.1:${HOST_PORT}/${database}"
  (
    cd "$DATABASE_DIR"
    DATABASE_URL="$database_url" PYTHONPATH="$PROJECT_ROOT/backend/src" \
      alembic -c alembic.ini "$@"
  )
}

apply_runtime_grants() {
  local database=$1
  "${DOCKER[@]}" exec --interactive "$CONTAINER_NAME" psql \
    --set=ON_ERROR_STOP=1 --username "$POSTGRES_ADMIN_USER" --dbname "$database" \
    --set=admin_role="$POSTGRES_ADMIN_USER" \
    <"$PROJECT_ROOT/infrastructure/postgres/10-runtime-grants.sql"
}

bootstrap_roles() {
  "${DOCKER[@]}" exec --interactive "$CONTAINER_NAME" psql \
    --set=ON_ERROR_STOP=1 --username "$POSTGRES_ADMIN_USER" --dbname postgres <<'SQL'
DO $$
DECLARE
  service_role text;
BEGIN
  FOREACH service_role IN ARRAY ARRAY[
    'customer_service', 'account_service', 'transaction_service',
    'integration_service', 'analytics_service', 'signal_service',
    'opportunity_service', 'product_service', 'action_service',
    'rule_management_service', 'feature_store_service', 'ml_engine_service',
    'portfolio_service', 'notification_service', 'keycloak_service'
  ]
  LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = service_role) THEN
      EXECUTE format('CREATE ROLE %I LOGIN', service_role);
    END IF;
  END LOOP;
END $$;
SQL
}

bootstrap_schemas() {
  local database=$1
  sql "$database" '
DO $$
DECLARE
  item text[];
BEGIN
  FOREACH item SLICE 1 IN ARRAY ARRAY[
    ARRAY['"'"'customer_service'"'"','"'"'customer'"'"'],
    ARRAY['"'"'account_service'"'"','"'"'account'"'"'],
    ARRAY['"'"'transaction_service'"'"','"'"'transaction'"'"'],
    ARRAY['"'"'integration_service'"'"','"'"'integration'"'"'],
    ARRAY['"'"'analytics_service'"'"','"'"'analytics'"'"'],
    ARRAY['"'"'signal_service'"'"','"'"'signal'"'"'],
    ARRAY['"'"'opportunity_service'"'"','"'"'opportunity'"'"'],
    ARRAY['"'"'product_service'"'"','"'"'product'"'"'],
    ARRAY['"'"'action_service'"'"','"'"'action'"'"'],
    ARRAY['"'"'rule_management_service'"'"','"'"'rule_management'"'"'],
    ARRAY['"'"'feature_store_service'"'"','"'"'feature_store'"'"'],
    ARRAY['"'"'ml_engine_service'"'"','"'"'ml'"'"'],
    ARRAY['"'"'portfolio_service'"'"','"'"'portfolio'"'"'],
    ARRAY['"'"'notification_service'"'"','"'"'notification'"'"'],
    ARRAY['"'"'keycloak_service'"'"','"'"'keycloak'"'"']
  ]
  LOOP
    EXECUTE format('"'"'CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION %I'"'"', item[2], item[1]);
    EXECUTE format('"'"'REVOKE ALL ON SCHEMA %I FROM PUBLIC'"'"', item[2]);
  END LOOP;
END $$;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
' >/dev/null
}

column_count() {
  local database=$1 schema=$2 table=$3 columns=$4
  sql "$database" "
    SELECT count(*)
      FROM information_schema.columns
     WHERE table_schema='${schema}' AND table_name='${table}'
       AND column_name = ANY (string_to_array('${columns}', ','));"
}

relation_count() {
  local database=$1
  sql "$database" "
    SELECT count(*)
      FROM information_schema.tables
     WHERE (table_schema, table_name) IN (
       ('customer','banking_relationship_declarations'),
       ('analytics','flow_visibility_snapshots'),
       ('analytics','flow_visibility_policies'),
       ('feature_store','feature_set_registry')
     );"
}

privilege() {
  local database=$1 role=$2 privilege_name=$3 object_name=$4
  sql "$database" "SELECT has_table_privilege('${role}', '${object_name}', '${privilege_name}');"
}

schema_privilege() {
  local database=$1 role=$2 schema_name=$3
  sql "$database" "SELECT has_schema_privilege('${role}', '${schema_name}', 'USAGE');"
}

mkdir -p "$(dirname -- "$OUTPUT_FILE")"
"${DOCKER[@]}" run --detach --rm \
  --name "$CONTAINER_NAME" \
  --publish 127.0.0.1::5432 \
  --env "POSTGRES_DB=postgres" \
  --env "POSTGRES_USER=$POSTGRES_ADMIN_USER" \
  --env "POSTGRES_PASSWORD=$POSTGRES_ADMIN_PASSWORD" \
  "$POSTGRES_IMAGE" >/dev/null

for _ in $(seq 1 60); do
  if "${DOCKER[@]}" exec "$CONTAINER_NAME" pg_isready \
    --username "$POSTGRES_ADMIN_USER" --dbname postgres >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
"${DOCKER[@]}" exec "$CONTAINER_NAME" pg_isready \
  --username "$POSTGRES_ADMIN_USER" --dbname postgres >/dev/null
HOST_PORT=$("${DOCKER[@]}" port "$CONTAINER_NAME" 5432/tcp | awk -F: 'END {print $NF}')
[[ "$HOST_PORT" =~ ^[0-9]+$ ]]

"${DOCKER[@]}" exec "$CONTAINER_NAME" createdb \
  --username "$POSTGRES_ADMIN_USER" "$ADMIN_ONLY_DATABASE"
assert_value admin_only_service_roles_absent 0 "$(sql postgres "
  SELECT count(*) FROM pg_roles
   WHERE rolname IN ('customer_service','analytics_service','opportunity_service',
                     'rule_management_service','feature_store_service','ml_engine_service');")"
alembic_run "$ADMIN_ONLY_DATABASE" upgrade head
assert_value admin_only_upgrade_to_head 0020_multibank_visibility \
  "$(sql "$ADMIN_ONLY_DATABASE" 'SELECT version_num FROM alembic_version')"
alembic_run "$ADMIN_ONLY_DATABASE" downgrade base
assert_value admin_only_downgrade_to_base 0 "$(sql "$ADMIN_ONLY_DATABASE" "
  SELECT count(*) FROM public.alembic_version;")"
alembic_run "$ADMIN_ONLY_DATABASE" upgrade head
assert_value admin_only_reupgrade_to_head 0020_multibank_visibility \
  "$(sql "$ADMIN_ONLY_DATABASE" 'SELECT version_num FROM alembic_version')"

bootstrap_roles
"${DOCKER[@]}" exec "$CONTAINER_NAME" createdb \
  --username "$POSTGRES_ADMIN_USER" "$EXISTING_DATABASE"
"${DOCKER[@]}" exec "$CONTAINER_NAME" createdb \
  --username "$POSTGRES_ADMIN_USER" "$FRESH_DATABASE"
bootstrap_schemas "$EXISTING_DATABASE"
bootstrap_schemas "$FRESH_DATABASE"

head_count=$(
  cd "$DATABASE_DIR"
  PYTHONPATH="$PROJECT_ROOT/backend/src" alembic -c alembic.ini heads | grep -c '(head)$'
)
assert_value unique_alembic_head 1 "$head_count"

# Existing-database path: build the exact parent schema and prove 0020 objects are absent.
alembic_run "$EXISTING_DATABASE" upgrade 0019_ml_studio_catalog_merge
assert_value existing_starts_at_0019 0019_ml_studio_catalog_merge \
  "$(sql "$EXISTING_DATABASE" 'SELECT version_num FROM alembic_version')"
assert_value pre0020_customer_columns_absent 0 \
  "$(column_count "$EXISTING_DATABASE" customer customers 'banking_relationship,banking_relationship_declared_at,banking_relationship_declared_by,banking_relationship_reason,banking_relationship_source,declared_turnover,declared_turnover_as_of,declared_turnover_entered_by,declared_turnover_source')"
assert_value pre0020_transaction_columns_absent 0 \
  "$(column_count "$EXISTING_DATABASE" transaction transactions 'counterparty_name,remittance_information,externally_domiciled')"
assert_value pre0020_opportunity_column_absent 0 \
  "$(column_count "$EXISTING_DATABASE" opportunity opportunities 'recommendation_nature')"
assert_value pre0020_owned_relations_absent 0 "$(relation_count "$EXISTING_DATABASE")"

sql "$EXISTING_DATABASE" "
INSERT INTO config.transaction_categories
  (id, category_code, version, label, active, provenance, checksum, reason, created_by)
VALUES
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1', 'USER_SENTINEL', 'user-v1',
   'Sentinelle utilisateur', true, 'BOA_APPROVED', repeat('a', 64),
   'Oracle de conservation de données', 'business.analyst.boa');
INSERT INTO opportunity.opportunity_rules
  (id, opportunity_type, version, configuration_json, active, created_by)
VALUES
  ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1', 'USER_SENTINEL', 'user-v1',
   '{\"owner\":\"boa\",\"preserve\":true}'::json, true, 'business.analyst.boa');
" >/dev/null
sentinel_before=$(sql "$EXISTING_DATABASE" "
  SELECT md5(
    (SELECT row_to_json(c)::text FROM config.transaction_categories c
      WHERE category_code='USER_SENTINEL' AND version='user-v1') ||
    (SELECT row_to_json(r)::text FROM opportunity.opportunity_rules r
      WHERE opportunity_type='USER_SENTINEL' AND version='user-v1')
  );")

alembic_run "$EXISTING_DATABASE" upgrade 0020_multibank_visibility
apply_runtime_grants "$EXISTING_DATABASE"
assert_value existing_upgrade_to_0020 0020_multibank_visibility \
  "$(sql "$EXISTING_DATABASE" 'SELECT version_num FROM alembic_version')"
assert_value customer_columns_added 9 \
  "$(column_count "$EXISTING_DATABASE" customer customers 'banking_relationship,banking_relationship_declared_at,banking_relationship_declared_by,banking_relationship_reason,banking_relationship_source,declared_turnover,declared_turnover_as_of,declared_turnover_entered_by,declared_turnover_source')"
assert_value transaction_columns_added 3 \
  "$(column_count "$EXISTING_DATABASE" transaction transactions 'counterparty_name,remittance_information,externally_domiciled')"
assert_value opportunity_column_added 1 \
  "$(column_count "$EXISTING_DATABASE" opportunity opportunities 'recommendation_nature')"
assert_value owned_relations_added 4 "$(relation_count "$EXISTING_DATABASE")"
assert_value visibility_constraints_added 3 "$(sql "$EXISTING_DATABASE" "
  SELECT count(*) FROM pg_constraint
   WHERE conname LIKE '%ck_customers_banking_relationship'
      OR conname LIKE '%ck_customers_declared_turnover_positive'
      OR conname LIKE '%ck_opportunity_recommendation_nature';")"
assert_value flow_rule_seeded 1 "$(sql "$EXISTING_DATABASE" "
  SELECT count(*) FROM opportunity.opportunity_rules
   WHERE opportunity_type='FLOW_DOMICILIATION' AND version='1'
     AND NOT active AND created_by='migration-0020'
     AND configuration_json::jsonb->>'visibility_sensitivity'='ROBUST'
     AND configuration_json::jsonb->'recommended_product_codes'=
       '[\"BOA_PACK_BUSINESS_PME\",\"BOA_BUSINESS_ONLINE\",\"BOA_VIREMENT_MASSE\",\"BOA_PRELEVEMENT_MASSE\"]'::jsonb;")"
assert_value visibility_policy_seeded 1 "$(sql "$EXISTING_DATABASE" "
  SELECT count(*) FROM analytics.flow_visibility_policies
   WHERE policy_id='multibank-flow-visibility' AND version=1 AND active
     AND created_by='migration-0020'
     AND configuration_json::jsonb->>'status'='HYPOTHÈSE À VALIDER AVEC BOA';")"
assert_value category_seeded 1 "$(sql "$EXISTING_DATABASE" "
  SELECT count(*) FROM config.transaction_categories
   WHERE category_code='INTER_BANK_SELF_TRANSFER' AND version='multibank-v1'
     AND active AND provenance='SYNTHETIC_POC' AND created_by='migration-0020';")"
assert_value inactive_feature_set_seeded 1 "$(sql "$EXISTING_DATABASE" "
  SELECT count(*) FROM feature_store.feature_set_registry
   WHERE feature_set_version='sales-features-v3-multibank'
     AND status='REGISTERED_INACTIVE' AND created_by='migration-0020'
     AND definition_json::jsonb->>'status'='REGISTERED_INACTIVE';")"
assert_value user_data_preserved_on_upgrade "$sentinel_before" "$(sql "$EXISTING_DATABASE" "
  SELECT md5(
    (SELECT row_to_json(c)::text FROM config.transaction_categories c
      WHERE category_code='USER_SENTINEL' AND version='user-v1') ||
    (SELECT row_to_json(r)::text FROM opportunity.opportunity_rules r
      WHERE opportunity_type='USER_SENTINEL' AND version='user-v1')
  );")"

# Positive and least-privilege grant oracles after 0020.
assert_value customer_snapshot_select_granted t \
  "$(privilege "$EXISTING_DATABASE" customer_service SELECT analytics.flow_visibility_snapshots)"
assert_value customer_snapshot_insert_denied f \
  "$(privilege "$EXISTING_DATABASE" customer_service INSERT analytics.flow_visibility_snapshots)"
for role in product_service opportunity_service portfolio_service feature_store_service rule_management_service; do
  assert_value "${role}_snapshot_select_granted" t \
    "$(privilege "$EXISTING_DATABASE" "$role" SELECT analytics.flow_visibility_snapshots)"
done
for grant_name in SELECT INSERT UPDATE; do
  assert_value "analytics_snapshot_${grant_name,,}_granted" t \
    "$(privilege "$EXISTING_DATABASE" analytics_service "$grant_name" analytics.flow_visibility_snapshots)"
done
assert_value analytics_snapshot_delete_denied f \
  "$(privilege "$EXISTING_DATABASE" analytics_service DELETE analytics.flow_visibility_snapshots)"
assert_value analytics_visibility_policy_select_granted t \
  "$(privilege "$EXISTING_DATABASE" analytics_service SELECT analytics.flow_visibility_policies)"
assert_value analytics_visibility_policy_update_denied f \
  "$(privilege "$EXISTING_DATABASE" analytics_service UPDATE analytics.flow_visibility_policies)"
for grant_name in SELECT INSERT UPDATE; do
  assert_value "opportunity_visibility_policy_${grant_name,,}_granted" t \
    "$(privilege "$EXISTING_DATABASE" opportunity_service "$grant_name" analytics.flow_visibility_policies)"
done
assert_value opportunity_visibility_policy_delete_denied f \
  "$(privilege "$EXISTING_DATABASE" opportunity_service DELETE analytics.flow_visibility_policies)"
for grant_name in SELECT UPDATE; do
  assert_value "rule_management_visibility_policy_${grant_name,,}_granted" t \
    "$(privilege "$EXISTING_DATABASE" rule_management_service "$grant_name" analytics.flow_visibility_policies)"
done
assert_value rule_management_visibility_policy_insert_denied f \
  "$(privilege "$EXISTING_DATABASE" rule_management_service INSERT analytics.flow_visibility_policies)"
assert_value analytics_customer_select_granted t \
  "$(privilege "$EXISTING_DATABASE" analytics_service SELECT customer.customers)"
assert_value feature_store_customer_select_granted t \
  "$(privilege "$EXISTING_DATABASE" feature_store_service SELECT customer.customers)"
assert_value opportunity_action_select_granted t \
  "$(privilege "$EXISTING_DATABASE" opportunity_service SELECT action.opportunity_actions)"
assert_value rule_simulation_action_select_granted t \
  "$(privilege "$EXISTING_DATABASE" rule_management_service SELECT action.opportunity_actions)"
assert_value rule_simulation_action_insert_denied f \
  "$(privilege "$EXISTING_DATABASE" rule_management_service INSERT action.opportunity_actions)"
assert_value feature_store_registry_select_granted t \
  "$(privilege "$EXISTING_DATABASE" feature_store_service SELECT feature_store.feature_set_registry)"
assert_value ml_registry_select_granted t \
  "$(privilege "$EXISTING_DATABASE" ml_engine_service SELECT feature_store.feature_set_registry)"
assert_value ml_feature_store_usage_granted t \
  "$(schema_privilege "$EXISTING_DATABASE" ml_engine_service feature_store)"

# A direct business value in a 0020 column must make downgrade fail closed.
sql "$EXISTING_DATABASE" "
INSERT INTO customer.relationship_managers
  (id, subject_id, display_name, branch_code, active, created_by)
VALUES
  ('cccccccc-cccc-cccc-cccc-ccccccccccc1', 'rm-downgrade-guard',
   'Sentinelle downgrade', 'BR-GUARD', true, 'migration-test');
INSERT INTO customer.customers
  (id, customer_ref, legal_name, sector_code, segment_code, scenario_code,
   incorporated_on, status, banking_relationship, rm_id, created_by)
VALUES
  ('dddddddd-dddd-dddd-dddd-ddddddddddd1', 'SME-DOWNGRADE-GUARD',
   'PME sentinelle downgrade', 'SERVICES', 'SMALL', 'GUARD', '2020-01-01',
   'ACTIVE', 'SECONDARY', 'cccccccc-cccc-cccc-cccc-ccccccccccc1',
   'migration-test');
" >/dev/null
if alembic_run "$EXISTING_DATABASE" downgrade 0019_ml_studio_catalog_merge; then
  printf '[visibility-migration] FAIL protected downgrade unexpectedly succeeded\n' >&2
  exit 1
fi
assert_value protected_downgrade_keeps_0020 0020_multibank_visibility \
  "$(sql "$EXISTING_DATABASE" 'SELECT version_num FROM alembic_version')"
sql "$EXISTING_DATABASE" "
DELETE FROM customer.customers WHERE customer_ref='SME-DOWNGRADE-GUARD';
DELETE FROM customer.relationship_managers WHERE subject_id='rm-downgrade-guard';
" >/dev/null

alembic_run "$EXISTING_DATABASE" downgrade 0019_ml_studio_catalog_merge
assert_value downgrade_to_0019 0019_ml_studio_catalog_merge \
  "$(sql "$EXISTING_DATABASE" 'SELECT version_num FROM alembic_version')"
assert_value downgrade_customer_columns_removed 0 \
  "$(column_count "$EXISTING_DATABASE" customer customers 'banking_relationship,banking_relationship_declared_at,banking_relationship_declared_by,banking_relationship_reason,banking_relationship_source,declared_turnover,declared_turnover_as_of,declared_turnover_entered_by,declared_turnover_source')"
assert_value downgrade_transaction_columns_removed 0 \
  "$(column_count "$EXISTING_DATABASE" transaction transactions 'counterparty_name,remittance_information,externally_domiciled')"
assert_value downgrade_opportunity_column_removed 0 \
  "$(column_count "$EXISTING_DATABASE" opportunity opportunities 'recommendation_nature')"
assert_value downgrade_relations_removed 0 "$(relation_count "$EXISTING_DATABASE")"
assert_value migration_seeds_removed 0 "$(sql "$EXISTING_DATABASE" "
  SELECT
    (SELECT count(*) FROM config.transaction_categories
      WHERE category_code='INTER_BANK_SELF_TRANSFER' AND version='multibank-v1') +
    (SELECT count(*) FROM opportunity.opportunity_rules
      WHERE opportunity_type='FLOW_DOMICILIATION' AND version='1');")"
assert_value user_data_preserved_on_downgrade "$sentinel_before" "$(sql "$EXISTING_DATABASE" "
  SELECT md5(
    (SELECT row_to_json(c)::text FROM config.transaction_categories c
      WHERE category_code='USER_SENTINEL' AND version='user-v1') ||
    (SELECT row_to_json(r)::text FROM opportunity.opportunity_rules r
      WHERE opportunity_type='USER_SENTINEL' AND version='user-v1')
  );")"
alembic_run "$EXISTING_DATABASE" upgrade 0020_multibank_visibility
apply_runtime_grants "$EXISTING_DATABASE"
assert_value reupgrade_to_0020 0020_multibank_visibility \
  "$(sql "$EXISTING_DATABASE" 'SELECT version_num FROM alembic_version')"
assert_value reupgrade_relations_restored 4 "$(relation_count "$EXISTING_DATABASE")"
assert_value reupgrade_seeds_restored 2 "$(sql "$EXISTING_DATABASE" "
  SELECT
    (SELECT count(*) FROM config.transaction_categories
      WHERE category_code='INTER_BANK_SELF_TRANSFER' AND version='multibank-v1') +
    (SELECT count(*) FROM opportunity.opportunity_rules
      WHERE opportunity_type='FLOW_DOMICILIATION' AND version='1');")"
assert_value reupgrade_grant_restored t \
  "$(privilege "$EXISTING_DATABASE" opportunity_service SELECT action.opportunity_actions)"
assert_value reupgrade_rule_simulation_grant_restored t \
  "$(privilege "$EXISTING_DATABASE" rule_management_service SELECT action.opportunity_actions)"
assert_value reupgrade_rule_snapshot_grant_restored t \
  "$(privilege "$EXISTING_DATABASE" rule_management_service SELECT analytics.flow_visibility_snapshots)"
assert_value user_data_preserved_on_reupgrade "$sentinel_before" "$(sql "$EXISTING_DATABASE" "
  SELECT md5(
    (SELECT row_to_json(c)::text FROM config.transaction_categories c
      WHERE category_code='USER_SENTINEL' AND version='user-v1') ||
    (SELECT row_to_json(r)::text FROM opportunity.opportunity_rules r
      WHERE opportunity_type='USER_SENTINEL' AND version='user-v1')
  );")"

# Blank-database path: the P0 oracle must traverse 0001 through the unique head.
alembic_run "$FRESH_DATABASE" upgrade head
apply_runtime_grants "$FRESH_DATABASE"
assert_value fresh_upgrade_to_unique_head 0020_multibank_visibility \
  "$(sql "$FRESH_DATABASE" 'SELECT version_num FROM alembic_version')"
assert_value fresh_single_version_row 1 \
  "$(sql "$FRESH_DATABASE" 'SELECT count(*) FROM alembic_version')"
assert_value fresh_customer_columns 9 \
  "$(column_count "$FRESH_DATABASE" customer customers 'banking_relationship,banking_relationship_declared_at,banking_relationship_declared_by,banking_relationship_reason,banking_relationship_source,declared_turnover,declared_turnover_as_of,declared_turnover_entered_by,declared_turnover_source')"
assert_value fresh_transaction_columns 3 \
  "$(column_count "$FRESH_DATABASE" transaction transactions 'counterparty_name,remittance_information,externally_domiciled')"
assert_value fresh_opportunity_column 1 \
  "$(column_count "$FRESH_DATABASE" opportunity opportunities 'recommendation_nature')"
assert_value fresh_owned_relations 4 "$(relation_count "$FRESH_DATABASE")"
assert_value fresh_seed_set 4 "$(sql "$FRESH_DATABASE" "
  SELECT
    (SELECT count(*) FROM config.transaction_categories
      WHERE category_code='INTER_BANK_SELF_TRANSFER' AND version='multibank-v1') +
    (SELECT count(*) FROM opportunity.opportunity_rules
      WHERE opportunity_type='FLOW_DOMICILIATION' AND version='1') +
    (SELECT count(*) FROM analytics.flow_visibility_policies
      WHERE policy_id='multibank-flow-visibility' AND version=1 AND active) +
    (SELECT count(*) FROM feature_store.feature_set_registry
      WHERE feature_set_version='sales-features-v3-multibank'
        AND status='REGISTERED_INACTIVE');")"
assert_value fresh_privilege_oracle t \
  "$(privilege "$FRESH_DATABASE" analytics_service UPDATE analytics.flow_visibility_snapshots)"

mapfile -t migration_files < <(cd "$PROJECT_ROOT" && find database/migrations/versions -type f -name '*.py' | sort)
source_files=(
  backend/src/boa_oi/models/entities.py
  "${migration_files[@]}"
  infrastructure/postgres/10-runtime-grants.sql
  scripts/migrate.sh
  scripts/validate-visibility-migration.sh
)
source_digest=$(
  cd "$PROJECT_ROOT"
  sha256sum "${source_files[@]}" | sha256sum | awk '{print $1}'
)
source_files_json=$(printf '%s\n' "${source_files[@]}" | jq -R . | jq -s .)
postgres_version=$(sql postgres 'SHOW server_version')
alembic_version=$(alembic --version | awk '{print $2}')
base_commit=$(git -C "$PROJECT_ROOT" rev-parse HEAD)
branch=$(git -C "$PROJECT_ROOT" branch --show-current)
working_tree_state=CLEAN
if [[ -n $(git -C "$PROJECT_ROOT" status --short) ]]; then
  working_tree_state=DIRTY
fi

jq -n \
  --arg runId "visibility-migration-$(date -u +%Y%m%dT%H%M%SZ)" \
  --arg generatedAt "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg baseCommit "$base_commit" \
  --arg branch "$branch" \
  --arg workingTreeState "$working_tree_state" \
  --arg sourceDigest "$source_digest" \
  --argjson sourceFiles "$source_files_json" \
  --arg postgresImage "$POSTGRES_IMAGE" \
  --arg postgresVersion "$postgres_version" \
  --arg alembicVersion "$alembic_version" \
  --arg existingDatabase "$EXISTING_DATABASE" \
  --arg freshDatabase "$FRESH_DATABASE" \
  --arg adminOnlyDatabase "$ADMIN_ONLY_DATABASE" \
  '{
    schemaVersion:"1.0",
    runId:$runId,
    generatedAt:$generatedAt,
    status:"PASS",
    scope:"LOCAL_ISOLATED_POSTGRESQL_VISIBILITY_MIGRATION",
    sourceRevision:{
      baseCommit:$baseCommit,
      branch:$branch,
      workingTreeState:$workingTreeState,
      sourceDigest:$sourceDigest,
      digestMethod:"sha256(concatenated sha256sum output in listed order)",
      files:$sourceFiles
    },
    environment:{
      postgresImage:$postgresImage,
      postgresVersion:$postgresVersion,
      alembicVersion:$alembicVersion,
      existingDatabase:$existingDatabase,
      freshDatabase:$freshDatabase,
      adminOnlyDatabase:$adminOnlyDatabase,
      serviceRolesAndOwnedSchemasBootstrapped:true,
      alembicAdminOnlyCycleExecutedBeforeServiceRoleBootstrap:true,
      temporaryContainerAndDatabasesRemovedOnExit:true
    },
    matrix:{
      uniqueAlembicHead:{from:"revision graph",to:"0020_multibank_visibility",status:"PASS"},
      adminOnlyFullCycle:{from:"blank",to:"head",via:"base",then:"head",status:"PASS"},
      blankDatabaseToHead:{from:"blank",to:"0020_multibank_visibility",status:"PASS"},
      existingDatabaseUpgrade:{from:"0019_ml_studio_catalog_merge",to:"0020_multibank_visibility",status:"PASS"},
      downgrade:{from:"0020_multibank_visibility",to:"0019_ml_studio_catalog_merge",status:"PASS"},
      reupgrade:{from:"0019_ml_studio_catalog_merge",to:"0020_multibank_visibility",status:"PASS"}
    },
    oracles:{
      schema:{
        pre0020ObjectsAbsent:"PASS",
        all0020ColumnsAdded:"PASS",
        visibilityTablesIndexesAndConstraintsAdded:"PASS",
        all0020ObjectsRemovedOnDowngrade:"PASS",
        all0020ObjectsRestoredOnReupgrade:"PASS"
      },
      data:{
        flowDomiciliationRuleSeed:"PASS",
        selfTransferCategorySeed:"PASS",
        inactiveAntiLeakageFeatureSetSeed:"PASS",
        migrationOwnedSeedsRemovedOnDowngrade:"PASS",
        migrationOwnedSeedsRestoredOnReupgrade:"PASS",
        userControlledSentinelsPreservedAcrossCycle:"PASS",
        protectedDowngradeFailsClosed:"PASS"
      },
      privileges:{
        alembicIndependentOfNamedRuntimeRoles:"PASS",
        runtimeGrantsAppliedOutsideAlembic:"PASS",
        explicitSelectAndDmlGrantsAfterUpgrade:"PASS",
        deniedDeleteAndExcessInsert:"PASS",
        crossSchemaUsageGrantsAfterUpgrade:"PASS",
        grantsRestoredOnReupgrade:"PASS"
      }
    },
    invariants:{
      operatingMode:"POC_SHADOW",
      scoringMode:"RULES_ONLY",
      rulesWeight:1,
      mlWeight:0,
      creditDecisioning:false,
      llmOrGpuUsed:false,
      boaAssumptionsExplicit:true
    },
    limitations:[
      "Validation locale sur un conteneur PostgreSQL isolé et des sentinelles synthétiques uniquement; aucune donnée BOA réelle.",
      "La matrice valide DDL, seeds déterministes, conservation de sentinelles et privilèges SQL; elle ne mesure ni charge, ni concurrence de migration, ni réplication.",
      "Le downgrade destructif est refusé tant que des données métier 0020 sont présentes; leur export ou suppression gouvernée reste une précondition explicite.",
      "Les invariants POC_SHADOW, RULES_ONLY, rules_weight=1 et ml_weight=0 sont des contraintes du lot consignées ici; cette matrice de migration ne remplace pas les tests applicatifs dédiés."
    ]
  }' >"$OUTPUT_FILE"

sha256sum "$OUTPUT_FILE" >"$CHECKSUM_FILE"
printf '[visibility-migration] PASS: %s\n' "$OUTPUT_FILE"
printf '[visibility-migration] SHA256: %s\n' "$(awk '{print $1}' "$CHECKSUM_FILE")"
