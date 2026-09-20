#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_command docker
require_command jq
load_local_env

POSTGRES_DB=${POSTGRES_DB:-boa_sme}
POSTGRES_ADMIN_USER=${POSTGRES_ADMIN_USER:-boa_admin}
POSTGRES_ADMIN_PASSWORD=${POSTGRES_ADMIN_PASSWORD:-DevOnly-Postgres-ChangeMe!}
TEST_DATABASE="boa_ml_migration_proof_$$"
FRESH_DATABASE="boa_ml_migration_fresh_$$"
OUTPUT_FILE=${ML_MIGRATION_EVIDENCE_FILE:-$PROJECT_ROOT/docs/evidence/ml/RESULTATS-MIGRATION-ML-SHADOW.json}

mkdir -p "$(dirname -- "$OUTPUT_FILE")"
compose up --detach postgres
wait_for_healthy postgres 120
compose exec -T postgres psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_ADMIN_USER" \
  --dbname postgres --command \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${POSTGRES_DB}' AND pid <> pg_backend_pid();" \
  >/dev/null
compose exec -T postgres createdb --username "$POSTGRES_ADMIN_USER" \
  --template "$POSTGRES_DB" "$TEST_DATABASE"
compose exec -T postgres createdb --username "$POSTGRES_ADMIN_USER" "$FRESH_DATABASE"

