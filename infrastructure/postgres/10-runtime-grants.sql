\set ON_ERROR_STOP on

SELECT format('ALTER SCHEMA notification OWNER TO %I', :'admin_role') \gexec

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
GRANT UPDATE (processing_status, processing_error) ON integration.outbox_messages TO action_service;
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
GRANT USAGE ON SCHEMA integration, config TO transaction_service;
GRANT SELECT, INSERT, UPDATE ON integration.import_batches TO transaction_service;
GRANT SELECT, INSERT, UPDATE ON integration.import_rejections TO transaction_service;
GRANT SELECT, INSERT, UPDATE ON config.transaction_categories TO transaction_service;
GRANT USAGE ON SCHEMA customer, opportunity, action, ml TO portfolio_service;
GRANT SELECT ON ALL TABLES IN SCHEMA customer, opportunity, action, ml TO portfolio_service;

-- Lot multibancarisation : droits croisés appliqués après la migration 0020.
GRANT USAGE ON SCHEMA analytics TO customer_service, product_service, opportunity_service, portfolio_service, feature_store_service, rule_management_service;
GRANT SELECT ON analytics.flow_visibility_snapshots TO customer_service, product_service, opportunity_service, portfolio_service, feature_store_service, rule_management_service;
GRANT SELECT, INSERT, UPDATE ON analytics.flow_visibility_snapshots TO analytics_service;
GRANT SELECT ON analytics.flow_visibility_policies TO analytics_service;
GRANT SELECT, INSERT, UPDATE ON analytics.flow_visibility_policies TO opportunity_service;
GRANT SELECT, UPDATE ON analytics.flow_visibility_policies TO rule_management_service;
GRANT USAGE ON SCHEMA customer TO analytics_service, feature_store_service;
GRANT SELECT ON customer.customers TO analytics_service, feature_store_service;
GRANT SELECT, INSERT ON customer.banking_relationship_declarations TO customer_service;
GRANT USAGE ON SCHEMA action TO opportunity_service, rule_management_service;
GRANT SELECT ON action.opportunity_actions TO opportunity_service, rule_management_service;
GRANT USAGE ON SCHEMA feature_store TO feature_store_service, ml_engine_service;
GRANT SELECT ON feature_store.feature_set_registry TO feature_store_service, ml_engine_service;

-- Lot 16 Financial Intelligence : le service compose via HTTP et ne lit que son
-- modèle d'autorisation. Il peut ajouter un audit, jamais le modifier ni le supprimer.
SELECT format('ALTER SCHEMA financial_intelligence OWNER TO %I', :'admin_role') \gexec
REVOKE CREATE ON SCHEMA financial_intelligence FROM financial_intelligence_service;
GRANT USAGE ON SCHEMA financial_intelligence TO financial_intelligence_service;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA financial_intelligence FROM financial_intelligence_service;
ALTER DEFAULT PRIVILEGES IN SCHEMA financial_intelligence
  REVOKE ALL ON TABLES FROM financial_intelligence_service;
GRANT SELECT ON
  financial_intelligence.external_consumers,
  financial_intelligence.external_portfolios,
  financial_intelligence.external_portfolio_companies,
  financial_intelligence.data_access_grants
TO financial_intelligence_service;
GRANT SELECT, INSERT ON financial_intelligence.access_audit TO financial_intelligence_service;
