from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Callable

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from boa_oi.mlops.service import (
    ConflictError,
    MLOpsGovernanceService,
    NotFoundError,
    SqlAlchemyModelRepository,
    ValidationError,
)
from boa_oi.models.entities import ModelRegistry
from boa_oi.platform import (
    READ_ROLES,
    Principal,
    Problem,
    correlation_id,
    get_session,
    require_roles,
)
from boa_oi.technical.ids import deterministic_uuid

PREFIX = "/internal/v1/ml/governance"
router = APIRouter(prefix=PREFIX, tags=["ML governance"])
governance_router = router
AUTHOR_ROLES = ("DATA_ANALYST", "ADMIN")
REVIEWER_ROLES = ("RULE_APPROVER", "ADMIN")
RELEASE_ROLES = ("ADMIN",)


class ArtifactPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    algorithm: str = "LOGISTIC_REGRESSION"
    featureOrder: list[str] = Field(min_length=1)
    coefficients: dict[str, float]
    intercept: float
    threshold: float = Field(gt=0, lt=1)


class GovernancePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    modelId: str = "sales-propensity"
    modelVersion: str
    featureVersion: str
    datasetVersion: str
    trainingPeriodFrom: date
    trainingPeriodTo: date
    validationPeriodFrom: date
    validationPeriodTo: date
    testPeriodFrom: date | None = None
    testPeriodTo: date | None = None
    codeVersion: str
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    lineage: dict[str, Any]
    deploymentMode: str = "POC_ASSISTIVE"
    reason: str = Field(min_length=1)
    artifact: ArtifactPayload


class TransitionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1)


class RollbackPayload(TransitionPayload):
    modelVersion: str | None = None


class MetricsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scores: list[float] = Field(default_factory=list)
    labels: list[int | bool] = Field(default_factory=list)
    k: int | float = 10
    treatment: list[int | bool] | None = None


class LabelEvaluationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    labels: list[dict[str, Any]] = Field(default_factory=list)
    evaluatedAsOf: date


def get_governance_service(session: Session = Depends(get_session)) -> MLOpsGovernanceService:
    return MLOpsGovernanceService(SqlAlchemyModelRepository(session))


def _actor(principal: Principal) -> str:
    return principal.username or principal.subject


def _trace(request: Request) -> str:
    return correlation_id(request)


def _error(exc: Exception) -> Problem:
    if isinstance(exc, NotFoundError):
        return Problem(404, "ML_GOVERNANCE_NOT_FOUND", str(exc))
    if isinstance(exc, ConflictError):
        return Problem(409, "ML_GOVERNANCE_CONFLICT", str(exc))
    return Problem(422, "ML_GOVERNANCE_VALIDATION_ERROR", str(exc))


def _response(run: Any) -> dict[str, Any]:
    return {"run": run.as_dict(), "mode": run.deployment_mode}


def _operation(call: Callable[[], Any]) -> dict[str, Any]:
    try:
        return _response(call())
    except (NotFoundError, ConflictError, ValidationError) as exc:
        raise _error(exc) from exc


@router.post("/runs", status_code=status.HTTP_201_CREATED)
def register_run(
    payload: GovernancePayload,
    request: Request,
    session: Session = Depends(get_session),
    service: MLOpsGovernanceService = Depends(get_governance_service),
    principal: Principal = Depends(require_roles(*AUTHOR_ROLES)),
) -> dict[str, Any]:
    try:
        if set(payload.artifact.featureOrder) != set(payload.artifact.coefficients):
            raise ValidationError("artifact featureOrder must match coefficient names exactly")
        if session.scalar(
            select(ModelRegistry).where(ModelRegistry.model_version == payload.modelVersion)
        ):
            raise ConflictError("model artifact version already exists")
        actor = _actor(principal)
        session.add(
            ModelRegistry(
                id=deterministic_uuid("model", payload.modelVersion),
                model_version=payload.modelVersion,
                score_type="SALES_PROPENSITY",
                algorithm=payload.artifact.algorithm,
                status="CHALLENGER",
                feature_set_version=payload.featureVersion,
                feature_order_json=payload.artifact.featureOrder,
                coefficients_json=payload.artifact.coefficients,
                intercept=Decimal(str(payload.artifact.intercept)),
                threshold=Decimal(str(payload.artifact.threshold)),
                validation_metrics_json=payload.metrics,
                training_dataset_version=payload.datasetVersion,
                training_code_version=payload.codeVersion,
                training_period_from=payload.trainingPeriodFrom,
                training_period_to=payload.trainingPeriodTo,
                validation_period_from=payload.validationPeriodFrom,
                validation_period_to=payload.validationPeriodTo,
                hyperparameters_json=payload.hyperparameters,
                deployment_mode=payload.deploymentMode,
                created_by=actor,
            )
        )
        session.flush()
        run = service.register_run(
            payload.model_dump(exclude_none=True, exclude={"artifact", "reason"}),
            actor=actor,
            trace_id=_trace(request),
            reason=payload.reason,
        )
    except (NotFoundError, ConflictError, ValidationError) as exc:
        raise _error(exc) from exc
    return _response(run)


