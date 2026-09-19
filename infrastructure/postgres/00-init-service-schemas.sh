#!/usr/bin/env bash
set -Eeuo pipefail

required=(
  CUSTOMER_DB_PASSWORD ACCOUNT_DB_PASSWORD TRANSACTION_DB_PASSWORD
  INTEGRATION_DB_PASSWORD ANALYTICS_DB_PASSWORD SIGNAL_DB_PASSWORD
  OPPORTUNITY_DB_PASSWORD PRODUCT_DB_PASSWORD ACTION_DB_PASSWORD
  RULE_MANAGEMENT_DB_PASSWORD KEYCLOAK_DB_PASSWORD
  FEATURE_STORE_DB_PASSWORD ML_ENGINE_DB_PASSWORD PORTFOLIO_DB_PASSWORD
  NOTIFICATION_DB_PASSWORD
)
for variable in "${required[@]}"; do
  if [[ -z "${!variable:-}" ]]; then
    echo "Missing required bootstrap variable: ${variable}" >&2
    exit 1
  fi
done

bootstrap_role_schema() {
  local role="$1" schema="$2" password="$3"
  psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=role_name="$role" --set=schema_name="$schema" --set=role_password="$password" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'role_name', :'role_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role_name') \gexec
SELECT format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION %I', :'schema_name', :'role_name') \gexec
SELECT format('ALTER ROLE %I SET search_path TO %I', :'role_name', :'schema_name') \gexec
SELECT format('REVOKE ALL ON SCHEMA %I FROM PUBLIC', :'schema_name') \gexec
SELECT format('GRANT USAGE, CREATE ON SCHEMA %I TO %I', :'schema_name', :'role_name') \gexec
SQL
}

bootstrap_role_schema customer_service customer "$CUSTOMER_DB_PASSWORD"
bootstrap_role_schema account_service account "$ACCOUNT_DB_PASSWORD"
bootstrap_role_schema transaction_service transaction "$TRANSACTION_DB_PASSWORD"
bootstrap_role_schema integration_service integration "$INTEGRATION_DB_PASSWORD"
bootstrap_role_schema analytics_service analytics "$ANALYTICS_DB_PASSWORD"
bootstrap_role_schema signal_service signal "$SIGNAL_DB_PASSWORD"
bootstrap_role_schema opportunity_service opportunity "$OPPORTUNITY_DB_PASSWORD"
bootstrap_role_schema product_service product "$PRODUCT_DB_PASSWORD"
bootstrap_role_schema action_service action "$ACTION_DB_PASSWORD"
bootstrap_role_schema rule_management_service rule_management "$RULE_MANAGEMENT_DB_PASSWORD"
bootstrap_role_schema feature_store_service feature_store "$FEATURE_STORE_DB_PASSWORD"
bootstrap_role_schema ml_engine_service ml "$ML_ENGINE_DB_PASSWORD"
bootstrap_role_schema portfolio_service portfolio "$PORTFOLIO_DB_PASSWORD"
bootstrap_role_schema notification_service notification "$NOTIFICATION_DB_PASSWORD"
bootstrap_role_schema keycloak_service keycloak "$KEYCLOAK_DB_PASSWORD"

psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL
