from __future__ import annotations

import math
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from boa_oi.ml_training.service import (
    ALGORITHM,
    MIN_EXAMPLES,
    MIN_POSITIVES,
    create_training_job,
    request_cancellation,
    run_training_job,
    serialize_job,
)
from boa_oi.models.entities import (
    MLDatasetManifest,
    MLEvaluationSnapshot,
    MLGovernanceAuditLog,
    MLTrainingExample,
    MLTrainingJob,
    ModelRegistry,
    OutcomeLabelSnapshot,
)
from boa_oi.platform import (
    Principal,
    Problem,
    correlation_id,
    get_session,
    require_roles,
    session_factory_for_app,
)

PREFIX = "/internal/v1/ml/governance"
router = APIRouter(prefix=PREFIX, tags=["ML Studio"])
READ_ROLES = ("ML_STEWARD", "RULE_APPROVER", "ADMIN", "SERVICE")
AUTHOR_ROLES = ("ML_STEWARD", "ADMIN")


class TrainingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifestId: UUID
    algorithm: str = ALGORITHM
    seed: int = Field(default=20260921, ge=0, le=2_147_483_647)
    justification: str = Field(min_length=8, max_length=2_000)


def _actor(principal: Principal) -> str:
    return principal.username or principal.subject


@router.post("/trainings", status_code=status.HTTP_202_ACCEPTED)
async def start_training(
    payload: TrainingPayload,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*AUTHOR_ROLES)),
) -> dict[str, Any]:
    job, created = create_training_job(
        session,
        manifest_id=payload.manifestId,
        algorithm=payload.algorithm,
        seed=payload.seed,
        justification=payload.justification,
        author=_actor(principal),
        idempotency_key=idempotency_key,
        correlation_id=correlation_id(request),
    )
    if created:
        session.commit()
        factory = session_factory_for_app(request.app)
        background_tasks.add_task(run_training_job, factory, job.id)
    return serialize_job(job)


