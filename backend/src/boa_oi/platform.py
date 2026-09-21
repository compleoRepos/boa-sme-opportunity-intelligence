from __future__ import annotations

import base64
import json
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from boa_oi import __version__

_bearer = HTTPBearer(auto_error=False)
_logger = logging.getLogger("boa.platform")
_LOCAL_ENVIRONMENTS = frozenset({"development", "local", "test"})


class Problem(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
        title: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []
        self.title = title or code.replace("_", " ").title()


class Principal(BaseModel):
    subject: str
    username: str | None = None
    email: str | None = None
    email_verified: bool = False
    roles: set[str] = Field(default_factory=set)
    scopes: set[str] = Field(default_factory=set)
    client_id: str | None = None
    branch_ids: tuple[str, ...] = ()
    customer_scopes: tuple[str, ...] = ()
    relationship_manager_ids: tuple[str, ...] = ()


def auth_disabled() -> bool:
    disabled = os.getenv("BOA_AUTH_DISABLED", "false").strip().lower() == "true"
    environment = os.getenv("APP_ENV", "unknown").strip().lower()
    if disabled and environment not in _LOCAL_ENVIRONMENTS:
        raise RuntimeError(
            "BOA_AUTH_DISABLED=true is forbidden unless APP_ENV is development, local or test."
        )
    return disabled


def _configure_platform_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    _logger.setLevel(getattr(logging, level_name, logging.INFO))
    if not any(getattr(handler, "_boa_platform_handler", False) for handler in _logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler._boa_platform_handler = True  # type: ignore[attr-defined]
        _logger.addHandler(handler)
    _logger.propagate = False


def oidc_issuer() -> str:
    configured = (
        os.getenv("OIDC_PUBLIC_ISSUER_URL")
        or os.getenv("OIDC_ISSUER")
        or os.getenv("OIDC_ISSUER_URL")
    )
    if configured:
        return configured.rstrip("/")
    keycloak_url = os.getenv("KEYCLOAK_URL")
    realm = os.getenv("KEYCLOAK_REALM") or os.getenv("BOA_KEYCLOAK_REALM")
    if not keycloak_url or not realm:
        raise Problem(503, "AUTH_CONFIGURATION_ERROR", "OIDC issuer is not configured.")
    return f"{keycloak_url.rstrip('/')}/realms/{realm}"


def oidc_internal_issuer() -> str:
    configured = os.getenv("OIDC_ISSUER_URL") or os.getenv("OIDC_ISSUER")
    if configured:
        return configured.rstrip("/")
    return oidc_issuer()


@lru_cache(maxsize=4)
def _jwk_client(jwks_url: str):
    try:
        import jwt
    except ImportError as exc:  # pragma: no cover - packaging guard
        raise Problem(503, "AUTH_CONFIGURATION_ERROR", "JWT support is unavailable.") from exc
    return jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300)


def _decode_token(token: str) -> dict[str, Any]:
    try:
        import jwt
        from jwt import ExpiredSignatureError, InvalidTokenError
    except ImportError as exc:  # pragma: no cover - packaging guard
        raise Problem(503, "AUTH_CONFIGURATION_ERROR", "JWT support is unavailable.") from exc
    allowed_issuers = {oidc_issuer().rstrip("/"), oidc_internal_issuer().rstrip("/")}
    audience = os.getenv("OAUTH_AUDIENCE") or os.getenv("OIDC_AUDIENCE")
    if not audience:
        raise Problem(503, "AUTH_CONFIGURATION_ERROR", "OIDC audience is not configured.")
    try:
        key = (
            _jwk_client(f"{oidc_internal_issuer()}/protocol/openid-connect/certs")
            .get_signing_key_from_jwt(token)
            .key
        )
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256", "RS384", "RS512"],
            audience=audience,
            options={"require": ["exp", "iss", "sub", "aud"]},
            leeway=10,
        )
        if str(claims["iss"]).rstrip("/") not in allowed_issuers:
            raise InvalidTokenError("OIDC issuer is not allowed")
        return claims
    except ExpiredSignatureError as exc:
        raise Problem(401, "TOKEN_EXPIRED", "The access token has expired.") from exc
    except InvalidTokenError as exc:
        raise Problem(401, "AUTHENTICATION_REQUIRED", "The access token is invalid.") from exc
    except Problem:
        raise
    except Exception as exc:
        raise Problem(
            503, "AUTH_PROVIDER_UNAVAILABLE", "The identity provider is unavailable."
        ) from exc


