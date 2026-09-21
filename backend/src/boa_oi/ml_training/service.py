from __future__ import annotations

import asyncio
import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Callable, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from boa_oi.audit.service import ensure_relational_language
from boa_oi.models.entities import (
    MLDatasetManifest,
    MLGovernanceAuditLog,
    MLTrainingExample,
    MLTrainingJob,
)
from boa_oi.platform import Problem
from boa_oi.technical.ids import deterministic_uuid

ALGORITHM = "LOGISTIC_REGRESSION"
MIN_EXAMPLES = 200
MIN_POSITIVES = 30
TERMINAL_STATUSES = frozenset({"SUCCEEDED", "FAILED", "INSUFFICIENT_DATA", "CANCELLED"})
TRAINABLE_SOURCES = frozenset({"BOA_HISTORICAL_OBSERVED", "DEMO_SYNTHETIC_LABELS"})
STEPS: tuple[tuple[str, int, int], ...] = (
    ("Chargement du manifeste", 0, 10),
    ("Contrôle anti-fuite", 10, 25),
    ("Extraction des vecteurs et étiquettes", 25, 45),
    ("Entraînement", 45, 70),
    ("Évaluation sur la période de test", 70, 85),
    ("Calibration", 85, 95),
    ("Enregistrement de l'artefact et du rapport", 95, 100),
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def request_hash(manifest_id: UUID, algorithm: str, seed: int, justification: str) -> str:
    body = {
        "algorithm": algorithm,
        "justification": justification.strip(),
        "manifestId": str(manifest_id),
        "seed": seed,
    }
    return hashlib.sha256(
        json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def serialize_job(row: MLTrainingJob) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "manifestId": str(row.manifest_id),
        "algorithm": row.algorithm,
        "seed": row.seed,
        "justification": row.justification,
        "status": row.status,
        "currentStep": row.current_step,
        "percentage": row.percentage,
        "steps": list(row.steps_json or []),
        "result": row.result_json,
        "error": row.error_json,
        "cancellationRequested": row.cancellation_requested,
        "author": row.author,
        "correlationId": row.correlation_id,
        "startedAt": row.started_at.isoformat() if row.started_at else None,
        "completedAt": row.completed_at.isoformat() if row.completed_at else None,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
        "terminal": row.status in TERMINAL_STATUSES,
    }


def create_training_job(
    session: Session,
    *,
    manifest_id: UUID,
    algorithm: str,
    seed: int,
    justification: str,
    author: str,
    idempotency_key: str,
    correlation_id: str,
) -> tuple[MLTrainingJob, bool]:
    if algorithm != ALGORITHM:
        raise Problem(
            422, "UNSUPPORTED_ALGORITHM", "Seule la régression logistique est disponible."
        )
    justification = justification.strip()
    if len(justification) < 8:
        raise Problem(
            422, "JUSTIFICATION_REQUIRED", "Une justification de 8 caractères minimum est requise."
        )
    try:
        ensure_relational_language({"justification": justification})
    except ValueError as exc:
        raise Problem(422, "FORBIDDEN_VOCABULARY", str(exc)) from exc
    digest = request_hash(manifest_id, algorithm, seed, justification)
    existing = session.scalar(
        select(MLTrainingJob).where(MLTrainingJob.idempotency_key == idempotency_key)
    )
    if existing is not None:
        if existing.request_hash != digest:
            raise Problem(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "Cette clé d'idempotence désigne déjà une autre demande.",
            )
        return existing, False
    manifest = session.get(MLDatasetManifest, manifest_id)
    if manifest is None:
        raise Problem(404, "MANIFEST_NOT_FOUND", "Le manifeste demandé est introuvable.")
    active = session.scalar(
        select(MLTrainingJob).where(
            MLTrainingJob.manifest_id == manifest_id,
            MLTrainingJob.status.in_(("QUEUED", "RUNNING")),
        )
    )
    if active is not None:
        raise Problem(
            409,
            "TRAINING_IN_PROGRESS",
            "Un entraînement est déjà en cours pour ce manifeste.",
        )
    row = MLTrainingJob(
        id=deterministic_uuid("ml-training-job", idempotency_key),
        manifest_id=manifest_id,
        algorithm=algorithm,
        seed=seed,
        justification=justification,
        status="QUEUED",
        current_step=STEPS[0][0],
        percentage=0,
        steps_json=[],
        cancellation_requested=False,
        author=author,
        idempotency_key=idempotency_key,
        request_hash=digest,
        correlation_id=correlation_id,
    )
    session.add(row)
    session.add(
        MLGovernanceAuditLog(
            action="TRAINING_QUEUED",
            user_id=author,
            object_type="MLTrainingJob",
            object_id=str(row.id),
            object_version="1.0",
            old_value_json=None,
            new_value_json={
                "manifestId": str(manifest_id),
                "algorithm": algorithm,
                "seed": seed,
                "status": "QUEUED",
            },
            reason=justification,
            trace_id=correlation_id,
        )
    )
    try:
        session.flush()
    except IntegrityError as exc:
        raise Problem(
            409,
            "TRAINING_IN_PROGRESS",
            "Un entraînement est déjà en cours pour ce manifeste.",
        ) from exc
    return row, True


def request_cancellation(
    session: Session, job_id: UUID, actor: str, trace_id: str
) -> MLTrainingJob:
    row = session.get(MLTrainingJob, job_id)
    if row is None:
        raise Problem(404, "TRAINING_NOT_FOUND", "L'entraînement demandé est introuvable.")
    if row.status in TERMINAL_STATUSES:
        return row
    row.cancellation_requested = True
    session.add(
        MLGovernanceAuditLog(
            action="TRAINING_CANCELLATION_REQUESTED",
            user_id=actor,
            object_type="MLTrainingJob",
            object_id=str(row.id),
            object_version="1.0",
            old_value_json={"status": row.status},
            new_value_json={"status": row.status, "cancellationRequested": True},
            reason="Annulation demandée depuis le Studio ML",
            trace_id=trace_id,
        )
    )
    session.flush()
    return row


def _update_job(
    factory: sessionmaker[Session], job_id: UUID, update: Callable[[MLTrainingJob], None]
) -> MLTrainingJob:
    with factory.begin() as session:
        row = session.get(MLTrainingJob, job_id)
        if row is None:
            raise RuntimeError(f"unknown training job: {job_id}")
        update(row)
        session.flush()
        session.refresh(row)
        return row


def _cancel_if_requested(factory: sessionmaker[Session], job_id: UUID) -> bool:
    with factory() as session:
        row = session.get(MLTrainingJob, job_id)
        if row is None:
            return True
        if not row.cancellation_requested:
            return False

    def cancel(item: MLTrainingJob) -> None:
        item.status = "CANCELLED"
        item.current_step = "Annulé"
        item.completed_at = utcnow()

    _update_job(factory, job_id, cancel)
    return True


def _step_start(factory: sessionmaker[Session], job_id: UUID, label: str, percentage: int) -> None:
    def update(row: MLTrainingJob) -> None:
        if row.started_at is None:
            row.started_at = utcnow()
        row.status = "RUNNING"
        row.current_step = label
        row.percentage = percentage
        steps = list(row.steps_json or [])
        steps.append({"name": label, "status": "RUNNING", "startedAt": utcnow().isoformat()})
        row.steps_json = steps

    _update_job(factory, job_id, update)


def _step_finish(
    factory: sessionmaker[Session], job_id: UUID, label: str, percentage: int, detail: str
) -> None:
    def update(row: MLTrainingJob) -> None:
        now = utcnow()
        # Copy every mapping as well as the list. SQLAlchemy's plain JSON type does not
        # track nested in-place mutations, so changing a dict already owned by the
        # persisted value can silently leave the RUNNING state in the database.
        steps = [dict(item) for item in (row.steps_json or [])]
        for item in reversed(steps):
            if item.get("name") == label and item.get("status") == "RUNNING":
                started = datetime.fromisoformat(str(item["startedAt"]))
                item.update(
                    status="COMPLETED",
                    completedAt=now.isoformat(),
                    durationMs=max(0, int((now - started).total_seconds() * 1000)),
                    detail=detail,
                )
                break
        row.steps_json = steps
        row.percentage = percentage

    _update_job(factory, job_id, update)


def _calibration_bins(labels: Sequence[int], scores: Sequence[float]) -> list[dict[str, Any]]:
    bins: list[dict[str, Any]] = []
    for index in range(10):
        low, high = index / 10, (index + 1) / 10
        positions = [
            pos
            for pos, score in enumerate(scores)
            if low <= score < high or (index == 9 and score == 1)
        ]
        count = len(positions)
        bins.append(
            {
                "decile": index + 1,
                "from": low,
                "to": high,
                "count": count,
                "meanPrediction": sum(scores[pos] for pos in positions) / count if count else 0,
                "observedRate": sum(labels[pos] for pos in positions) / count if count else 0,
            }
        )
    return bins


def _ece(bins: Sequence[dict[str, Any]], total: int) -> float:
    if not total:
        return math.nan
    return sum(
        int(item["count"])
        / total
        * abs(float(item["meanPrediction"]) - float(item["observedRate"]))
        for item in bins
    )


def _payload(
    manifest: MLDatasetManifest,
    job: MLTrainingJob,
    feature_order: list[str],
    coefficients: dict[str, float],
    intercept: float,
    metrics: dict[str, Any],
    artifact_checksum: str,
    examples: Sequence[MLTrainingExample],
) -> dict[str, Any]:
    train_dates = [item.observation_as_of for item in examples if item.split == "TRAIN"]
    test_dates = [item.observation_as_of for item in examples if item.split == "TEST"]
    model_version = f"sales-propensity-demo-{str(job.id)[:8]}"
    lineage_examples = [
        {
            "entityId": item.entity_ref,
            "observationAsOf": item.observation_as_of.isoformat(),
            "label": item.label,
            "labelAvailableFrom": item.label_available_from.isoformat(),
            "features": [
                {
                    "featureName": feature,
                    "featureTimestamp": item.observation_as_of.isoformat(),
                    "observationAsOf": item.observation_as_of.isoformat(),
                    "source": "demo-generator",
                    "sourceRecordId": f"{item.entity_ref}:{feature}",
                    "sourceAvailableAt": item.observation_as_of.isoformat(),
                }
                for feature in feature_order
            ],
        }
        for item in examples[:20]
    ]
    return {
        "modelId": "sales-propensity",
        "modelVersion": model_version,
        "featureVersion": str(
            manifest.population_json.get("featureSetVersion", "sales-features-v2")
        ),
        "datasetVersion": manifest.manifest_version,
        "trainingPeriodFrom": min(train_dates).isoformat(),
        "trainingPeriodTo": max(train_dates).isoformat(),
        "validationPeriodFrom": min(test_dates).isoformat(),
        "validationPeriodTo": max(test_dates).isoformat(),
        "testPeriodFrom": min(test_dates).isoformat(),
        "testPeriodTo": max(test_dates).isoformat(),
        "codeVersion": "ml-studio-logit-cpu-v1",
        "hyperparameters": {
            "solver": "lbfgs",
            "classWeight": "balanced",
            "randomState": job.seed,
            "standardization": True,
            "cpuOnly": True,
        },
        "metrics": metrics,
        "lineage": {
            "datasetId": manifest.manifest_version,
            "featureSetVersion": str(
                manifest.population_json.get("featureSetVersion", "sales-features-v2")
            ),
            "trainingCutoff": manifest.training_cutoff.isoformat(),
            "sourceSnapshots": list(manifest.label_snapshot_ids_json or []),
            "codeRevision": "ml-studio-logit-cpu-v1",
            "labelDefinition": manifest.label_definition_version,
            "datasetManifestHash": manifest.manifest_hash,
            "sourceKind": manifest.source_kind,
            "targetOutcome": manifest.target_outcome,
            "horizonDays": manifest.horizon_days,
            "population": manifest.population_json,
            "examples": lineage_examples,
        },
        "deploymentMode": "POC_SHADOW",
        "datasetManifestHash": manifest.manifest_hash,
        "artifactChecksum": artifact_checksum,
        "targetOutcome": manifest.target_outcome,
        "horizonDays": manifest.horizon_days,
        "reason": job.justification,
        "artifact": {
            "algorithm": ALGORITHM,
            "featureOrder": feature_order,
            "coefficients": coefficients,
            "intercept": intercept,
            "threshold": 0.5,
        },
        "registryStatus": "DEMO_ONLY"
        if manifest.source_kind == "DEMO_SYNTHETIC_LABELS"
        else "CHALLENGER",
        "promotable": manifest.source_kind == "BOA_HISTORICAL_OBSERVED",
        "promotionBlockers": (
            ["DEMO_SYNTHETIC_LABELS_NON_PROMOTABLE"]
            if manifest.source_kind == "DEMO_SYNTHETIC_LABELS"
            else []
        ),
    }


def execute_training_job(factory: sessionmaker[Session], job_id: UUID) -> None:
    """Run one deterministic CPU-only training. Each boundary is committed to PostgreSQL."""

    try:
        label, start, end = STEPS[0]
        _step_start(factory, job_id, label, start)
        with factory() as session:
            job = session.get(MLTrainingJob, job_id)
            if job is None:
                raise RuntimeError("job not found")
            manifest = session.get(MLDatasetManifest, job.manifest_id)
            if manifest is None:
                raise RuntimeError("manifest not found")
            manifest_id = manifest.id
            manifest_status = manifest.status
            source_kind = manifest.source_kind
        _step_finish(factory, job_id, label, end, f"Manifeste {manifest_status} chargé")
        if _cancel_if_requested(factory, job_id):
            return

        label, start, end = STEPS[1]
        _step_start(factory, job_id, label, start)
        with factory() as session:
            manifest = session.get(MLDatasetManifest, manifest_id)
            if manifest is None:
                raise RuntimeError("manifest not found")
            examples = list(
                session.scalars(
                    select(MLTrainingExample)
                    .where(MLTrainingExample.manifest_id == manifest_id)
                    .order_by(MLTrainingExample.observation_as_of, MLTrainingExample.entity_ref)
                )
            )
            job = session.get(MLTrainingJob, job_id)
            if job is None:
                raise RuntimeError("job not found")
            allowed = manifest.status == "TRAINING_READY" or source_kind == "DEMO_SYNTHETIC_LABELS"
            leaks = sum(
                item.label_available_from <= item.observation_as_of
                or item.source_kind != source_kind
                for item in examples
            )
            duplicate_count = len(examples) - len(
                {(item.entity_ref, item.observation_as_of) for item in examples}
            )
            positives = sum(item.label for item in examples)
            if not allowed or manifest.status == "BLOCKED":
                error: dict[str, Any] = {
                    "code": "MANIFEST_BLOCKED",
                    "message": "Le manifeste n'est pas autorisé pour l'entraînement.",
                    "details": list(manifest.blockers_json or []),
                }
                _insufficient(factory, job_id, error)
                return
            if source_kind not in TRAINABLE_SOURCES or leaks or duplicate_count:
                error = {
                    "code": "ANTI_LEAKAGE_FAILED",
                    "message": "Les contrôles point-in-time ont échoué.",
                    "details": {"temporalLeaks": leaks, "duplicates": duplicate_count},
                }
                _insufficient(factory, job_id, error)
                return
            if len(examples) < MIN_EXAMPLES or positives < MIN_POSITIVES:
                error = {
                    "code": "INSUFFICIENT_DATA",
                    "message": "Le volume d'apprentissage est inférieur aux seuils prudents.",
                    "details": {
                        "examples": len(examples),
                        "positives": positives,
                        "minimumExamples": MIN_EXAMPLES,
                        "minimumPositives": MIN_POSITIVES,
                    },
                }
                _insufficient(factory, job_id, error)
                return
        _step_finish(
            factory,
            job_id,
            label,
            end,
            f"{len(examples)} exemples, {positives} positifs, aucune fuite détectée",
        )
        if _cancel_if_requested(factory, job_id):
            return

        label, start, end = STEPS[2]
        _step_start(factory, job_id, label, start)
        feature_order = sorted(examples[0].feature_values_json)
        if any(sorted(item.feature_values_json) != feature_order for item in examples):
            raise ValueError("feature order mismatch between training examples")
        train = [item for item in examples if item.split == "TRAIN"]
        test = [item for item in examples if item.split == "TEST"]
        if not train or not test or len({item.label for item in train}) < 2:
            _insufficient(
                factory,
                job_id,
                {
                    "code": "INSUFFICIENT_SPLIT",
                    "message": "Les périodes apprentissage/test ou les classes sont insuffisantes.",
                },
            )
            return
        x_train = [
            [float(item.feature_values_json[key]) for key in feature_order] for item in train
        ]
        y_train = [int(item.label) for item in train]
        x_test = [[float(item.feature_values_json[key]) for key in feature_order] for item in test]
        y_test = [int(item.label) for item in test]
        _step_finish(factory, job_id, label, end, f"{len(examples)} exemples extraits")
        if _cancel_if_requested(factory, job_id):
            return

        label, start, end = STEPS[3]
        _step_start(factory, job_id, label, start)
        from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
        from sklearn.pipeline import make_pipeline  # type: ignore[import-untyped]
        from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]

        with factory() as session:
            job = session.get(MLTrainingJob, job_id)
            if job is None:
                raise RuntimeError("job not found")
            seed = job.seed
        pipeline = make_pipeline(
            StandardScaler(),
            LogisticRegression(solver="lbfgs", class_weight="balanced", random_state=seed),
        )
        pipeline.fit(x_train, y_train)
        scaler = pipeline.named_steps["standardscaler"]
        model = pipeline.named_steps["logisticregression"]
        coefficients_array = model.coef_[0] / scaler.scale_
        intercept = float(model.intercept_[0] - sum(model.coef_[0] * scaler.mean_ / scaler.scale_))
        coefficients = {
            name: round(float(value), 10)
            for name, value in zip(feature_order, coefficients_array, strict=True)
        }
        _step_finish(factory, job_id, label, end, "Régression logistique CPU entraînée")
        if _cancel_if_requested(factory, job_id):
            return

        label, start, end = STEPS[4]
        _step_start(factory, job_id, label, start)
        from sklearn.metrics import (  # type: ignore[import-untyped]
            average_precision_score,
            brier_score_loss,
            confusion_matrix,
            precision_score,
            recall_score,
        )

        scores = [float(value) for value in pipeline.predict_proba(x_test)[:, 1]]
        predictions = [int(value >= 0.5) for value in scores]
        tn, fp, fn, tp = confusion_matrix(y_test, predictions, labels=[0, 1]).ravel()
        metrics: dict[str, Any] = {
            "PR-AUC": round(float(average_precision_score(y_test, scores)), 8),
            "precision": round(float(precision_score(y_test, predictions, zero_division=0)), 8),
            "recall": round(float(recall_score(y_test, predictions, zero_division=0)), 8),
            "brierScore": round(float(brier_score_loss(y_test, scores)), 8),
            "confusionMatrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
            "sampleCount": len(y_test),
            "positiveCount": sum(y_test),
            "productionPerformanceClaim": False,
        }
        _step_finish(factory, job_id, label, end, f"{len(test)} exemples de test évalués")
        if _cancel_if_requested(factory, job_id):
            return

        label, start, end = STEPS[5]
        _step_start(factory, job_id, label, start)
        bins = _calibration_bins(y_test, scores)
        metrics["expectedCalibrationError"] = round(_ece(bins, len(y_test)), 8)
        metrics["calibrationStatus"] = "NOT_VALIDATED"
        metrics["calibrationCurve"] = bins
        _step_finish(factory, job_id, label, end, "Courbe de calibration calculée en déciles")
        if _cancel_if_requested(factory, job_id):
            return

        label, start, end = STEPS[6]
        _step_start(factory, job_id, label, start)
        artifact_body = {
            "featureOrder": feature_order,
            "coefficients": coefficients,
            "intercept": round(intercept, 10),
            "threshold": 0.5,
        }
        artifact_checksum = hashlib.sha256(
            json.dumps(artifact_body, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
        with factory() as session:
            manifest = session.get(MLDatasetManifest, manifest_id)
            job = session.get(MLTrainingJob, job_id)
            if manifest is None or job is None:
                raise RuntimeError("training state disappeared")
            result = _payload(
                manifest,
                job,
                feature_order,
                coefficients,
                round(intercept, 10),
                metrics,
                artifact_checksum,
                examples,
            )
        _step_finish(factory, job_id, label, end, "Artefact candidat et rapport persistés")

        def succeed(row: MLTrainingJob) -> None:
            row.status = "SUCCEEDED"
            row.current_step = "Terminé"
            row.percentage = 100
            row.result_json = result
            row.completed_at = utcnow()

        _update_job(factory, job_id, succeed)
    except Exception as exc:  # noqa: BLE001 - task boundary must persist every failure
        failure_message = str(exc)[:500]

        def fail(row: MLTrainingJob) -> None:
            row.status = "FAILED"
            row.current_step = "Échec"
            row.error_json = {
                "code": "TRAINING_FAILED",
                "message": failure_message,
            }
            row.completed_at = utcnow()

        _update_job(factory, job_id, fail)


def _insufficient(factory: sessionmaker[Session], job_id: UUID, error: dict[str, Any]) -> None:
    def update(row: MLTrainingJob) -> None:
        row.status = "INSUFFICIENT_DATA"
        row.current_step = "Données insuffisantes"
        row.error_json = error
        row.completed_at = utcnow()

    _update_job(factory, job_id, update)


async def run_training_job(factory: sessionmaker[Session], job_id: UUID) -> None:
    await asyncio.to_thread(execute_training_job, factory, job_id)


__all__ = [
    "ALGORITHM",
    "MIN_EXAMPLES",
    "MIN_POSITIVES",
    "STEPS",
    "TERMINAL_STATUSES",
    "create_training_job",
    "execute_training_job",
    "request_cancellation",
    "run_training_job",
    "serialize_job",
]
