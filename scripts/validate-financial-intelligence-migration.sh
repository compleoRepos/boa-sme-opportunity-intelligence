#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
CONTAINER=${FI_MIGRATION_CONTAINER:-boa-fi-migration-${$}}
POSTGRES_USER=${POSTGRES_ADMIN_USER:-boa_admin}
POSTGRES_PASSWORD=${POSTGRES_ADMIN_PASSWORD:-local-fi-migration-only}
ADMIN_DB=fi_admin_only_${$}
EXISTING_DB=fi_existing_${$}
EVIDENCE=${FI_MIGRATION_EVIDENCE_FILE:-$PROJECT_ROOT/docs/evidence/financial-intelligence/RESULTATS-MIGRATIONS-FI.json}
RUN_ID=${FI_MIGRATION_RUN_ID:-fi-migrations-$(date -u +%Y%m%dT%H%M%SZ)}
POSTGRES_IMAGE=${POSTGRES_IMAGE:-postgres:16-bookworm}

cleanup() {
  sudo -n docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

sudo -n docker run --rm --detach --name "$CONTAINER" \
  -e POSTGRES_USER="$POSTGRES_USER" \
  -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  -e POSTGRES_DB=postgres \
  -p 127.0.0.1::5432 "$POSTGRES_IMAGE" >/dev/null
for _ in $(seq 1 90); do
  if sudo -n docker exec "$CONTAINER" pg_isready -U "$POSTGRES_USER" -d postgres >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
sudo -n docker exec "$CONTAINER" pg_isready -U "$POSTGRES_USER" -d postgres >/dev/null
HOST_PORT=$(sudo -n docker port "$CONTAINER" 5432/tcp | awk -F: 'NR==1{print $NF}')

psql_admin() {
  local database=$1
  shift
  sudo -n docker exec -i "$CONTAINER" psql --set=ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$database" "$@"
}

sql_value() {
  local database=$1 query=$2
  psql_admin "$database" -tAc "$query" | tr -d '[:space:]'
}

create_database() {
  sudo -n docker exec "$CONTAINER" createdb -U "$POSTGRES_USER" "$1"
}

url() {
  printf 'postgresql+psycopg://%s:%s@127.0.0.1:%s/%s' \
    "$POSTGRES_USER" "$POSTGRES_PASSWORD" "$HOST_PORT" "$1"
}

alembic_run() {
  local database=$1
  shift
  (
    cd "$PROJECT_ROOT/database"
    PYTHONPATH="$PROJECT_ROOT/backend/src" DATABASE_URL="$(url "$database")" \
      python3 -m alembic -c alembic.ini "$@"
  )
}

alembic_destructive() {
  local database=$1
  shift
  (
    cd "$PROJECT_ROOT/database"
    PGOPTIONS='-c boa.allow_fi_destructive_downgrade=true' \
      PYTHONPATH="$PROJECT_ROOT/backend/src" DATABASE_URL="$(url "$database")" \
      python3 -m alembic -c alembic.ini "$@"
  )
}

assert_equal() {
  local name=$1 expected=$2 actual=$3
  if [[ "$actual" != "$expected" ]]; then
    printf 'FAIL %s: expected=%s actual=%s\n' "$name" "$expected" "$actual" >&2
    exit 1
  fi
  printf 'PASS %s=%s\n' "$name" "$actual"
}

create_database "$ADMIN_DB"
assert_equal admin_roles_absent 0 "$(sql_value postgres "SELECT count(*) FROM pg_roles WHERE rolname='financial_intelligence_service'")"
alembic_run "$ADMIN_DB" upgrade head >/dev/null
assert_equal admin_upgrade_head 0021_financial_intelligence \
  "$(sql_value "$ADMIN_DB" "SELECT version_num FROM alembic_version")"
assert_equal admin_fi_tables 5 "$(sql_value "$ADMIN_DB" "SELECT count(*) FROM information_schema.tables WHERE table_schema='financial_intelligence'")"
alembic_destructive "$ADMIN_DB" downgrade base >/dev/null
assert_equal admin_downgrade_base 0 "$(sql_value "$ADMIN_DB" "SELECT count(*) FROM information_schema.tables WHERE table_schema='financial_intelligence'")"
alembic_run "$ADMIN_DB" upgrade head >/dev/null
assert_equal admin_reupgrade_head 0021_financial_intelligence \
  "$(sql_value "$ADMIN_DB" "SELECT version_num FROM alembic_version")"

create_database "$EXISTING_DB"
alembic_run "$EXISTING_DB" upgrade 0020_multibank_visibility >/dev/null
assert_equal existing_pre0021_tables 0 "$(sql_value "$EXISTING_DB" "SELECT count(*) FROM information_schema.tables WHERE table_schema='financial_intelligence'")"
alembic_run "$EXISTING_DB" upgrade 0021_financial_intelligence >/dev/null
assert_equal existing_upgrade_0021 0021_financial_intelligence \
  "$(sql_value "$EXISTING_DB" "SELECT version_num FROM alembic_version")"

roles=(
  customer_service account_service transaction_service integration_service analytics_service
  signal_service opportunity_service product_service action_service rule_management_service
  feature_store_service ml_engine_service portfolio_service notification_service
  financial_intelligence_service keycloak_service
)
for role in "${roles[@]}"; do
  sudo -n docker exec "$CONTAINER" createuser -U "$POSTGRES_USER" "$role"
  psql_admin postgres -c "ALTER ROLE $role LOGIN PASSWORD 'local-fi-role-only'" >/dev/null
done
# shellcheck disable=SC2024 # The local shell only opens this non-sensitive file for reading.
sudo -n docker exec -i "$CONTAINER" psql --set=ON_ERROR_STOP=1 \
  -U "$POSTGRES_USER" -d "$EXISTING_DB" --set=admin_role="$POSTGRES_USER" \
  < "$PROJECT_ROOT/infrastructure/postgres/10-runtime-grants.sql" >/dev/null

psql_admin "$EXISTING_DB" <<'SQL' >/dev/null
INSERT INTO financial_intelligence.external_consumers
  (id, consumer_ref, display_name, consumer_type, status, allowed_scopes, synthetic_data)
VALUES
  ('00000000-0000-0000-0000-000000000101', 'CONSUMER-MIGRATION', 'Synthetic migration consumer',
   'FUND', 'ACTIVE', '["financial.read"]'::jsonb, true);
INSERT INTO financial_intelligence.external_portfolios
  (id, consumer_id, portfolio_ref, fund_ref, display_name, status)
VALUES
  ('00000000-0000-0000-0000-000000000102', '00000000-0000-0000-0000-000000000101',
   'PORTFOLIO-MIGRATION', 'FUND-MIGRATION', 'Synthetic migration portfolio', 'ACTIVE');
INSERT INTO financial_intelligence.external_portfolio_companies
  (id, portfolio_id, company_ref, status, valid_from)
VALUES
  ('00000000-0000-0000-0000-000000000103', '00000000-0000-0000-0000-000000000102',
   'SME-00001', 'ACTIVE', '2025-01-01T00:00:00Z');
INSERT INTO financial_intelligence.data_access_grants
  (id, grant_ref, consumer_id, portfolio_id, subject_id, client_id, scope, purpose,
   status, valid_from, valid_until, authorization_reference)
VALUES
  ('00000000-0000-0000-0000-000000000104', 'GRANT-MIGRATION',
   '00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000102',
   'external-migration', 'boa-sme-spa', 'financial.read', 'SYNTHETIC_PORTFOLIO_MONITORING', 'ACTIVE',
   '2025-01-01T00:00:00Z', '2099-01-01T00:00:00Z', 'AUTH-MIGRATION');
SQL

assert_equal admin_seeded_consumer 1 "$(sql_value "$EXISTING_DB" "SELECT count(*) FROM financial_intelligence.external_consumers")"
assert_equal runtime_select_consumer 1 "$(
  PGPASSWORD=local-fi-role-only psql -h 127.0.0.1 -p "$HOST_PORT" -U financial_intelligence_service \
    -d "$EXISTING_DB" -tAc "SELECT count(*) FROM financial_intelligence.external_consumers" | tr -d '[:space:]'
)"
psql_admin "$EXISTING_DB" -c "INSERT INTO financial_intelligence.external_consumers (id,consumer_ref,display_name,consumer_type,status,allowed_scopes,synthetic_data) VALUES ('00000000-0000-0000-0000-000000000106','CONSUMER-MISMATCH','Synthetic mismatch consumer','FUND','ACTIVE','[\"financial.read\"]'::jsonb,true)" >/dev/null
if psql_admin "$EXISTING_DB" <<'SQL' >/dev/null 2>&1
INSERT INTO financial_intelligence.data_access_grants
  (id, grant_ref, consumer_id, portfolio_id, subject_id, client_id, scope, purpose,
   status, valid_from, valid_until, authorization_reference)
