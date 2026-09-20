from __future__ import annotations

import os
from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from boa_oi.http_clients import service_binary_request, service_request
from boa_oi.platform import (
    ADMIN_ROLES,
    COMMERCIAL_ROLES,
    READ_ROLES,
    Principal,
    Problem,
    correlation_id,
    create_service_app,
    require_roles,
)

app = create_service_app(
    "api-gateway",
    "The only public HTTP entry point; JWT/RBAC, routing, correlation "
    "and normalized dependency errors.",
    database=False,
)

SERVICES = {
    "customer": "CUSTOMER_SERVICE_URL",
    "account": "ACCOUNT_SERVICE_URL",
    "transaction": "TRANSACTION_SERVICE_URL",
    "analytics": "ANALYTICS_SERVICE_URL",
    "signal": "SIGNAL_SERVICE_URL",
    "opportunity": "OPPORTUNITY_SERVICE_URL",
    "product": "PRODUCT_SERVICE_URL",
    "action": "ACTION_SERVICE_URL",
    "integration": "BANKING_INTEGRATION_SERVICE_URL",
    "rule-management": "RULE_MANAGEMENT_SERVICE_URL",
    "rule-engine": "RULE_ENGINE_SERVICE_URL",
    "rule-simulation": "RULE_SIMULATION_SERVICE_URL",
    "feature-store": "FEATURE_STORE_SERVICE_URL",
    "ml-engine": "ML_ENGINE_SERVICE_URL",
    "portfolio": "PORTFOLIO_SERVICE_URL",
    "notification": "NOTIFICATION_SERVICE_URL",
}
GLOBAL_ANALYTICS_ROLES = ("DATA_ANALYST", "ADMIN", "SERVICE")


def target(service: str) -> str:
    value = os.getenv(SERVICES[service])
    if not value:
        raise Problem(
            503,
            "DEPENDENCY_CONFIGURATION_ERROR",
            f"{SERVICES[service]} is not configured.",
        )
    return value.rstrip("/")


async def authorize_customer_scope(request: Request, customer_id: str) -> None:
    await service_request(
        "GET",
        f"{target('customer')}/internal/v1/customers/{customer_id}",
        correlation_id=correlation_id(request),
        incoming_authorization=request.headers.get("Authorization"),
        dev_principal=request.headers.get("X-Dev-Principal"),
    )


async def authorize_opportunity_scope(request: Request, opportunity_id: str) -> None:
    opportunity = await service_request(
        "GET",
        f"{target('opportunity')}/internal/v1/opportunities/{opportunity_id}",
        correlation_id=correlation_id(request),
        incoming_authorization=request.headers.get("Authorization"),
        dev_principal=request.headers.get("X-Dev-Principal"),
    )
    await authorize_customer_scope(request, opportunity["customerId"])


async def proxy(
    request: Request,
    service: str,
    path: str,
    *,
    body: Any | None = None,
    idempotency_key: str | None = None,
    response_status: int | None = None,
) -> JSONResponse:
    customer_id = request.path_params.get("customer_id")
    opportunity_id = request.path_params.get("opportunity_id")
    if customer_id and service != "customer":
        await authorize_customer_scope(request, customer_id)
    if opportunity_id:
        await authorize_opportunity_scope(request, opportunity_id)
    result = await service_request(
        request.method,
        f"{target(service)}/internal/v1/{path.lstrip('/')}",
        correlation_id=correlation_id(request),
        params=dict(request.query_params),
        json=body,
        idempotency_key=idempotency_key,
        incoming_authorization=request.headers.get("Authorization"),
        dev_principal=request.headers.get("X-Dev-Principal"),
    )
    status_code = response_status or (
        201
        if request.method == "POST" and path.endswith("actions")
        else (202 if request.method == "POST" else 200)
    )
    return JSONResponse(
        result,
        status_code=status_code,
        headers={"X-Correlation-ID": correlation_id(request)},
    )


async def binary_proxy(request: Request, service: str, path: str) -> Response:
    result = await service_binary_request(
        request.method,
        f"{target(service)}/internal/v1/{path.lstrip('/')}",
        correlation_id=correlation_id(request),
        params=dict(request.query_params),
        incoming_authorization=request.headers.get("Authorization"),
        dev_principal=request.headers.get("X-Dev-Principal"),
    )
    headers = {
        "Content-Disposition": result.content_disposition or 'attachment; filename="export.xlsx"',
        "Cache-Control": "no-store",
        "X-Correlation-ID": correlation_id(request),
    }
    if result.sha256:
        headers["X-Content-SHA256"] = result.sha256
    return Response(result.content, media_type=result.media_type, headers=headers)