cleanup() {
  compose exec -T postgres dropdb --if-exists --force --username "$POSTGRES_ADMIN_USER" \
    "$TEST_DATABASE" >/dev/null 2>&1 || true
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

sql() {
  sql_database "$TEST_DATABASE" "$1"
}

assert_sql_value() {
  local label=$1 expected=$2 query=$3 value
  value=$(sql "$query")
  printf '[ml-migration] %s=%s\n' "$label" "$value"
  [[ "$value" == "$expected" ]]
}

[[ $(sql "SELECT version_num FROM alembic_version") == "0017_ml_shadow_governance" ]]
[[ $(sql "SELECT count(*) FROM opportunity.opportunities") -gt 0 ]]
[[ $(sql "SELECT count(*) FROM opportunity.scoring_policy_versions WHERE status='ACTIVE'") -eq 1 ]]

alembic "$FRESH_DATABASE" "upgrade head"
[[ $(sql_database "$FRESH_DATABASE" "SELECT version_num FROM alembic_version") == "0017_ml_shadow_governance" ]]

alembic "$TEST_DATABASE" "downgrade 0016_ingestion_governance"

opportunity_id=$(sql "SELECT id FROM opportunity.opportunities ORDER BY id LIMIT 1")
policy_version_id=$(sql "SELECT id FROM opportunity.scoring_policy_versions WHERE status='ACTIVE' ORDER BY id LIMIT 1")
policy_id=$(sql "SELECT policy_id FROM opportunity.scoring_policy_versions WHERE id='${policy_version_id}'")

sql "UPDATE opportunity.opportunities SET scoring_policy_id='rollback-hybrid-test', rules_weight=0.65, ml_weight=0.35, fallback_mode='HYBRID_ML', priority_score=73.25, priority_level='P2', priority_components_json='[{\"name\":\"rules\",\"contribution\":45},{\"name\":\"sales_propensity_ml\",\"contribution\":28.25}]'::json, explanation_json='{\"propensity\":{\"score\":0.81},\"combination\":{\"method\":\"HYBRID_RERANK\"}}'::json, engine_version='rollback-test+ml-rerank-poc-v1' WHERE id='${opportunity_id}'" >/dev/null
sql "UPDATE opportunity.scoring_policy_versions SET rules_weight=0.65, ml_weight=0.35, checksum=repeat('c',64) WHERE id='${policy_version_id}'" >/dev/null
sql "UPDATE opportunity.scoring_policies SET policy_id='rollback-hybrid-test' WHERE id='${policy_id}'" >/dev/null

snapshot_query="SELECT jsonb_build_object('opportunity',(SELECT to_jsonb(o) - 'created_at' - 'updated_at' FROM opportunity.opportunities o WHERE id='${opportunity_id}'),'policyVersion',(SELECT to_jsonb(v) - 'created_at' - 'updated_at' FROM opportunity.scoring_policy_versions v WHERE id='${policy_version_id}'),'policy',(SELECT to_jsonb(p) - 'created_at' - 'updated_at' FROM opportunity.scoring_policies p WHERE id='${policy_id}'))::text"
expected=$(sql "$snapshot_query" | jq -cS .)

alembic "$TEST_DATABASE" "upgrade 0017_ml_shadow_governance"
assert_sql_value shadow_opportunity 1 "SELECT count(*) FROM opportunity.opportunities WHERE id='${opportunity_id}' AND rules_weight=1 AND ml_weight=0 AND fallback_mode='RULES_ONLY'"
assert_sql_value shadow_policy 1 "SELECT count(*) FROM opportunity.scoring_policy_versions WHERE id='${policy_version_id}' AND rules_weight=1 AND ml_weight=0"
assert_sql_value active_policy_index 1 "SELECT count(*) FROM pg_indexes WHERE schemaname='opportunity' AND indexname='uq_scoring_policy_single_active'"
assert_sql_value effective_window_constraint 1 "SELECT count(*) FROM pg_constraint WHERE conname LIKE '%ck_scoring_policy_effective_window'"

alembic "$TEST_DATABASE" "downgrade 0016_ingestion_governance"
actual=$(sql "$snapshot_query" | jq -cS .)
printf '[ml-migration] restore_match=%s\n' "$([[ "$actual" == "$expected" ]] && echo t || echo f)"
[[ "$actual" == "$expected" ]]

alembic "$TEST_DATABASE" "upgrade 0017_ml_shadow_governance"
[[ $(sql "SELECT version_num FROM alembic_version") == "0017_ml_shadow_governance" ]]

source_digest=$(
  cd "$PROJECT_ROOT"
  sha256sum \
    backend/src/boa_oi/models/entities.py \
    database/migrations/versions/0017_ml_shadow_governance.py \
    scripts/validate-ml-migration-rollback.sh \
    | sha256sum | awk '{print $1}'
)
run_id="ml-migration-rollback-$(date -u +%Y%m%dT%H%M%SZ)"
generated_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
base_commit=$(git -C "$PROJECT_ROOT" rev-parse HEAD)

jq -n \
  --arg runId "$run_id" \
  --arg generatedAt "$generated_at" \
  --arg baseCommit "$base_commit" \
  --arg sourceDigest "$source_digest" \
  --arg sourceDatabase "$POSTGRES_DB" \
  --arg testDatabase "$TEST_DATABASE" \
  --arg freshDatabase "$FRESH_DATABASE" \
  --arg opportunityId "$opportunity_id" \
  --arg policyVersionId "$policy_version_id" \
  '{runId:$runId,generatedAt:$generatedAt,status:"PASS",scope:"LOCAL_SYNTHETIC_MIGRATION_ROLLBACK",sourceRevision:{baseCommit:$baseCommit,sourceDigest:$sourceDigest},environment:{sourceDatabase:$sourceDatabase,testDatabase:$testDatabase,freshDatabase:$freshDatabase,isolatedClone:true},objects:{opportunityId:$opportunityId,policyVersionId:$policyVersionId},checks:{freshUpgrade0001To0017:"PASS",shadowNeutralization:"PASS",exactDowngradeRestore:"PASS",reupgradeTo0017:"PASS",singleActivePolicyIndex:"PASS",effectiveWindowConstraint:"PASS"},limitations:["Base vierge et clone PostgreSQL Docker local; données du clone synthétiques uniquement.","Ce test prouve la réversibilité technique de 0017; il ne constitue ni homologation de production ni validation de performance ML."]}' >"$OUTPUT_FILE"

echo "[ml-migration] PASS: $OUTPUT_FILE"