VALUES
  ('00000000-0000-0000-0000-000000000107', 'GRANT-MISMATCH',
   '00000000-0000-0000-0000-000000000106', '00000000-0000-0000-0000-000000000102',
   'external-mismatch', 'boa-sme-spa', 'financial.read', 'SYNTHETIC_PORTFOLIO_MONITORING', 'ACTIVE',
   '2025-01-01T00:00:00Z', '2099-01-01T00:00:00Z', 'AUTH-MISMATCH');
SQL
then
  echo 'FAIL mismatched Consumer/Portfolio grant unexpectedly allowed' >&2
  exit 1
fi
assert_equal consumer_portfolio_integrity 1 "$(sql_value "$EXISTING_DB" "SELECT count(*) FROM financial_intelligence.data_access_grants")"
if psql_admin "$EXISTING_DB" <<'SQL' >/dev/null 2>&1
INSERT INTO financial_intelligence.data_access_grants
  (id, grant_ref, consumer_id, portfolio_id, subject_id, client_id, scope, purpose,
   status, valid_from, valid_until, authorization_reference)
VALUES
  ('00000000-0000-0000-0000-000000000109', 'GRANT-WRONG-PURPOSE',
   '00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000102',
   'external-wrong-purpose', 'boa-sme-spa', 'financial.read', 'ANOTHER_PURPOSE', 'ACTIVE',
   '2025-01-01T00:00:00Z', '2099-01-01T00:00:00Z', 'AUTH-WRONG-PURPOSE');
