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
RULE_MANAGEMENT_DB_PASSWORD=${RULE_MANAGEMENT_DB_PASSWORD:-DevOnly-RuleManagementDb-ChangeMe!}
FEATURE_STORE_DB_PASSWORD=${FEATURE_STORE_DB_PASSWORD:-DevOnly-FeatureStoreDb-ChangeMe!}
ML_ENGINE_DB_PASSWORD=${ML_ENGINE_DB_PASSWORD:-DevOnly-MlEngineDb-ChangeMe!}
PORTFOLIO_DB_PASSWORD=${PORTFOLIO_DB_PASSWORD:-DevOnly-PortfolioDb-ChangeMe!}
NOTIFICATION_DB_PASSWORD=${NOTIFICATION_DB_PASSWORD:-DevOnly-NotificationDb-ChangeMe!}

for role_spec in \
  "rule_management_service:$RULE_MANAGEMENT_DB_PASSWORD:rule" \
  "feature_store_service:$FEATURE_STORE_DB_PASSWORD:feature_store" \
  "ml_engine_service:$ML_ENGINE_DB_PASSWORD:ml" \
  "portfolio_service:$PORTFOLIO_DB_PASSWORD:portfolio" \
  "notification_service:$NOTIFICATION_DB_PASSWORD:notification"; do
  IFS=: read -r role password schema <<<"$role_spec"
  compose exec -T postgres psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_ADMIN_USER" --dbname "$POSTGRES_DB" \
    --set=role_name="$role" --set=role_password="$password" --set=schema_name="$schema" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'role_name', :'role_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role_name') \gexec
SELECT format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION %I', :'schema_name', :'role_name') \gexec
SQL
done

echo "Applying the versioned Alembic migration exactly once with the local migration account..."
compose run --rm --no-deps \
  --entrypoint /bin/sh \
  --env "DATABASE_URL=postgresql+psycopg://${POSTGRES_ADMIN_USER}:${POSTGRES_ADMIN_PASSWORD}@postgres:5432/${POSTGRES_DB}" \
  customer -ec 'cd /app/database && exec alembic -c alembic.ini upgrade head'

