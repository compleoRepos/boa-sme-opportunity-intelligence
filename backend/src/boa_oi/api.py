from __future__ import annotations

import os

import uvicorn


def application_for(service_name: str | None = None):
    service = (service_name or os.getenv("SERVICE_NAME") or "api-gateway").lower()
    if service == "api-gateway":
        from boa_oi.gateway_api import app
    elif service == "customer-service":
        from boa_oi.customer_api import app
    elif service == "account-service":
        from boa_oi.account_api import app
    elif service == "transaction-service":
        from boa_oi.transaction_api import app
    elif service == "mock-banking-api":
        from boa_oi.mock_banking_api import app
    elif service == "banking-integration-service":
        from boa_oi.banking_integration_api import app
    elif service == "analytics-service":
        from boa_oi.analytics_api import app
    elif service == "signal-service":
        from boa_oi.signal_api import app
    elif service == "opportunity-service":
        from boa_oi.opportunity_api import app
    elif service == "product-service":
        from boa_oi.product_api import app
    elif service == "action-service":
        from boa_oi.action_api import app
    elif service == "rule-management-service":
        from boa_oi.rule_management_api import app
    elif service == "rule-engine-service":
        from boa_oi.rule_engine_api import app
    elif service == "rule-simulation-service":
        from boa_oi.rule_simulation_api import app
    elif service == "feature-store-service":
        from boa_oi.feature_store_api import app
    elif service == "ml-engine-service":
        from boa_oi.ml_engine_api import app
    elif service == "portfolio-service":
        from boa_oi.portfolio_api import app
    else:
        raise RuntimeError(f"Unknown SERVICE_NAME: {service}")
    return app


app = application_for()


def run() -> None:
    uvicorn.run("boa_oi.api:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))


__all__ = ["app", "application_for", "run"]