SQL
then
  echo 'FAIL non-authorized FI purpose unexpectedly allowed' >&2
  exit 1
fi
if psql_admin "$EXISTING_DB" <<'SQL' >/dev/null 2>&1
INSERT INTO financial_intelligence.data_access_grants
  (id, grant_ref, consumer_id, portfolio_id, subject_id, client_id, scope, purpose,
   status, valid_from, valid_until, authorization_reference)
VALUES
  ('00000000-0000-0000-0000-000000000110', 'GRANT-MISSING-CLIENT',
   '00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000102',
   'external-missing-client', NULL, 'financial.read', 'SYNTHETIC_PORTFOLIO_MONITORING', 'ACTIVE',
   '2025-01-01T00:00:00Z', '2099-01-01T00:00:00Z', 'AUTH-MISSING-CLIENT');
SQL
then
  echo 'FAIL grant without OAuth client unexpectedly allowed' >&2
  exit 1
fi
assert_equal client_purpose_constraints 1 "$(sql_value "$EXISTING_DB" "SELECT count(*) FROM financial_intelligence.data_access_grants")"
if psql_admin "$EXISTING_DB" <<'SQL' >/dev/null 2>&1
INSERT INTO financial_intelligence.external_portfolio_companies
  (id, portfolio_id, company_ref, status, valid_from, valid_until)