@app.get("/api/v1/exports/opportunities.xlsx", tags=["Exports"])
async def export_opportunities_xlsx(
    request: Request,
    _principal: Principal = Depends(require_roles(*READ_ROLES)),
) -> Response:
    return await binary_proxy(request, "opportunity", "exports/opportunities.xlsx")


@app.get("/api/v1/exports/portfolio.xlsx", tags=["Exports"])
async def export_portfolio_xlsx(
    request: Request,
    _principal: Principal = Depends(require_roles("RELATIONSHIP_MANAGER", "BRANCH_MANAGER")),
) -> Response:
    return await binary_proxy(request, "portfolio", "exports/portfolio.xlsx")


# Public GET routes consumed by frontend/src/api/hooks.ts and required by docs/api.md.
GET_ROUTES = [
    ("/api/v1/dashboards/me", "portfolio", "dashboards/me", ("RELATIONSHIP_MANAGER",)),
    ("/api/v1/dashboards/branch", "portfolio", "dashboards/branch", ("BRANCH_MANAGER",)),
    (
        "/api/v1/dashboards/relationship-managers/{relationship_manager_id}",
        "portfolio",
        "dashboards/relationship-managers/{relationship_manager_id}",
        ("BRANCH_MANAGER",),
    ),
    (
        "/api/v1/customers/{customer_id}/propensity",
        "portfolio",
        "customers/{customer_id}/propensity",
        ("RELATIONSHIP_MANAGER", "BRANCH_MANAGER", "ADMIN"),
    ),
    (
        "/api/v1/customers/{customer_id}/activity",
        "transaction",
        "customers/{customer_id}/activity",
        READ_ROLES,
    ),
    ("/api/v1/ml/models", "ml-engine", "ml/models", READ_ROLES),
    ("/api/v1/ml/models/active", "ml-engine", "ml/models/active", READ_ROLES),
    ("/api/v1/ml/models/{model_version}", "ml-engine", "ml/models/{model_version}", READ_ROLES),
    (
        "/api/v1/opportunities",
        "opportunity",
        "opportunities",
        GLOBAL_ANALYTICS_ROLES,
    ),
    (
        "/api/v1/opportunities/{opportunity_id}",
        "opportunity",
        "opportunities/{opportunity_id}",
        READ_ROLES,
    ),
    (
        "/api/v1/opportunities/{opportunity_id}/explanation",
        "opportunity",
        "opportunities/{opportunity_id}/explanation",
        READ_ROLES,
    ),
    (
        "/api/v1/opportunities/{opportunity_id}/actions",
        "action",
        "opportunities/{opportunity_id}/actions",
        READ_ROLES,
    ),
    ("/api/v1/actions", "action", "actions", READ_ROLES),
    ("/api/v1/customers", "customer", "customers", READ_ROLES),
    (
        "/api/v1/customers/{customer_id}",
        "customer",
        "customers/{customer_id}",
        READ_ROLES,
    ),
    (
        "/api/v1/customers/{customer_id}/accounts",
        "account",
        "customers/{customer_id}/accounts",
        READ_ROLES,
    ),
    (
        "/api/v1/customers/{customer_id}/products",
        "product",
        "customers/{customer_id}/products",
        READ_ROLES,
    ),
    (
        "/api/v1/customers/{customer_id}/transactions",
        "transaction",
        "customers/{customer_id}/transactions",
        READ_ROLES,
    ),
    (
        "/api/v1/customers/{customer_id}/metrics",
        "analytics",
        "customers/{customer_id}/metrics",
        READ_ROLES,
    ),
    (
        "/api/v1/customers/{customer_id}/signals",
        "signal",
        "customers/{customer_id}/signals",
        READ_ROLES,
    ),
    (
        "/api/v1/customers/{customer_id}/opportunities",
        "opportunity",
        "customers/{customer_id}/opportunities",
        READ_ROLES,
    ),
    (
        "/api/v1/customers/{customer_id}/actions",
        "action",
        "customers/{customer_id}/actions",
        READ_ROLES,
    ),
    ("/api/v1/accounts", "account", "accounts", GLOBAL_ANALYTICS_ROLES),
    (
        "/api/v1/accounts/{account_id}",
        "account",
        "accounts/{account_id}",
        GLOBAL_ANALYTICS_ROLES,
    ),
    (
        "/api/v1/accounts/{account_id}/balances",
        "account",
        "accounts/{account_id}/balances",
        GLOBAL_ANALYTICS_ROLES,
    ),
    (
        "/api/v1/accounts/{account_id}/transactions",
        "transaction",
        "accounts/{account_id}/transactions",
        GLOBAL_ANALYTICS_ROLES,
    ),
    ("/api/v1/transactions", "transaction", "transactions", GLOBAL_ANALYTICS_ROLES),
    (
        "/api/v1/transactions/{transaction_id}",
        "transaction",
        "transactions/{transaction_id}",
        GLOBAL_ANALYTICS_ROLES,
    ),
    ("/api/v1/analytics/metrics", "analytics", "metrics", GLOBAL_ANALYTICS_ROLES),
    ("/api/v1/signals", "signal", "signals", GLOBAL_ANALYTICS_ROLES),
    (
        "/api/v1/signals/{signal_id}",
        "signal",
        "signals/{signal_id}",
        GLOBAL_ANALYTICS_ROLES,
    ),
    ("/api/v1/products", "product", "products", READ_ROLES),
    ("/api/v1/products/{product_id}", "product", "products/{product_id}", READ_ROLES),
    ("/api/v1/admin/rules", "opportunity", "admin/rules", ADMIN_ROLES),
    ("/api/v1/admin/engine", "opportunity", "admin/engine", ADMIN_ROLES),
    (
        "/api/v1/metrics/dashboard",
        "action",
        "metrics/dashboard",
        GLOBAL_ANALYTICS_ROLES,
    ),
]