@router.get("/runs", dependencies=[Depends(require_roles(*READ_ROLES))])
def list_runs(
    service: MLOpsGovernanceService = Depends(get_governance_service),
) -> dict[str, Any]:
    runs = service.list_runs()
    return {"runs": [run.as_dict() for run in runs], "count": len(runs), "mode": "POC_ASSISTIVE"}


@router.get("/runs/{model_id}/{model_version}", dependencies=[Depends(require_roles(*READ_ROLES))])
def get_run(
    model_id: str,
    model_version: str,
    service: MLOpsGovernanceService = Depends(get_governance_service),
) -> dict[str, Any]:
    return _operation(lambda: service.get(model_id, model_version))


@router.post("/runs/{model_id}/{model_version}/lineage/validate")
def validate_lineage(
    model_id: str,
    model_version: str,
    payload: TransitionPayload,
    request: Request,
    service: MLOpsGovernanceService = Depends(get_governance_service),
    principal: Principal = Depends(require_roles(*AUTHOR_ROLES)),
) -> dict[str, Any]:
    return _operation(
        lambda: service.validate_lineage(
            model_id,
            model_version,
            actor=_actor(principal),
            trace_id=_trace(request),
            reason=payload.reason,
        )
    )


@router.post("/runs/{model_id}/{model_version}/submit")
def submit_run(
    model_id: str,
    model_version: str,
    payload: TransitionPayload,
    request: Request,
    service: MLOpsGovernanceService = Depends(get_governance_service),
    principal: Principal = Depends(require_roles(*AUTHOR_ROLES)),
) -> dict[str, Any]:
    return _operation(
        lambda: service.submit(
            model_id,
            model_version,
            actor=_actor(principal),
            trace_id=_trace(request),
            reason=payload.reason,
        )
    )


@router.post("/runs/{model_id}/{model_version}/approve")
def approve_run(
    model_id: str,
    model_version: str,
    payload: TransitionPayload,
    request: Request,
    service: MLOpsGovernanceService = Depends(get_governance_service),
    principal: Principal = Depends(require_roles(*REVIEWER_ROLES)),
) -> dict[str, Any]:
    return _operation(
        lambda: service.approve(
            model_id,
            model_version,
            actor=_actor(principal),
            trace_id=_trace(request),
            reason=payload.reason,
        )
    )


@router.post("/runs/{model_id}/{model_version}/promote")
def promote_run(
    model_id: str,
    model_version: str,
    payload: TransitionPayload,
    request: Request,
    service: MLOpsGovernanceService = Depends(get_governance_service),
    principal: Principal = Depends(require_roles(*RELEASE_ROLES)),
) -> dict[str, Any]:
    return _operation(
        lambda: service.promote(
            model_id,
            model_version,
            actor=_actor(principal),
            trace_id=_trace(request),
            reason=payload.reason,
        )
    )


@router.post("/runs/{model_id}/{model_version}/retire")
def retire_run(
    model_id: str,
    model_version: str,
    payload: TransitionPayload,
    request: Request,
    service: MLOpsGovernanceService = Depends(get_governance_service),
    principal: Principal = Depends(require_roles(*RELEASE_ROLES)),
) -> dict[str, Any]:
    return _operation(
        lambda: service.retire(
            model_id,
            model_version,
            actor=_actor(principal),
            trace_id=_trace(request),
            reason=payload.reason,
        )
    )


@router.post("/rollback")
def rollback(
    payload: RollbackPayload,
    request: Request,
    service: MLOpsGovernanceService = Depends(get_governance_service),
    principal: Principal = Depends(require_roles(*RELEASE_ROLES)),
) -> dict[str, Any]:
    return _operation(
        lambda: service.rollback(
            actor=_actor(principal),
            trace_id=_trace(request),
            reason=payload.reason,
            to_model_version=payload.modelVersion,
        )
    )


@router.post("/evaluation/metrics", dependencies=[Depends(require_roles(*READ_ROLES))])
def evaluate_model_metrics(
    payload: MetricsPayload,
    service: MLOpsGovernanceService = Depends(get_governance_service),
) -> dict[str, Any]:
    return service.evaluate(
        payload.scores, payload.labels, k=payload.k, treatment=payload.treatment
    )


@router.post("/evaluation/labels", dependencies=[Depends(require_roles(*READ_ROLES))])
def evaluate_labels(
    payload: LabelEvaluationPayload,
    service: MLOpsGovernanceService = Depends(get_governance_service),
) -> dict[str, Any]:
    return service.evaluate_labels(payload.labels, evaluated_as_of=payload.evaluatedAsOf)


@router.get("/audits", dependencies=[Depends(require_roles(*READ_ROLES))])
def list_audits(
    service: MLOpsGovernanceService = Depends(get_governance_service),
) -> dict[str, Any]:
    return {"audits": [entry.as_dict() for entry in service.audits()]}


@router.get("/champion", dependencies=[Depends(require_roles(*READ_ROLES))])
def get_champion(
    service: MLOpsGovernanceService = Depends(get_governance_service),
) -> dict[str, Any]:
    champion = service.champion()
    return {"champion": champion.as_dict() if champion else None, "mode": "POC_ASSISTIVE"}


__all__ = ["PREFIX", "get_governance_service", "governance_router", "router"]
