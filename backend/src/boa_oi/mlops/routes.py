from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from boa_oi.ml.governance import evaluation_blockers
from boa_oi.mlops.service import (
    ConflictError,
    MLOpsGovernanceService,
    NotFoundError,
    SqlAlchemyModelRepository,
    ValidationError,
)
from boa_oi.models.entities import MLDatasetManifest, MLEvaluationSnapshot, ModelRegistry
from boa_oi.platform import (
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
AUTHOR_ROLES = ("DATA_ANALYST", "ML_STEWARD", "ADMIN")
EVALUATION_ROLES = ("DATA_ANALYST", "ADMIN", "SERVICE")
APPROVER_ROLES = ("RULE_APPROVER", "ADMIN")
RELEASE_ROLES = ("ADMIN",)
GOVERNANCE_READ_ROLES = ("DATA_ANALYST", "ML_STEWARD", "RULE_APPROVER", "ADMIN", "SERVICE")


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
    deploymentMode: Literal["POC_SHADOW"] = "POC_SHADOW"
    datasetManifestHash: str = Field(min_length=64, max_length=64)
    artifactChecksum: str = Field(min_length=64, max_length=64)
    targetOutcome: str = Field(min_length=1, max_length=80)
    horizonDays: int = Field(gt=0, le=3650)
    reason: str = Field(min_length=1)
    artifact: ArtifactPayload
    registryStatus: Literal["CHALLENGER", "DEMO_ONLY"] | None = None
    promotable: bool | None = None
    promotionBlockers: list[str] = Field(default_factory=list)


class TransitionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1)


class RollbackPayload(TransitionPayload):
    modelVersion: str | None = None


class MetricsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluationRef: str = Field(min_length=3, max_length=100)
    modelVersion: str = Field(min_length=1, max_length=40)
    datasetManifestHash: str = Field(min_length=64, max_length=64)
    sourceKind: Literal["LOCAL_COMMERCIAL_OUTCOME", "BOA_HISTORICAL_OBSERVED", "SYNTHETIC"]
    evaluationPeriodFrom: date
    evaluationPeriodTo: date
    scores: list[float] = Field(default_factory=list)
    labels: list[int | bool] = Field(default_factory=list)
    k: int | float = 10
    treatment: list[int | bool] | None = None
    acceptanceCriteria: dict[str, Any] = Field(default_factory=dict)
    calibrationMethod: Literal["NONE", "PLATT", "ISOTONIC"] = "NONE"
    calibrationEvidenceRef: str | None = Field(default=None, max_length=200)


class LabelEvaluationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    labels: list[dict[str, Any]] = Field(default_factory=list)
    evaluatedAsOf: date
    sourceKind: Literal["LOCAL_COMMERCIAL_OUTCOME", "BOA_HISTORICAL_OBSERVED", "SYNTHETIC"]


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
        demo_only = payload.lineage.get("sourceKind") == "DEMO_SYNTHETIC_LABELS"
        expected_status = "DEMO_ONLY" if demo_only else "CHALLENGER"
        if payload.registryStatus is not None and payload.registryStatus != expected_status:
            raise ValidationError("registryStatus must match the governed dataset source")
        if payload.promotable is not None and payload.promotable == demo_only:
            raise ValidationError("promotable must match the governed dataset source")
        required_blocker = "DEMO_SYNTHETIC_LABELS_NON_PROMOTABLE"
        if demo_only and required_blocker not in payload.promotionBlockers:
            raise ValidationError("DEMO_ONLY payload must declare its promotion blocker")
        actor = _actor(principal)
        session.add(
            ModelRegistry(
                id=deterministic_uuid("model", payload.modelVersion),
                model_version=payload.modelVersion,
                score_type="SALES_PROPENSITY",
                algorithm=payload.artifact.algorithm,
                status="DEMO_ONLY" if demo_only else "CHALLENGER",
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
                deployment_mode="POC_SHADOW",
                target_outcome=payload.targetOutcome,
                horizon_days=payload.horizonDays,
                score_interpretation="RANKING_ONLY",
                calibration_status=str(payload.metrics.get("calibrationStatus", "NOT_VALIDATED")),
                dataset_manifest_hash=payload.datasetManifestHash,
                artifact_checksum=payload.artifactChecksum,
                contract_version="1.0",
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
        if demo_only:
            run.status = "DEMO_ONLY"
            run.activation_gate_status = "BLOCKED"
            run.activation_gate_blockers = list(
                dict.fromkeys(
                    ["DEMO_SYNTHETIC_LABELS_NON_PROMOTABLE", *run.activation_gate_blockers]
                )
            )
            run.validation = {
                **run.validation,
                "demoOnly": True,
                "activationGateStatus": "BLOCKED",
                "activationBlockers": run.activation_gate_blockers,
            }
            service.repository.save(run)
    except (NotFoundError, ConflictError, ValidationError) as exc:
        raise _error(exc) from exc
    return _response(run)


@router.get("/runs", dependencies=[Depends(require_roles(*GOVERNANCE_READ_ROLES))])
def list_runs(
    service: MLOpsGovernanceService = Depends(get_governance_service),
) -> dict[str, Any]:
    runs = service.list_runs()
    return {"runs": [run.as_dict() for run in runs], "count": len(runs), "mode": "POC_SHADOW"}


@router.get(
    "/runs/{model_id}/{model_version}",
    dependencies=[Depends(require_roles(*GOVERNANCE_READ_ROLES))],
)
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
    principal: Principal = Depends(require_roles(*APPROVER_ROLES)),
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


@router.post("/evaluation/metrics")
def evaluate_model_metrics(
    payload: MetricsPayload,
    request: Request,
    session: Session = Depends(get_session),
    service: MLOpsGovernanceService = Depends(get_governance_service),
    principal: Principal = Depends(require_roles(*EVALUATION_ROLES)),
) -> dict[str, Any]:
    if payload.evaluationPeriodTo < payload.evaluationPeriodFrom:
        raise Problem(422, "INVALID_EVALUATION_PERIOD", "Evaluation period is not chronological.")
    if payload.calibrationMethod != "NONE" and not payload.calibrationEvidenceRef:
        raise Problem(
            422,
            "CALIBRATION_EVIDENCE_REQUIRED",
            "A calibration evidence reference is required for PLATT or ISOTONIC.",
        )
    report = service.evaluate(
        payload.scores, payload.labels, k=payload.k, treatment=payload.treatment
    )
    metrics = dict(report["metrics"])
    calibration = {
        "status": "NOT_VALIDATED",
        "method": "NONE",
        "requestedMethod": payload.calibrationMethod,
        "evidenceRef": payload.calibrationEvidenceRef,
        "brierScore": metrics.get("brierScore", "N/A"),
        "expectedCalibrationError": metrics.get("expectedCalibrationError", "N/A"),
    }
    manifest = session.scalar(
        select(MLDatasetManifest).where(
            MLDatasetManifest.manifest_hash == payload.datasetManifestHash
        )
    )
    blockers = evaluation_blockers(
        source_kind=payload.sourceKind,
        metrics=metrics,
        calibration=calibration,
        acceptance_criteria=payload.acceptanceCriteria,
    )
    if manifest is None:
        blockers.append("DATASET_MANIFEST_NOT_FOUND")
    blockers.append("DECLARATIVE_EVALUATION_INPUT_NOT_LINKED_TO_SNAPSHOTS")
    blockers = list(dict.fromkeys(blockers))
    existing = session.scalar(
        select(MLEvaluationSnapshot).where(
            MLEvaluationSnapshot.evaluation_ref == payload.evaluationRef
        )
    )
    if existing is not None:
        raise Problem(409, "EVALUATION_EXISTS", "The evaluation reference already exists.")
    labels = [bool(item) for item in payload.labels]
    record = MLEvaluationSnapshot(
        id=deterministic_uuid("ml-evaluation", payload.evaluationRef),
        evaluation_ref=payload.evaluationRef,
        model_version=payload.modelVersion,
        dataset_manifest_hash=payload.datasetManifestHash,
        source_kind=payload.sourceKind,
        evaluation_period_from=payload.evaluationPeriodFrom,
        evaluation_period_to=payload.evaluationPeriodTo,
        sample_count=len(labels),
        positive_count=sum(labels),
        negative_count=len(labels) - sum(labels),
        metrics_json=metrics,
        calibration_json=calibration,
        acceptance_criteria_json=payload.acceptanceCriteria,
        status="BLOCKED" if blockers else "NOT_VALIDATED",
        blockers_json=blockers,
        created_by=_actor(principal),
    )
    session.add(record)
    session.flush()
    return {
        "evaluationRef": record.evaluation_ref,
        "modelVersion": record.model_version,
        "datasetManifestHash": record.dataset_manifest_hash,
        "sourceKind": record.source_kind,
        "metrics": metrics,
        "calibration": calibration,
        "acceptanceCriteria": record.acceptance_criteria_json,
        "status": record.status,
        "activationBlockers": blockers,
        "deploymentMode": "POC_SHADOW",
        "correlationId": _trace(request),
        "productionPerformanceClaim": False,
    }


@router.get(
    "/evaluation/snapshots",
    dependencies=[Depends(require_roles(*GOVERNANCE_READ_ROLES))],
)
def list_evaluation_snapshots(session: Session = Depends(get_session)) -> dict[str, Any]:
    records = list(
        session.scalars(
            select(MLEvaluationSnapshot).order_by(MLEvaluationSnapshot.created_at.desc())
        )
    )
    return {
        "data": [
            {
                "evaluationRef": item.evaluation_ref,
                "modelVersion": item.model_version,
                "datasetManifestHash": item.dataset_manifest_hash,
                "sourceKind": item.source_kind,
                "evaluationPeriodFrom": item.evaluation_period_from.isoformat(),
                "evaluationPeriodTo": item.evaluation_period_to.isoformat(),
                "sampleCount": item.sample_count,
                "metrics": item.metrics_json,
                "calibration": item.calibration_json,
                "acceptanceCriteria": item.acceptance_criteria_json,
                "status": item.status,
                "activationBlockers": item.blockers_json,
            }
            for item in records
        ],
        "meta": {"totalCount": len(records), "deploymentMode": "POC_SHADOW"},
    }


@router.post("/evaluation/labels")
def evaluate_labels(
    payload: LabelEvaluationPayload,
    request: Request,
    service: MLOpsGovernanceService = Depends(get_governance_service),
    principal: Principal = Depends(require_roles(*EVALUATION_ROLES)),
) -> dict[str, Any]:
    result = service.evaluate_labels(payload.labels, evaluated_as_of=payload.evaluatedAsOf)
    candidate_ready = bool(result.get("trainingReady"))
    blockers = []
    if payload.sourceKind != "BOA_HISTORICAL_OBSERVED":
        blockers.append("BOA_HISTORICAL_LABELS_UNAVAILABLE")
    if not candidate_ready:
        blockers.append("LABEL_MATURITY_INCOMPLETE")
    response = {
        **result,
        "sourceKind": payload.sourceKind,
        "candidateMaturityReady": candidate_ready,
        "trainingReady": not blockers,
        "activationBlockers": blockers,
        "deploymentMode": "POC_SHADOW",
    }
    service.record_label_evaluation(
        actor=_actor(principal),
        trace_id=_trace(request),
        source_kind=payload.sourceKind,
        result=response,
    )
    return {**response, "correlationId": _trace(request)}


@router.get("/audits", dependencies=[Depends(require_roles(*GOVERNANCE_READ_ROLES))])
def list_audits(
    service: MLOpsGovernanceService = Depends(get_governance_service),
) -> dict[str, Any]:
    return {"audits": [entry.as_dict() for entry in service.audits()]}


@router.get("/champion", dependencies=[Depends(require_roles(*GOVERNANCE_READ_ROLES))])
def get_champion(
    service: MLOpsGovernanceService = Depends(get_governance_service),
) -> dict[str, Any]:
    champion = service.champion()
    return {"champion": champion.as_dict() if champion else None, "mode": "POC_SHADOW"}


__all__ = ["PREFIX", "get_governance_service", "governance_router", "router"]