VALUES
  ('00000000-0000-0000-0000-000000000108', '00000000-0000-0000-0000-000000000102',
   'SME-00002', 'INACTIVE', '2025-01-01T00:00:00Z', NULL);
SQL
then
  echo 'FAIL inactive membership without valid_until unexpectedly allowed' >&2
  exit 1
fi
assert_equal inactive_membership_requires_end 1 "$(sql_value "$EXISTING_DB" "SELECT count(*) FROM financial_intelligence.external_portfolio_companies")"
PGPASSWORD=local-fi-role-only psql -h 127.0.0.1 -p "$HOST_PORT" -U financial_intelligence_service \
  -d "$EXISTING_DB" --set=ON_ERROR_STOP=1 <<'SQL' >/dev/null
INSERT INTO financial_intelligence.access_audit
  (id, subject_id, client_id, endpoint, required_scope, trace_id, result, reason_code)
VALUES
  ('00000000-0000-0000-0000-000000000105', 'external-migration', 'boa-sme-spa',
   '/migration-proof', 'financial.read', 'trace-migration', 'ALLOW', 'AUTHORIZED');
SQL

if PGPASSWORD=local-fi-role-only psql -h 127.0.0.1 -p "$HOST_PORT" \
  -U financial_intelligence_service -d "$EXISTING_DB" --set=ON_ERROR_STOP=1 \
  -c "UPDATE financial_intelligence.access_audit SET result='DENY'" >/dev/null 2>&1; then
  echo 'FAIL runtime audit update unexpectedly allowed' >&2
  exit 1
fi
if PGPASSWORD=local-fi-role-only psql -h 127.0.0.1 -p "$HOST_PORT" \
  -U financial_intelligence_service -d "$EXISTING_DB" --set=ON_ERROR_STOP=1 \
  -c "DELETE FROM financial_intelligence.access_audit" >/dev/null 2>&1; then
  echo 'FAIL runtime audit delete unexpectedly allowed' >&2
  exit 1
fi
if PGPASSWORD=local-fi-role-only psql -h 127.0.0.1 -p "$HOST_PORT" \
  -U financial_intelligence_service -d "$EXISTING_DB" --set=ON_ERROR_STOP=1 \
  -c "TRUNCATE financial_intelligence.access_audit" >/dev/null 2>&1; then
  echo 'FAIL runtime audit truncate unexpectedly allowed' >&2
  exit 1
fi
for mutation in \
  "UPDATE financial_intelligence.access_audit SET result='DENY'" \
  "DELETE FROM financial_intelligence.access_audit" \
  "TRUNCATE financial_intelligence.access_audit" \
  "SET boa.allow_fi_audit_truncate='true'; TRUNCATE financial_intelligence.access_audit"
do
  if psql_admin "$EXISTING_DB" -c "$mutation" >/dev/null 2>&1; then
    echo "FAIL administrative audit mutation unexpectedly allowed: $mutation" >&2
    exit 1
  fi
done
if PGPASSWORD=local-fi-role-only psql -h 127.0.0.1 -p "$HOST_PORT" \
  -U financial_intelligence_service -d "$EXISTING_DB" --set=ON_ERROR_STOP=1 \
  -c "INSERT INTO financial_intelligence.external_consumers (id,consumer_ref,display_name,consumer_type,status,allowed_scopes,synthetic_data) VALUES ('00000000-0000-0000-0000-000000000106','FORBIDDEN','Forbidden','FUND','ACTIVE','[]',true)" >/dev/null 2>&1; then
  echo 'FAIL runtime entitlement insert unexpectedly allowed' >&2
  exit 1