def register_get(
    public_path: str, service: str, internal_template: str, roles: tuple[str, ...]
) -> None:
    operation_id = "gateway_" + public_path.strip("/").replace("/", "_").replace("{", "").replace(
        "}", ""
    ).replace("-", "_")

    async def endpoint(
        request: Request, _principal: Principal = Depends(require_roles(*roles))
    ) -> JSONResponse:
        return await proxy(request, service, internal_template.format(**request.path_params))

    app.add_api_route(
        public_path,
        endpoint,
        methods=["GET"],
        tags=[service.title()],
        operation_id=operation_id,
    )


for public_path, service, internal_path, roles in GET_ROUTES:
    register_get(public_path, service, internal_path, roles)


RULE_READ_ROLES = ("BUSINESS_ANALYST", "RULE_APPROVER", "DATA_ANALYST", "ADMIN")
RULE_AUTHOR_ROLES = ("BUSINESS_ANALYST", "ADMIN")
RULE_APPROVER_ROLES = ("RULE_APPROVER", "ADMIN")


async def json_body(request: Request) -> Any:
    try:
        return await request.json()
    except ValueError as exc:
        raise Problem(400, "VALIDATION_ERROR", "The request body must be valid JSON.") from exc


@app.get("/api/v1/labels", tags=["Labels"])
async def label_catalog(
    request: Request,
    _principal: Principal = Depends(require_roles(*READ_ROLES)),
) -> JSONResponse:
    return await proxy(request, "rule-management", "labels")


@app.get("/api/v1/admin/labels/{namespace}/{code}/versions", tags=["Labels"])
async def label_catalog_versions(
    namespace: str,
    code: str,
    request: Request,
    _principal: Principal = Depends(require_roles("ADMIN")),
) -> JSONResponse:
    return await proxy(
        request,
        "rule-management",
        f"labels/{namespace}/{code}/versions",
    )


@app.put("/api/v1/admin/labels/{namespace}/{code}", tags=["Labels"])
async def update_label_catalog(
    namespace: str,
    code: str,
    request: Request,
    _principal: Principal = Depends(require_roles("ADMIN")),
) -> JSONResponse:
    return await proxy(
        request,
        "rule-management",
        f"labels/{namespace}/{code}",
        body=await json_body(request),
    )


@app.get("/api/v1/admin/notifications", tags=["Notifications"])
async def notifications(
    request: Request,
    _principal: Principal = Depends(require_roles("ADMIN")),
) -> JSONResponse:
    return await proxy(request, "notification", "notifications")