@router.get("/trainings", dependencies=[Depends(require_roles(*READ_ROLES))])
def training_history(
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 25,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    total = session.scalar(select(func.count()).select_from(MLTrainingJob)) or 0
    rows = list(
        session.scalars(
            select(MLTrainingJob).order_by(MLTrainingJob.created_at.desc()).limit(page_size)
        )
    )
    return {
        "data": [serialize_job(row) for row in rows],
        "meta": {"pageSize": page_size, "totalCount": total, "hasMore": total > page_size},
    }


@router.get("/trainings/{job_id}", dependencies=[Depends(require_roles(*READ_ROLES))])
def get_training(job_id: UUID, session: Session = Depends(get_session)) -> dict[str, Any]:
    row = session.get(MLTrainingJob, job_id)
    if row is None:
        raise Problem(404, "TRAINING_NOT_FOUND", "L'entraînement demandé est introuvable.")
    return serialize_job(row)


@router.post("/trainings/{job_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
def cancel_training(
    job_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles(*AUTHOR_ROLES)),
) -> dict[str, Any]:
    return serialize_job(
        request_cancellation(session, job_id, _actor(principal), correlation_id(request))
    )


def _probability(model: ModelRegistry, example: MLTrainingExample) -> float:
    linear = float(model.intercept) + sum(
        float(model.coefficients_json.get(feature, 0))
        * float(example.feature_values_json.get(feature, 0))
        for feature in model.feature_order_json
    )
    return 1 / (1 + math.exp(-max(-35, min(35, linear))))


def _priority(score: float) -> str:
    if score >= 0.7:
        return "P1"
    if score >= 0.4:
        return "P2"
    return "P3"


@router.get("/model-comparisons", dependencies=[Depends(require_roles(*READ_ROLES))])
def compare_models(
    left: str,
    right: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    models = list(
        session.scalars(select(ModelRegistry).where(ModelRegistry.model_version.in_((left, right))))
    )
    by_version = {item.model_version: item for item in models}
    if left not in by_version or right not in by_version:
        raise Problem(404, "MODEL_NOT_FOUND", "Une version de modèle demandée est introuvable.")
    first, second = by_version[left], by_version[right]
    if (
        first.feature_set_version != second.feature_set_version
        or first.feature_order_json != second.feature_order_json
    ):
        return {
            "comparable": False,
            "reason": "FEATURE_SET_MISMATCH",
            "message": "Comparaison impossible : les modèles n'utilisent pas le même feature set.",
        }
    if first.training_dataset_version != second.training_dataset_version:
        return {
            "comparable": False,
            "reason": "COMMON_TEST_SET_UNAVAILABLE",
            "message": "Comparaison impossible : les modèles n'ont pas le même jeu de test.",
        }
    manifest = session.scalar(
        select(MLDatasetManifest).where(
            MLDatasetManifest.manifest_version == first.training_dataset_version
        )
    )
    if manifest is None:
        return {
            "comparable": False,
            "reason": "COMMON_TEST_SET_UNAVAILABLE",
            "message": "Comparaison impossible : le jeu de test commun n'est pas persisté.",
        }
    examples = list(
        session.scalars(
            select(MLTrainingExample).where(
                MLTrainingExample.manifest_id == manifest.id,
                MLTrainingExample.split == "TEST",
            )
        )
    )
    changes: list[dict[str, Any]] = []
    changed = 0
    for example in examples:
        left_score = _probability(first, example)
        right_score = _probability(second, example)
        left_priority, right_priority = _priority(left_score), _priority(right_score)
        changed += int(left_priority != right_priority)
        contributions = sorted(
            (
                {
                    "feature": feature,
                    "left": round(
                        float(first.coefficients_json.get(feature, 0))
                        * float(example.feature_values_json.get(feature, 0)),
                        6,
                    ),
                    "right": round(
                        float(second.coefficients_json.get(feature, 0))
                        * float(example.feature_values_json.get(feature, 0)),
                        6,
                    ),
                }
                for feature in first.feature_order_json
            ),
            key=lambda item: abs(float(item["right"]) - float(item["left"])),
            reverse=True,
        )[:3]
        changes.append(
            {
                "entityRef": example.entity_ref,
                "leftScore": round(left_score, 6),
                "rightScore": round(right_score, 6),
                "leftPriority": left_priority,
                "rightPriority": right_priority,
                "absoluteDifference": round(abs(right_score - left_score), 6),
                "contributions": contributions,
            }
        )
    changes.sort(key=lambda item: item["absoluteDifference"], reverse=True)
    return {
        "comparable": True,
        "testDataset": manifest.manifest_version,
        "testCount": len(examples),
        "rankingChangeRate": round(changed / len(examples), 6) if examples else 0,
        "models": [
            {
                "modelVersion": model.model_version,
                "status": model.status,
                "featureSetVersion": model.feature_set_version,
                "metrics": model.validation_metrics_json,
            }
            for model in (first, second)
        ],
        "largestChanges": changes[:10],
    }


@router.get("/studio-summary", dependencies=[Depends(require_roles(*READ_ROLES))])
def studio_summary(session: Session = Depends(get_session)) -> dict[str, Any]:
    labels_total = session.scalar(select(func.count()).select_from(OutcomeLabelSnapshot)) or 0
    mature_labels = (
        session.scalar(
            select(func.count())
            .select_from(OutcomeLabelSnapshot)
            .where(
                OutcomeLabelSnapshot.window_closed.is_(True),
                OutcomeLabelSnapshot.outcome_value.is_not(None),
            )
        )
        or 0
    )
    latest_evaluation = session.scalar(
        select(MLEvaluationSnapshot).order_by(MLEvaluationSnapshot.created_at.desc())
    )
    champion = session.scalar(
        select(ModelRegistry)
        .where(ModelRegistry.status.in_(("CHAMPION", "ACTIVE")))
        .order_by(ModelRegistry.updated_at.desc())
    )
    gate_events = list(
        session.scalars(
            select(MLGovernanceAuditLog)
            .where(MLGovernanceAuditLog.action.in_(("APPROVED", "PROMOTED")))
            .order_by(MLGovernanceAuditLog.timestamp.desc())
        )
    )
    manifests = list(
        session.scalars(select(MLDatasetManifest).order_by(MLDatasetManifest.created_at.desc()))
    )
    boa_manifest = next(
        (
            item
            for item in manifests
            if item.source_kind == "BOA_HISTORICAL_OBSERVED" and item.status == "VALIDATED"
        ),
        None,
    )
    gates = [
        {
            "gate": "G0",
            "label": "Cadre et usage commercial",
            "status": "PASSED",
            "actor": None,
            "at": None,
            "missingCondition": None,
        },
        {
            "gate": "G1",
            "label": "Données et étiquettes BOA",
            "status": "PASSED" if boa_manifest else "BLOCKED",
            "actor": boa_manifest.created_by if boa_manifest else None,
            "at": boa_manifest.created_at.isoformat() if boa_manifest else None,
            "missingCondition": None
            if boa_manifest
            else "Un manifeste historique BOA validé et point-in-time est requis.",
        },
        {
            "gate": "G2",
            "label": "Évaluation indépendante",
            "status": "PASSED"
            if latest_evaluation and latest_evaluation.status == "VALIDATED"
            else "BLOCKED",
            "actor": latest_evaluation.created_by if latest_evaluation else None,
            "at": latest_evaluation.created_at.isoformat() if latest_evaluation else None,
            "missingCondition": None
            if latest_evaluation and latest_evaluation.status == "VALIDATED"
            else "Brier, ECE et critères BOA doivent être validés sur le même jeu de test.",
        },
        {
            "gate": "G3",
            "label": "Activation gouvernée",
            "status": "PASSED" if champion and gate_events else "BLOCKED",
            "actor": gate_events[0].user_id if champion and gate_events else None,
            "at": gate_events[0].timestamp.isoformat() if champion and gate_events else None,
            "missingCondition": None
            if champion and gate_events
            else (
                "La porte G3 n'est pas franchie : labels historiques BOA et évaluation "
                "indépendante validée requis."
            ),
        },
        {
            "gate": "G4",
            "label": "Surveillance et retour arrière",
            "status": "BLOCKED",
            "actor": None,
            "at": None,
            "missingCondition": (
                "Une activation G3 préalable et une période d'observation sont requises."
            ),
        },
    ]
    definitions = [
        {
            "version": "commercial-conversion-90d-v1",
            "name": "Conversion commerciale à 90 jours",
            "targetOutcome": "ANY_COMMERCIAL_OPPORTUNITY",
            "horizonDays": 90,
            "population": {"segment": "PME"},
            "status": "À VALIDER AVEC BOA",
        }
    ]
    return {
        "mode": "ML_SHADOW" if champion else "RULES_ONLY",
        "weights": {"rules": 1, "ml": 0},
        "productionPerformanceClaim": False,
        "champion": {
            "modelVersion": champion.model_version,
            "status": champion.status,
            "updatedAt": champion.updated_at.isoformat(),
        }
        if champion
        else None,
        "labels": {"available": labels_total, "mature": mature_labels},
        "latestEvaluation": {
            "brierScore": latest_evaluation.metrics_json.get("brierScore"),
            "expectedCalibrationError": latest_evaluation.metrics_json.get(
                "expectedCalibrationError"
            ),
            "status": latest_evaluation.status,
            "createdAt": latest_evaluation.created_at.isoformat(),
        }
        if latest_evaluation
        else None,
        "gates": gates,
        "targetDefinitions": definitions,
        "assumptions": {
            "minimumExamples": MIN_EXAMPLES,
            "minimumPositives": MIN_POSITIVES,
            "maximumMlWeight": 0.5,
            "status": "HYPOTHÈSE À VALIDER AVEC BOA",
        },
    }


__all__ = ["router"]
