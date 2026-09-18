#!/usr/bin/env bash
set -Eeuo pipefail

template=/opt/boa/realm.template.json
rendered=/opt/keycloak/data/import/boa-sme-mvp-realm.json
mkdir -p "$(dirname "$rendered")"
cp "$template" "$rendered"

replace_literal() {
  local token="$1" value="$2" escaped
  escaped=${value//\\/\\\\}
  escaped=${escaped//&/\\&}
  escaped=${escaped//|/\\|}
  sed -i "s|${token}|${escaped}|g" "$rendered"
}

replace_literal 'DevOnly-Rm1-ChangeMe!' "${RM_DEMO_PASSWORD:-DevOnly-Rm1-ChangeMe!}"
replace_literal 'DevOnly-Branch1-ChangeMe!' "${BRANCH_MANAGER_DEMO_PASSWORD:-DevOnly-Branch1-ChangeMe!}"
replace_literal 'DevOnly-Admin1-ChangeMe!' "${ADMIN_DEMO_PASSWORD:-DevOnly-Admin1-ChangeMe!}"
replace_literal 'DevOnly-Analyst1-ChangeMe!' "${ANALYST_DEMO_PASSWORD:-DevOnly-Analyst1-ChangeMe!}"
replace_literal 'DevOnly-BusinessAnalyst1-ChangeMe!' "${BUSINESS_ANALYST_DEMO_PASSWORD:-DevOnly-BusinessAnalyst1-ChangeMe!}"
replace_literal 'DevOnly-RuleApprover1-ChangeMe!' "${RULE_APPROVER_DEMO_PASSWORD:-DevOnly-RuleApprover1-ChangeMe!}"
replace_literal 'DevOnly-GatewayClient-ChangeMe!' "${API_GATEWAY_CLIENT_SECRET:-DevOnly-GatewayClient-ChangeMe!}"
replace_literal 'DevOnly-PipelineClient-ChangeMe!' "${PIPELINE_CLIENT_SECRET:-DevOnly-PipelineClient-ChangeMe!}"
replace_literal 'DevOnly-CustomerClient-ChangeMe!' "${CUSTOMER_CLIENT_SECRET:-DevOnly-CustomerClient-ChangeMe!}"
replace_literal 'DevOnly-AccountClient-ChangeMe!' "${ACCOUNT_CLIENT_SECRET:-DevOnly-AccountClient-ChangeMe!}"
replace_literal 'DevOnly-TransactionClient-ChangeMe!' "${TRANSACTION_CLIENT_SECRET:-DevOnly-TransactionClient-ChangeMe!}"
replace_literal 'DevOnly-IntegrationClient-ChangeMe!' "${INTEGRATION_CLIENT_SECRET:-DevOnly-IntegrationClient-ChangeMe!}"
replace_literal 'DevOnly-AnalyticsClient-ChangeMe!' "${ANALYTICS_CLIENT_SECRET:-DevOnly-AnalyticsClient-ChangeMe!}"
replace_literal 'DevOnly-SignalClient-ChangeMe!' "${SIGNAL_CLIENT_SECRET:-DevOnly-SignalClient-ChangeMe!}"
replace_literal 'DevOnly-OpportunityClient-ChangeMe!' "${OPPORTUNITY_CLIENT_SECRET:-DevOnly-OpportunityClient-ChangeMe!}"
replace_literal 'DevOnly-ProductClient-ChangeMe!' "${PRODUCT_CLIENT_SECRET:-DevOnly-ProductClient-ChangeMe!}"
replace_literal 'DevOnly-ActionClient-ChangeMe!' "${ACTION_CLIENT_SECRET:-DevOnly-ActionClient-ChangeMe!}"
replace_literal 'DevOnly-RuleManagementClient-ChangeMe!' "${RULE_MANAGEMENT_CLIENT_SECRET:-DevOnly-RuleManagementClient-ChangeMe!}"
replace_literal 'DevOnly-RuleEngineClient-ChangeMe!' "${RULE_ENGINE_CLIENT_SECRET:-DevOnly-RuleEngineClient-ChangeMe!}"
replace_literal 'DevOnly-RuleSimulationClient-ChangeMe!' "${RULE_SIMULATION_CLIENT_SECRET:-DevOnly-RuleSimulationClient-ChangeMe!}"
replace_literal 'DevOnly-FeatureStoreClient-ChangeMe!' "${FEATURE_STORE_CLIENT_SECRET:-DevOnly-FeatureStoreClient-ChangeMe!}"
replace_literal 'DevOnly-MlEngineClient-ChangeMe!' "${ML_ENGINE_CLIENT_SECRET:-DevOnly-MlEngineClient-ChangeMe!}"
replace_literal 'DevOnly-PortfolioClient-ChangeMe!' "${PORTFOLIO_CLIENT_SECRET:-DevOnly-PortfolioClient-ChangeMe!}"

exec /opt/keycloak/bin/kc.sh "$@"
