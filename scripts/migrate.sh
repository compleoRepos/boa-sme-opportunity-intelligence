#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_command docker
load_local_env
compose up --detach postgres
wait_for_healthy postgres 120

POSTGRES_DB=${POSTGRES_DB:-boa_sme}
POSTGRES_ADMIN_USER=${POSTGRES_ADMIN_USER:-boa_admin}
POSTGRES_ADMIN_PASSWORD=${POSTGRES_ADMIN_PASSWORD:-DevOnly-Postgres-ChangeMe!}
CUSTOMER_DB_PASSWORD=${CUSTOMER_DB_PASSWORD:-DevOnly-CustomerDb-ChangeMe!}
ACCOUNT_DB_PASSWORD=${ACCOUNT_DB_PASSWORD:-DevOnly-AccountDb-ChangeMe!}
TRANSACTION_DB_PASSWORD=${TRANSACTION_DB_PASSWORD:-DevOnly-TransactionDb-ChangeMe!}
INTEGRATION_DB_PASSWORD=${INTEGRATION_DB_PASSWORD:-DevOnly-IntegrationDb-ChangeMe!}
ANALYTICS_DB_PASSWORD=${ANALYTICS_DB_PASSWORD:-DevOnly-AnalyticsDb-ChangeMe!}
SIGNAL_DB_PASSWORD=${SIGNAL_DB_PASSWORD:-DevOnly-SignalDb-ChangeMe!}
OPPORTUNITY_DB_PASSWORD=${OPPORTUNITY_DB_PASSWORD:-DevOnly-OpportunityDb-ChangeMe!}
PRODUCT_DB_PASSWORD=${PRODUCT_DB_PASSWORD:-DevOnly-ProductDb-ChangeMe!}
ACTION_DB_PASSWORD=${ACTION_DB_PASSWORD:-DevOnly-ActionDb-ChangeMe!}
RULE_MANAGEMENT_DB_PASSWORD=${RULE_MANAGEMENT_DB_PASSWORD:-DevOnly-RuleManagementDb-ChangeMe!}
FEATURE_STORE_DB_PASSWORD=${FEATURE_STORE_DB_PASSWORD:-DevOnly-FeatureStoreDb-ChangeMe!}
ML_ENGINE_DB_PASSWORD=${ML_ENGINE_DB_PASSWORD:-DevOnly-MlEngineDb-ChangeMe!}
PORTFOLIO_DB_PASSWORD=${PORTFOLIO_DB_PASSWORD:-DevOnly-PortfolioDb-ChangeMe!}
NOTIFICATION_DB_PASSWORD=${NOTIFICATION_DB_PASSWORD:-DevOnly-NotificationDb-ChangeMe!}
KEYCLOAK_DB_PASSWORD=${KEYCLOAK_DB_PASSWORD:-DevOnly-KeycloakDb-ChangeMe!}

# Les identités runtime relèvent du provisioning, jamais des migrations Alembic.
# Ce bootstrap est idempotent et couvre aussi une base existante ne contenant que le rôle admin.
for role_spec in \
  "customer_service:$CUSTOMER_DB_PASSWORD:customer" \
  "account_service:$ACCOUNT_DB_PASSWORD:account" \
  "transaction_service:$TRANSACTION_DB_PASSWORD:transaction" \
  "integration_service:$INTEGRATION_DB_PASSWORD:integration" \
  "analytics_service:$ANALYTICS_DB_PASSWORD:analytics" \
  "signal_service:$SIGNAL_DB_PASSWORD:signal" \
  "opportunity_service:$OPPORTUNITY_DB_PASSWORD:opportunity" \
  "product_service:$PRODUCT_DB_PASSWORD:product" \
  "action_service:$ACTION_DB_PASSWORD:action" \
  "rule_management_service:$RULE_MANAGEMENT_DB_PASSWORD:rule" \
  "feature_store_service:$FEATURE_STORE_DB_PASSWORD:feature_store" \
  "ml_engine_service:$ML_ENGINE_DB_PASSWORD:ml" \
  "portfolio_service:$PORTFOLIO_DB_PASSWORD:portfolio" \
  "notification_service:$NOTIFICATION_DB_PASSWORD:notification" \
  "keycloak_service:$KEYCLOAK_DB_PASSWORD:keycloak"; do
  IFS=: read -r role password schema <<<"$role_spec"
  compose exec -T postgres psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_ADMIN_USER" --dbname "$POSTGRES_DB" \
    --set=role_name="$role" --set=role_password="$password" --set=schema_name="$schema" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'role_name', :'role_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role_name') \gexec
SELECT format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION %I', :'schema_name', :'role_name') \gexec
SELECT format('ALTER ROLE %I SET search_path TO %I', :'role_name', :'schema_name') \gexec
SELECT format('REVOKE ALL ON SCHEMA %I FROM PUBLIC', :'schema_name') \gexec
SELECT format('GRANT USAGE, CREATE ON SCHEMA %I TO %I', :'schema_name', :'role_name') \gexec
SQL
done

printf '%s\n' 'Applying the versioned Alembic migration exactly once with the local migration account...'
compose run --rm --no-deps --build \
  --entrypoint /bin/sh \
  --env "DATABASE_URL=postgresql+psycopg://${POSTGRES_ADMIN_USER}:${POSTGRES_ADMIN_PASSWORD}@postgres:5432/${POSTGRES_DB}" \
  customer -ec 'cd /app/database && exec alembic -c alembic.ini upgrade head'

printf '%s\n' 'Granting each runtime role access only to its owned schema...'
declare -A schema_roles=(
  [customer]=customer_service [account]=account_service [transaction]=transaction_service
  [integration]=integration_service [analytics]=analytics_service [signal]=signal_service
  [opportunity]=opportunity_service [product]=product_service [action]=action_service
  [rule]=rule_management_service [feature_store]=feature_store_service [ml]=ml_engine_service
  [portfolio]=portfolio_service [notification]=notification_service
)
for schema in "${!schema_roles[@]}"; do
  role=${schema_roles[$schema]}
  compose exec -T postgres psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_ADMIN_USER" --dbname "$POSTGRES_DB" <<SQL
GRANT USAGE ON SCHEMA "$schema" TO "$role";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "$schema" TO "$role";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA "$schema" TO "$role";
ALTER DEFAULT PRIVILEGES IN SCHEMA "$schema" GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "$role";
ALTER DEFAULT PRIVILEGES IN SCHEMA "$schema" GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO "$role";
SQL
done

compose exec -T postgres psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_ADMIN_USER" --dbname "$POSTGRES_DB" \
  --set=admin_role="$POSTGRES_ADMIN_USER" \
  <"$PROJECT_ROOT/infrastructure/postgres/10-runtime-grants.sql"