@app.get("/api/v1/admin/notifications/digest-subscriptions", tags=["Notifications"])
async def digest_subscriptions(
    request: Request,
    _principal: Principal = Depends(require_roles("ADMIN")),
) -> JSONResponse:
    return await proxy(request, "notification", "notifications/digest-subscriptions")


@app.put(
    "/api/v1/admin/notifications/digest-subscriptions/{relationship_manager_id}",
    tags=["Notifications"],
)
async def update_digest_subscription(
    relationship_manager_id: str,
    request: Request,
    _principal: Principal = Depends(require_roles("ADMIN")),
) -> JSONResponse:
    body = await request.json()
    return await proxy(
        request,
        "notification",
        f"notifications/digest-subscriptions/{relationship_manager_id}",
        body=body,
    )


@app.post("/api/v1/admin/notifications/digests/generate", tags=["Notifications"])
async def generate_notification_digests(
    request: Request,
    _principal: Principal = Depends(require_roles("ADMIN")),
) -> JSONResponse:
    return await proxy(request, "notification", "notifications/digests/generate")


@app.post("/api/v1/admin/notifications/dispatch", tags=["Notifications"])
async def dispatch_notifications(
    request: Request,
    _principal: Principal = Depends(require_roles("ADMIN")),
) -> JSONResponse:
    return await proxy(request, "notification", "notifications/dispatch")


@app.post("/api/v1/admin/notifications/{notification_id}/retry", tags=["Notifications"])
async def retry_notification(
    notification_id: str,
    request: Request,
    _principal: Principal = Depends(require_roles("ADMIN")),
) -> JSONResponse:
    return await proxy(
        request,
        "notification",
        f"notifications/{notification_id}/retry",
    )


@app.get("/api/v1/admin/portfolio-assignments", tags=["Portfolio synchronization"])
async def portfolio_assignment_history(
    request: Request,
    _principal: Principal = Depends(require_roles("ADMIN")),
) -> JSONResponse:
    return await proxy(request, "customer", "portfolio-assignments")


@app.post("/api/v1/admin/portfolio-assignments/sync", tags=["Portfolio synchronization"])
async def portfolio_assignment_sync(
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    _principal: Principal = Depends(require_roles("ADMIN")),
) -> JSONResponse:
    return await proxy(
        request,
        "customer",
        "portfolio-assignments/sync",
        body=await json_body(request),
        idempotency_key=idempotency_key,
        response_status=202,
    )


@app.api_route(
    "/api/v1/admin/scoring-policies",
    methods=["GET", "POST"],
    tags=["Scoring governance"],
)
@app.api_route(
    "/api/v1/admin/scoring-policies/{subpath:path}",
    methods=["GET", "POST"],
    tags=["Scoring governance"],
)
async def scoring_policy_governance(
    request: Request,
    subpath: str = "",
    _principal: Principal = Depends(require_roles(*RULE_READ_ROLES)),
) -> JSONResponse:
    path = "scoring-policies" + (f"/{subpath}" if subpath else "")
    body = await json_body(request) if request.method != "GET" else None
    return await proxy(request, "opportunity", path, body=body)


@app.api_route(
    "/api/v1/admin/ml/governance",
    methods=["GET", "POST"],
    tags=["ML governance"],
)
@app.api_route(
    "/api/v1/admin/ml/governance/{subpath:path}",
    methods=["GET", "POST"],
    tags=["ML governance"],
)
async def ml_governance(
    request: Request,
    subpath: str = "",
    _principal: Principal = Depends(require_roles("DATA_ANALYST", "RULE_APPROVER", "ADMIN")),
) -> JSONResponse:
    path = "ml/governance" + (f"/{subpath}" if subpath else "")
    body = await json_body(request) if request.method != "GET" else None
    return await proxy(request, "ml-engine", path, body=body)


@app.post("/api/v1/admin/ml/outcomes/materialize", tags=["ML governance"])
async def materialize_ml_outcomes(
    request: Request,
    _principal: Principal = Depends(require_roles("DATA_ANALYST", "ADMIN", "SERVICE")),
) -> JSONResponse:
    return await proxy(
        request,
        "ml-engine",
        "ml/outcomes/materialize",
        body=await json_body(request),
    )


@app.get("/api/v1/admin/ml/outcomes/snapshots", tags=["ML governance"])
async def list_ml_outcome_snapshots(
    request: Request,
    _principal: Principal = Depends(require_roles("DATA_ANALYST", "ADMIN", "SERVICE")),
) -> JSONResponse:
    return await proxy(request, "ml-engine", "ml/outcomes/snapshots")