def _principal_from_claims(claims: dict[str, Any]) -> Principal:
    def values(name: str) -> tuple[str, ...]:
        raw = boa_scope.get(name, [])
        if isinstance(raw, str):
            return (raw,)
        if isinstance(raw, list):
            return tuple(str(item) for item in raw)
        return ()

    realm_roles = claims.get("realm_access", {}).get("roles", [])
    resource_access = claims.get("resource_access", {})
    client_roles: list[str] = []
    audience = os.getenv("OAUTH_AUDIENCE") or os.getenv("OIDC_AUDIENCE")
    audience_access = resource_access.get(audience, {}) if audience else {}
    if isinstance(audience_access, dict):
        client_roles.extend(audience_access.get("roles", []))
    scopes = str(claims.get("scope", "")).split()
    boa_scope = claims.get("boa", {}) if isinstance(claims.get("boa"), dict) else {}
    return Principal(
        subject=str(claims.get("sub")),
        username=claims.get("preferred_username"),
        email=claims.get("email") if claims.get("email_verified") is True else None,
        email_verified=claims.get("email_verified") is True,
        roles={str(role).upper() for role in [*realm_roles, *client_roles]},
        scopes=set(scopes),
        client_id=claims.get("azp") or claims.get("client_id"),
        branch_ids=values("branchIds"),
        customer_scopes=values("customerScopes"),
        relationship_manager_ids=values("relationshipManagerIds"),
    )


DEV_PRINCIPAL_HEADER = "X-Dev-Principal"


def _dev_principal(raw: str | None) -> Principal | None:
    """Persona de développement (uniquement lorsque BOA_AUTH_DISABLED=true).

    Le header X-Dev-Principal transporte un JSON {subject, username, roles, branchIds,
    relationshipManagerIds} afin de rejouer localement un périmètre CC ou agence sans Keycloak.
    Il est ignoré dès que l'authentification OIDC est active.
    """
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Problem(400, "VALIDATION_ERROR", "X-Dev-Principal must be valid JSON.") from exc
    if not isinstance(payload, dict) or not payload.get("subject"):
        raise Problem(400, "VALIDATION_ERROR", "X-Dev-Principal requires a subject.")

    def values(name: str) -> tuple[str, ...]:
        raw_value = payload.get(name, [])
        if isinstance(raw_value, str):
            return (raw_value,)
        return tuple(str(item) for item in raw_value or [])

    return Principal(
        subject=str(payload["subject"]),
        username=str(payload.get("username") or payload["subject"]),
        email=str(payload["email"]) if payload.get("email") else None,
        email_verified=bool(payload.get("email")),
        roles={str(role).upper() for role in payload.get("roles", [])},
        scopes={"*"},
        client_id="local-dev-persona",
        branch_ids=values("branchIds"),
        customer_scopes=values("customerScopes"),
        relationship_manager_ids=values("relationshipManagerIds"),
    )


async def current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    if auth_disabled():
        persona = _dev_principal(request.headers.get(DEV_PRINCIPAL_HEADER))
        if persona is not None:
            return persona
        return Principal(
            subject="local-test-user",
            username="local-test-user",
            roles={
                "ADMIN",
                "DATA_ANALYST",
                "ML_STEWARD",
                "BRANCH_MANAGER",
                "RELATIONSHIP_MANAGER",
                "SERVICE",
            },
            scopes={"*"},
            client_id="local-tests",
            branch_ids=("ALL",),
            customer_scopes=("global",),
            relationship_manager_ids=("ALL",),
        )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise Problem(401, "AUTHENTICATION_REQUIRED", "A bearer access token is required.")
    return _principal_from_claims(_decode_token(credentials.credentials))


def require_roles(*roles: str) -> Callable[..., Awaitable[Principal]]:
    allowed = {role.upper() for role in roles}

    async def dependency(
        principal: Principal = Depends(current_principal),
    ) -> Principal:
        if principal.roles.isdisjoint(allowed):
            raise Problem(403, "FORBIDDEN", "The authenticated principal lacks the required role.")
        return principal

    return dependency


def correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", "unknown")