echo "Granting each runtime role access only to its owned schema..."
declare -A schema_roles=(
  [customer]=customer_service [account]=account_service [transaction]=transaction_service
  [integration]=integration_service [analytics]=analytics_service [signal]=signal_service
  [opportunity]=opportunity_service [product]=product_service [action]=action_service
  [rule]=rule_management_service [feature_store]=feature_store_service [ml]=ml_engine_service
  [notification]=notification_service
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
  --set=admin_role="$POSTGRES_ADMIN_USER" <<'SQL'
SELECT format('ALTER SCHEMA notification OWNER TO %I', :'admin_role') \gexec
SQL

compose exec -T postgres psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_ADMIN_USER" --dbname "$POSTGRES_DB" <<'SQL'
GRANT USAGE ON SCHEMA customer, analytics TO rule_management_service;
GRANT SELECT ON ALL TABLES IN SCHEMA customer, analytics TO rule_management_service;
GRANT USAGE ON SCHEMA config TO rule_management_service;
GRANT SELECT, INSERT, UPDATE ON config.label_catalog TO rule_management_service;
GRANT SELECT, INSERT ON config.label_catalog_versions TO rule_management_service;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA customer, analytics, signal, rule FROM feature_store_service;
REVOKE USAGE ON SCHEMA customer, analytics, signal, rule FROM feature_store_service;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA customer, analytics, signal, rule, feature_store FROM ml_engine_service;
REVOKE USAGE ON SCHEMA customer, analytics, signal, rule, feature_store FROM ml_engine_service;
GRANT USAGE ON SCHEMA action TO ml_engine_service;
GRANT SELECT ON ALL TABLES IN SCHEMA action TO ml_engine_service;
GRANT USAGE ON SCHEMA opportunity TO ml_engine_service;
GRANT SELECT ON opportunity.opportunities TO ml_engine_service;
GRANT USAGE ON SCHEMA audit TO opportunity_service;
GRANT SELECT, INSERT ON audit.audit_logs TO opportunity_service;
GRANT USAGE ON SCHEMA audit TO action_service;
GRANT SELECT, INSERT ON audit.audit_logs TO action_service;
GRANT USAGE ON SCHEMA integration TO action_service;
GRANT SELECT, INSERT ON integration.outbox_messages TO action_service;
GRANT UPDATE (processing_status, processing_error)
  ON integration.outbox_messages TO action_service;
GRANT USAGE ON SCHEMA audit TO customer_service;
GRANT SELECT, INSERT ON audit.audit_logs TO customer_service;
GRANT USAGE ON SCHEMA audit TO portfolio_service;
GRANT SELECT, INSERT ON audit.audit_logs TO portfolio_service;
GRANT USAGE ON SCHEMA integration TO customer_service;
GRANT SELECT, INSERT ON integration.outbox_messages TO customer_service;
GRANT USAGE ON SCHEMA integration TO notification_service;
REVOKE ALL PRIVILEGES ON integration.outbox_messages FROM notification_service;
GRANT SELECT ON integration.outbox_messages TO notification_service;
GRANT UPDATE (published_at, attempt_count, processing_status, processing_error)
  ON integration.outbox_messages TO notification_service;
ALTER TABLE integration.outbox_messages ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS outbox_integration_owner ON integration.outbox_messages;
CREATE POLICY outbox_integration_owner ON integration.outbox_messages
  FOR ALL TO integration_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS outbox_action_producer ON integration.outbox_messages;
CREATE POLICY outbox_action_producer ON integration.outbox_messages
  FOR INSERT TO action_service WITH CHECK (event_type = 'ACTION_NOTIFICATION_REQUESTED');
DROP POLICY IF EXISTS outbox_action_reader ON integration.outbox_messages;
CREATE POLICY outbox_action_reader ON integration.outbox_messages
  FOR SELECT TO action_service USING (event_type = 'ACTION_NOTIFICATION_REQUESTED');
DROP POLICY IF EXISTS outbox_action_updater ON integration.outbox_messages;
CREATE POLICY outbox_action_updater ON integration.outbox_messages
  FOR UPDATE TO action_service
  USING (event_type = 'ACTION_NOTIFICATION_REQUESTED')
  WITH CHECK (event_type = 'ACTION_NOTIFICATION_REQUESTED');
DROP POLICY IF EXISTS outbox_customer_producer ON integration.outbox_messages;
CREATE POLICY outbox_customer_producer ON integration.outbox_messages
  FOR INSERT TO customer_service WITH CHECK (event_type = 'PORTFOLIO_ASSIGNMENT_CHANGED');
DROP POLICY IF EXISTS outbox_notification_consumer ON integration.outbox_messages;
CREATE POLICY outbox_notification_consumer ON integration.outbox_messages
  FOR ALL TO notification_service
  USING (event_type = 'ACTION_NOTIFICATION_REQUESTED')
  WITH CHECK (event_type = 'ACTION_NOTIFICATION_REQUESTED');
REVOKE CREATE ON SCHEMA notification FROM notification_service;
GRANT USAGE ON SCHEMA notification TO notification_service;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA notification FROM notification_service;
ALTER DEFAULT PRIVILEGES IN SCHEMA notification REVOKE ALL ON TABLES FROM notification_service;
GRANT SELECT, INSERT, UPDATE ON notification.notification_messages TO notification_service;
GRANT SELECT, INSERT, UPDATE ON notification.notification_digest_subscriptions TO notification_service;
GRANT SELECT, INSERT ON notification.notification_delivery_attempts TO notification_service;
GRANT USAGE ON SCHEMA customer TO opportunity_service;
GRANT SELECT ON customer.customers, customer.relationship_managers, customer.portfolio_assignments TO opportunity_service;
GRANT USAGE ON SCHEMA integration TO analytics_service;
GRANT SELECT, INSERT, UPDATE ON integration.import_batches TO analytics_service;
GRANT USAGE ON SCHEMA customer, opportunity, action, ml TO portfolio_service;
GRANT SELECT ON ALL TABLES IN SCHEMA customer, opportunity, action, ml TO portfolio_service;
SQL
