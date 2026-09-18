from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from boa_oi.features import FEATURE_ORDER
from boa_oi.models.entities import FeatureMaterialization, ModelRegistry, PropensityScoreRecord
from boa_oi.platform import Problem, not_found
from boa_oi.technical.ids import deterministic_uuid

from .domain import FeatureContribution, LogisticModel, LogisticScorer, ModelStatus


def model_from_record(record: ModelRegistry) -> LogisticModel:
    return LogisticModel(
        model_version=record.model_version,
        feature_set_version=record.feature_set_version,
        coefficients={name: float(value) for name, value in record.coefficients_json.items()},
        intercept=float(record.intercept),
        feature_order=tuple(record.feature_order_json),
        threshold=float(record.threshold),
        validation_metrics=record.validation_metrics_json,
        status=cast(ModelStatus, record.status),
    )


def active_model(session: Session, model_version: str | None = None) -> ModelRegistry:
    stmt = select(ModelRegistry)
    if model_version is None:
        stmt = stmt.where(ModelRegistry.status == "ACTIVE")
    else:
        stmt = stmt.where(ModelRegistry.model_version == model_version)
    record = session.scalar(stmt.order_by(ModelRegistry.model_version.desc()))
    if record is None:
        raise not_found("Model")
    if model_version is None and record.status != "ACTIVE":
        raise Problem(409, "ACTIVE_MODEL_UNAVAILABLE", "No active model is available.")
    return record


def score_materialization(
    session: Session,
    feature_record: FeatureMaterialization,
    *,
    model_version: str | None = None,
) -> PropensityScoreRecord:
    model_record = active_model(session, model_version)
    model = model_from_record(model_record)
    if tuple(feature_record.values_json) != FEATURE_ORDER:
        raise Problem(
            409,
            "FEATURE_ORDER_MISMATCH",
            "The materialized vector does not follow the declared feature order.",
        )
    try:
        score = LogisticScorer().score(
            model,
            {name: float(value) for name, value in feature_record.values_json.items()},
            feature_version=feature_record.feature_set_version,
            feature_checksum=feature_record.checksum,
            segment=_segment(feature_record),
        )
    except ValueError as exc:
        raise Problem(409, "MODEL_FEATURE_INCOMPATIBLE", str(exc)) from exc

    existing = session.scalar(
        select(PropensityScoreRecord).where(
            PropensityScoreRecord.customer_id == feature_record.customer_id,
            PropensityScoreRecord.as_of_date == feature_record.as_of_date,
            PropensityScoreRecord.model_version == model.model_version,
            PropensityScoreRecord.feature_checksum == feature_record.checksum,
        )
    )
    record = existing or PropensityScoreRecord(
        id=deterministic_uuid(
            "propensity-score",
            feature_record.customer_id,
            feature_record.as_of_date,
            model.model_version,
            feature_record.checksum,
        ),
        customer_id=feature_record.customer_id,
        customer_ref=feature_record.customer_ref,
        as_of_date=feature_record.as_of_date,
        score_type=score.score_type,
        score=score.propensity,
        threshold=score.threshold,
        above_threshold=score.above_threshold,
        calibration=score.calibration,
        segment=score.segment,
        model_version=score.model_version,
        feature_set_version=score.feature_version,
        feature_checksum=score.feature_checksum,
        contributions_json=[_contribution_payload(item) for item in score.contributions],
        top_factors_json=[_contribution_payload(item) for item in score.top_factors],
        training_dataset_version=model_record.training_dataset_version,
        deployment_mode=model_record.deployment_mode,
        created_by="ml-engine-service",
    )
    record.score = Decimal(str(score.propensity))
    record.threshold = Decimal(str(score.threshold))
    record.above_threshold = score.above_threshold
    record.calibration = score.calibration
    record.segment = score.segment
    record.contributions_json = [_contribution_payload(item) for item in score.contributions]
    record.top_factors_json = [_contribution_payload(item) for item in score.top_factors]
    record.training_dataset_version = model_record.training_dataset_version
    record.deployment_mode = model_record.deployment_mode
    session.add(record)
    session.flush()
    return record


def _segment(record: FeatureMaterialization) -> str:
    for source in record.sources_json:
        if source.get("sourceType") == "CUSTOMER_PROFILE":
            return str(source.get("segment", "UNKNOWN"))
    return "UNKNOWN"


def _contribution_payload(item: FeatureContribution) -> dict[str, Any]:
    return {
        "feature": item.feature,
        "value": item.value,
        "coefficient": item.coefficient,
        "contribution": item.contribution,
        "direction": item.direction,
    }


def serialize_model(record: ModelRegistry) -> dict[str, Any]:
    return {
        "modelVersion": record.model_version,
        "scoreType": record.score_type,
        "algorithm": record.algorithm,
        "status": record.status,
        "featureSetVersion": record.feature_set_version,
        "featureOrder": record.feature_order_json,
        "coefficients": record.coefficients_json,
        "intercept": float(record.intercept),
        "threshold": float(record.threshold),
        "validationMetrics": record.validation_metrics_json,
        "trainingDatasetVersion": record.training_dataset_version,
        "trainingCodeVersion": record.training_code_version,
        "deploymentMode": record.deployment_mode,
        "productionPerformanceClaim": False,
        "automaticTraining": False,
    }


def serialize_score(record: PropensityScoreRecord) -> dict[str, Any]:
    return {
        "customerId": record.customer_ref,
        "asOf": record.as_of_date.isoformat(),
        "scoreType": record.score_type,
        "propensity": float(record.score),
        "threshold": float(record.threshold),
        "aboveThreshold": record.above_threshold,
        "calibration": record.calibration,
        "segment": record.segment,
        "modelVersion": record.model_version,
        "featureVersion": record.feature_set_version,
        "featureChecksum": record.feature_checksum,
        "contributions": record.contributions_json,
        "topFactors": record.top_factors_json,
        "trainingDatasetVersion": record.training_dataset_version,
        "deploymentMode": record.deployment_mode,
        "traceId": str(record.id),
        "scoredAt": record.created_at.isoformat(),
    }


__all__ = [
    "active_model",
    "model_from_record",
    "score_materialization",
    "serialize_model",
    "serialize_score",
]