def problem_payload(request: Request, problem: Problem) -> dict[str, Any]:
    return {
        "type": f"https://boa.example/problems/{problem.code.lower().replace('_', '-')}",
        "title": problem.title,
        "status": problem.status_code,
        "code": problem.code,
        "message": problem.message,
        "correlationId": correlation_id(request),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": problem.details,
    }


def encode_cursor(offset: int) -> str:
    raw = json.dumps({"offset": offset}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(value: str | None) -> int:
    if not value:
        return 0
    try:
        padded = value + "=" * (-len(value) % 4)
        result = json.loads(base64.urlsafe_b64decode(padded.encode()))
        offset = int(result["offset"])
        if offset < 0:
            raise ValueError
        return offset
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise Problem(400, "INVALID_CURSOR", "The pagination cursor is invalid.") from exc


def page_response(
    request: Request,
    data: list[Any],
    *,
    page_size: int,
    offset: int,
    total_count: int | None,
) -> dict[str, Any]:
    has_more = len(data) > page_size
    visible = data[:page_size]
    next_cursor = encode_cursor(offset + page_size) if has_more else None
    self_link = str(request.url.path)
    next_link = f"{self_link}?pageSize={page_size}&cursor={next_cursor}" if next_cursor else None
    return {
        "data": visible,
        "meta": {
            "pageSize": page_size,
            "nextCursor": next_cursor,
            "hasMore": has_more,
            "totalCount": total_count,
        },
        "links": {"self": self_link, "next": next_link},
        "correlationId": correlation_id(request),
    }


def reject_unknown_filters(request: Request, allowed: Iterable[str]) -> None:
    permitted = set(allowed)
    unknown = sorted(set(request.query_params.keys()) - permitted)
    if unknown:
        raise Problem(
            400,
            "UNKNOWN_FILTER",
            "One or more query filters are not supported.",
            details=[
                {
                    "field": item,
                    "code": "UNKNOWN_FILTER",
                    "message": f"Unsupported filter: {item}",
                }
                for item in unknown
            ],
        )


def database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        raise Problem(503, "DATABASE_CONFIGURATION_ERROR", "DATABASE_URL is not configured.")
    if (
        not value.startswith(("postgresql+psycopg://", "postgresql://"))
        and os.getenv("BOA_ALLOW_NON_POSTGRES_TEST_DB", "false").lower() != "true"
    ):
        raise Problem(503, "DATABASE_CONFIGURATION_ERROR", "PostgreSQL is required.")
    return value


@lru_cache(maxsize=16)
def engine_for(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, future=True)


def session_factory_for_app(app: FastAPI) -> sessionmaker[Session]:
    override = getattr(app.state, "session_factory", None)
    if override is not None:
        return override
    return sessionmaker(bind=engine_for(database_url()), expire_on_commit=False)


def get_session(request: Request):
    factory = session_factory_for_app(request.app)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def install_openapi_security(app: FastAPI) -> None:
    original = app.openapi

    def customized() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = original()
        components = schema.setdefault("components", {})
        schemes = components.setdefault("securitySchemes", {})
        try:
            issuer = oidc_issuer()
        except Problem:
            issuer = "https://identity.invalid/realms/configure-me"
        schemes["oidc"] = {
            "type": "openIdConnect",
            "openIdConnectUrl": f"{issuer}/.well-known/openid-configuration",
        }
        schema["x-boa-correlation-header"] = "X-Correlation-ID"
        app.openapi_schema = schema
        return schema

    app.openapi = customized  # type: ignore[method-assign]


def create_service_app(service_name: str, description: str, *, database: bool = True) -> FastAPI:
    auth_disabled()
    _configure_platform_logging()
    app = FastAPI(
        title=f"BOA {service_name}",
        version=__version__,
        description=description,
        docs_url="/swagger",
        openapi_url="/openapi.json",
    )
    app.state.service_name = service_name
    app.state.database_required = database
    app.state.request_count = 0
    app.state.error_count = 0

    @app.middleware("http")
    async def platform_middleware(request: Request, call_next):
        value = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        if len(value) > 128:
            value = str(uuid.uuid4())
        request.state.correlation_id = value
        started = time.perf_counter()
        app.state.request_count += 1
        try:
            response = await call_next(request)
        except Exception:
            app.state.error_count += 1
            raise
        if response.status_code >= 500:
            app.state.error_count += 1
        response.headers["X-Correlation-ID"] = value
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
        _logger.info(
            json.dumps(
                {
                    "service": service_name,
                    "method": request.method,
                    "path": request.url.path,
                    "statusCode": response.status_code,
                    "durationMs": round(duration_ms, 2),
                    "correlationId": value,
                },
                separators=(",", ":"),
            )
        )
        return response

    @app.exception_handler(Problem)
    async def handle_problem(request: Request, exc: Problem) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=problem_payload(request, exc),
            headers={"X-Correlation-ID": correlation_id(request)},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "field": ".".join(map(str, item["loc"])),
                "code": item["type"],
                "message": item["msg"],
            }
            for item in exc.errors()
        ]
        problem = Problem(
            422, "VALIDATION_ERROR", "One or more fields are invalid.", details=details
        )
        return JSONResponse(
            status_code=422,
            content=problem_payload(request, problem),
            headers={"X-Correlation-ID": correlation_id(request)},
        )

    @app.exception_handler(HTTPException)
    async def handle_http(request: Request, exc: HTTPException) -> JSONResponse:
        code = "RESOURCE_NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        problem = Problem(exc.status_code, code, str(exc.detail))
        return JSONResponse(
            status_code=exc.status_code,
            content=problem_payload(request, problem),
            headers={"X-Correlation-ID": correlation_id(request)},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, _exc: Exception) -> JSONResponse:
        problem = Problem(500, "INTERNAL_ERROR", "An unexpected error occurred.")
        return JSONResponse(
            status_code=500,
            content=problem_payload(request, problem),
            headers={"X-Correlation-ID": correlation_id(request)},
        )

    @app.get(
        "/health",
        tags=["Operations"],
        operation_id=f"{service_name.replace('-', '_')}_health",
    )
    def health() -> dict[str, str]:
        return {"status": "healthy", "service": service_name, "version": __version__}

    @app.get(
        "/ready",
        tags=["Operations"],
        operation_id=f"{service_name.replace('-', '_')}_ready",
    )
    def ready() -> dict[str, str]:
        engine = None
        if database:
            try:
                factory = getattr(app.state, "session_factory", None)
                engine = factory.kw["bind"] if factory is not None else engine_for(database_url())
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
            except Problem:
                raise
            except Exception as exc:
                raise Problem(
                    503, "DATABASE_UNAVAILABLE", "The service database is unavailable."
                ) from exc
        readiness_check = getattr(app.state, "readiness_check", None)
        if readiness_check is not None:
            readiness_check(engine)
        return {"status": "ready", "service": service_name}

    @app.get(
        "/metrics",
        response_class=PlainTextResponse,
        tags=["Operations"],
        operation_id=f"{service_name.replace('-', '_')}_metrics",
    )
    def metrics() -> str:
        return (
            f'boa_service_info{{service="{service_name}",version="{__version__}"}} 1\n'
            f'boa_http_requests_total{{service="{service_name}"}} {app.state.request_count}\n'
            f'boa_http_errors_total{{service="{service_name}"}} {app.state.error_count}\n'
        )

    install_openapi_security(app)
    return app


def not_found(resource: str) -> Problem:
    return Problem(404, "RESOURCE_NOT_FOUND", f"{resource} was not found.")


READ_ROLES = (
    "RELATIONSHIP_MANAGER",
    "BRANCH_MANAGER",
    "DATA_ANALYST",
    "BUSINESS_ANALYST",
    "ML_STEWARD",
    "RULE_APPROVER",
    "ADMIN",
    "SERVICE",
)
COMMERCIAL_ROLES = ("RELATIONSHIP_MANAGER", "BRANCH_MANAGER", "ADMIN", "SERVICE")
ADMIN_ROLES = ("ADMIN", "SERVICE")
ANALYTICS_ROLES = ("DATA_ANALYST", "ADMIN", "SERVICE")


__all__ = [
    "ADMIN_ROLES",
    "ANALYTICS_ROLES",
    "COMMERCIAL_ROLES",
    "READ_ROLES",
    "Principal",
    "Problem",
    "auth_disabled",
    "correlation_id",
    "create_service_app",
    "current_principal",
    "decode_cursor",
    "get_session",
    "not_found",
    "page_response",
    "reject_unknown_filters",
    "require_roles",
]