@app.api_route(
    "/api/v1/admin/ml/datasets/manifests",
    methods=["GET", "POST"],
    tags=["ML governance"],
)
async def ml_dataset_manifests(
    request: Request,
    _principal: Principal = Depends(require_roles("DATA_ANALYST", "ADMIN", "SERVICE")),
) -> JSONResponse:
    body = await json_body(request) if request.method == "POST" else None
    return await proxy(request, "ml-engine", "ml/datasets/manifests", body=body)


@app.get("/api/v1/admin/readiness", tags=["Operations"])
async def platform_readiness(
    request: Request,
    _principal: Principal = Depends(require_roles("DATA_ANALYST", "ADMIN")),
) -> JSONResponse:
    return await proxy(request, "ml-engine", "readiness")


@app.api_route(
    "/api/v1/admin/monitoring/{subpath:path}",
    methods=["GET", "POST"],
    tags=["Operations"],
)
async def monitoring_governance(
    request: Request,
    subpath: str,
    _principal: Principal = Depends(require_roles("DATA_ANALYST", "ADMIN")),
) -> JSONResponse:
    body = await json_body(request) if request.method != "GET" else None
    return await proxy(request, "ml-engine", f"monitoring/{subpath}", body=body)


@app.get("/api/v1/rules", tags=["Rule Studio"])
async def list_rules(
    request: Request,
    _principal: Principal = Depends(require_roles(*RULE_READ_ROLES)),
) -> JSONResponse:
    return await proxy(request, "rule-management", "rules")


@app.get("/api/v1/rules/{rule_id}", tags=["Rule Studio"])
async def get_rule(
    rule_id: str,
    request: Request,
    _principal: Principal = Depends(require_roles(*RULE_READ_ROLES)),
) -> JSONResponse:
    return await proxy(request, "rule-management", f"rules/{rule_id}")


@app.post("/api/v1/rules", tags=["Rule Studio"])
async def create_rule(
    request: Request,
    _principal: Principal = Depends(require_roles(*RULE_AUTHOR_ROLES)),
) -> JSONResponse:
    return await proxy(
        request,
        "rule-management",
        "rules",
        body=await json_body(request),
        idempotency_key=request.headers.get("Idempotency-Key"),
        response_status=201,
    )


@app.put("/api/v1/rules/{rule_id}", tags=["Rule Studio"])
async def replace_rule(
    rule_id: str,
    request: Request,
    _principal: Principal = Depends(require_roles(*RULE_AUTHOR_ROLES)),
) -> JSONResponse:
    return await proxy(
        request,
        "rule-management",
        f"rules/{rule_id}",
        body=await json_body(request),
        idempotency_key=request.headers.get("Idempotency-Key"),
        response_status=200,
    )


def register_rule_get(suffix: str, service: str = "rule-management") -> None:
    async def endpoint(
        rule_id: str,
        request: Request,
        _principal: Principal = Depends(require_roles(*RULE_READ_ROLES)),
    ) -> JSONResponse:
        return await proxy(request, service, f"rules/{rule_id}/{suffix}")

    app.add_api_route(
        f"/api/v1/rules/{{rule_id}}/{suffix}",
        endpoint,
        methods=["GET"],
        tags=["Rule Studio"],
        operation_id=f"gateway_rule_{suffix}",
    )


for rule_get_suffix in ("versions", "history", "audit"):
    register_rule_get(rule_get_suffix)
register_rule_get("simulations", "rule-simulation")


def register_rule_action(
    action: str,
    service: str,
    roles: tuple[str, ...],
    response_status: int = 200,
) -> None:
    async def endpoint(
        rule_id: str,
        request: Request,
        _principal: Principal = Depends(require_roles(*roles)),
    ) -> JSONResponse:
        return await proxy(
            request,
            service,
            f"rules/{rule_id}/{action}",
            body=await json_body(request),
            idempotency_key=request.headers.get("Idempotency-Key"),
            response_status=response_status,
        )

    app.add_api_route(
        f"/api/v1/rules/{{rule_id}}/{action}",
        endpoint,
        methods=["POST"],
        tags=["Rule Studio"],
        operation_id=f"gateway_rule_{action}",
    )