fi
if alembic_run "$EXISTING_DB" downgrade 0020_multibank_visibility >/tmp/fi-downgrade-with-data.log 2>&1; then
  echo 'FAIL destructive downgrade unexpectedly allowed' >&2
  exit 1
fi

audit_before=$(sql_value "$EXISTING_DB" "SELECT count(*) FROM financial_intelligence.access_audit")
assert_equal immutable_audit_rows 1 "$audit_before"
alembic_destructive "$EXISTING_DB" downgrade 0020_multibank_visibility >/dev/null
assert_equal existing_downgrade_0020 0020_multibank_visibility \
  "$(sql_value "$EXISTING_DB" "SELECT version_num FROM alembic_version")"
alembic_run "$EXISTING_DB" upgrade 0021_financial_intelligence >/dev/null
assert_equal existing_reupgrade_0021 0021_financial_intelligence \
  "$(sql_value "$EXISTING_DB" "SELECT version_num FROM alembic_version")"

mkdir -p "$(dirname "$EVIDENCE")"
revision=$(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null || echo UNKNOWN)
branch=$(git -C "$PROJECT_ROOT" branch --show-current 2>/dev/null || echo UNKNOWN)
code_tree=DIRTY
if [[ -z $(git -C "$PROJECT_ROOT" status --porcelain -- backend database infrastructure scripts tests) ]]; then
  code_tree=CLEAN
fi
code_digest=$(
  cd "$PROJECT_ROOT"
  git ls-files -z --cached --others --exclude-standard backend database infrastructure scripts tests \
    | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}'
)
created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
jq -n \
  --arg runId "$RUN_ID" \
  --arg createdAt "$created_at" \
  --arg revision "$revision" \
  --arg branch "$branch" \
  --arg codeTree "$code_tree" \
  --arg codeDigest "$code_digest" \
  '{
    status:"PASS",
    runId:$runId,
    createdAt:$createdAt,
    source:{revision:$revision,branch:$branch,codeTree:$codeTree,codeDigest:$codeDigest,digestScope:"migration",digestManifest:"SOURCE-MANIFEST-FI.json",digestAlgorithm:"SHA-256 of path-sorted sha256sum lines"},
    database:"PostgreSQL 16 isolated container",
    matrix:{
      adminOnlyFullCycle:"PASS",
      existing0020To0021:"PASS",
      downgrade0021To0020:"PASS",
      reupgrade0020To0021:"PASS",
      destructiveDowngradeRefusedWithData:"PASS",
      runtimeLeastPrivilege:"PASS",
      auditAppendOnly:"PASS"
      ,auditTruncateProtected:"PASS"
      ,consumerPortfolioIntegrity:"PASS"
      ,inactiveMembershipRequiresEnd:"PASS"
      ,oauthClientBinding:"PASS"
      ,purposeBinding:"PASS"
    },
    invariants:{
      serviceRoleRequiredByAlembic:false,
      serviceMayReadEntitlements:true,
      serviceMayInsertAudit:true,
      serviceMayMutateAudit:false,
      serviceMayTruncateAudit:false,
      administrativeDirectDmlProtected:true,
      serviceMayMutateEntitlements:false,
      grantPortfolioConsumerConsistency:true,
      membershipHistoryUsesValidityWindow:true,
      grantRequiresOAuthClient:true,
      grantPurposeIsFixed:true
    },
    limitations:[
      "POC / SYNTHETIC DATA / NON-PRODUCTION.",
      "La validation ne remplace pas l homologation IAM, DPO, securite et exploitation BOA.",
      "Les triggers prouvent le refus des mutations DML directes. Un propriétaire DBA peut altérer ou supprimer un trigger; une garantie WORM exige une séparation de rôles et un stockage d audit externe à valider avec BOA."
    ]
  }' > "$EVIDENCE"
jq -e '.status=="PASS" and .matrix.auditAppendOnly=="PASS"' "$EVIDENCE" >/dev/null
printf 'PASS evidence=%s\n' "$EVIDENCE"