for rule_action, rule_service, rule_roles, rule_status in (
    ("duplicate", "rule-management", RULE_AUTHOR_ROLES, 201),
    ("validate", "rule-management", RULE_AUTHOR_ROLES, 200),
    ("test", "rule-management", RULE_READ_ROLES, 200),
    ("simulate", "rule-simulation", RULE_AUTHOR_ROLES, 200),
    ("submit", "rule-management", RULE_AUTHOR_ROLES, 200),
    ("approve", "rule-management", RULE_APPROVER_ROLES, 200),
    ("publish", "rule-management", RULE_APPROVER_ROLES, 200),
    ("disable", "rule-management", RULE_APPROVER_ROLES, 200),
    ("rollback", "rule-management", RULE_APPROVER_ROLES, 200),
):
    register_rule_action(rule_action, rule_service, rule_roles, rule_status)


class CreateAction(BaseModel):
    actionType: str
    dueAt: str | None = None
    note: str | None = Field(default=None, max_length=4_000)


@app.post(
    "/api/v1/opportunities/{opportunity_id}/actions",
    dependencies=[Depends(require_roles(*COMMERCIAL_ROLES))],
    tags=["Actions"],
)
async def create_action(
    opportunity_id: str,
    payload: CreateAction,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
) -> JSONResponse:
    opportunity = await service_request(
        "GET",
        f"{target('opportunity')}/internal/v1/opportunities/{opportunity_id}",
        correlation_id=correlation_id(request),
        incoming_authorization=request.headers.get("Authorization"),
        dev_principal=request.headers.get("X-Dev-Principal"),
    )
    body = {
        "opportunityId": opportunity_id,
        "customerId": opportunity["customerId"],
        **payload.model_dump(exclude_none=True),
    }
    return await proxy(request, "action", "actions", body=body, idempotency_key=idempotency_key)


@app.patch(
    "/api/v1/actions/{action_id}",
    dependencies=[Depends(require_roles(*COMMERCIAL_ROLES))],
    tags=["Actions"],
)
async def update_action(action_id: str, request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except ValueError as exc:
        raise Problem(400, "VALIDATION_ERROR", "The request body must be valid JSON.") from exc
    return await proxy(request, "action", f"actions/{action_id}", body=body)


@app.patch(
    "/api/v1/admin/rules/{rule_id}",
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Administration"],
)
async def update_rule(rule_id: str, request: Request) -> JSONResponse:
    body = await request.json()
    return await proxy(request, "opportunity", f"admin/rules/{rule_id}", body=body)


class PipelineRequest(BaseModel):
    customerIds: list[str] = Field(min_length=1, max_length=500)
    asOf: date
    periods: list[str] = Field(default_factory=lambda: ["7D", "30D", "90D", "180D", "365D"])


@app.post(
    "/api/v1/admin/pipeline",
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Pipeline"],
)
async def pipeline(
    payload: PipelineRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
) -> dict[str, Any]:
    corr = correlation_id(request)
    auth = request.headers.get("Authorization")
    persona = request.headers.get("X-Dev-Principal")
    analytics = await service_request(
        "POST",
        f"{target('analytics')}/internal/v1/analytics/recompute",
        correlation_id=corr,
        idempotency_key=f"{idempotency_key}-analytics",
        json=payload.model_dump(mode="json"),
        incoming_authorization=auth,
        dev_principal=persona,
        timeout=120,
    )
    signals = await service_request(
        "POST",
        f"{target('signal')}/internal/v1/signals/evaluate",
        correlation_id=corr,
        idempotency_key=f"{idempotency_key}-signals",
        json=payload.model_dump(mode="json"),
        incoming_authorization=auth,
        dev_principal=persona,
        timeout=60,
    )
    opportunities = await service_request(
        "POST",
        f"{target('opportunity')}/internal/v1/opportunities/generate",
        correlation_id=corr,
        idempotency_key=f"{idempotency_key}-opportunities",
        json={"customerIds": payload.customerIds, "asOf": payload.asOf.isoformat()},
        incoming_authorization=auth,
        dev_principal=persona,
        timeout=60,
    )
    return {
        "status": "COMPLETED",
        "correlationId": corr,
        "analytics": analytics,
        "signals": signals,
        "opportunities": opportunities,
    }


@app.post(
    "/api/v1/admin/recompute",
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
    tags=["Pipeline"],
)
async def recompute(
    payload: PipelineRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
) -> dict[str, Any]:
    return await pipeline(payload, request, idempotency_key)


__all__ = ["app"]
