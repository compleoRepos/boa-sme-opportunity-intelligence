from __future__ import annotations

import os
from datetime import date, datetime, time, timezone
from typing import Annotated, Any

from fastapi import Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from boa_oi.features import FEATURE_SET_VERSION
from boa_oi.features.service import materialize_customer
from boa_oi.http_clients import service_request
from boa_oi.ml.governance import canonical_digest, dataset_manifest_blockers
from boa_oi.ml.service import active_model, score_materialization, serialize_model, serialize_score
from boa_oi.ml_training.routes import router as ml_training_router
from boa_oi.mlops.routes import router as ml_governance_router
from boa_oi.models.entities import (
    ActionOutcome,
    FeatureMaterialization,
    MLDatasetManifest,
    ModelRegistry,
    Opportunity,
    OpportunityAction,
    OutcomeLabelSnapshot,
)
from boa_oi.operations.api import router as operations_router
from boa_oi.platform import (
    READ_ROLES,
    Problem,
    correlation_id,
    create_service_app,
    get_session,
    require_roles,
)
from boa_oi.technical.ids import deterministic_uuid

app = create_service_app(
    "ml-engine-service",
    "Deterministic CPU-only logistic sales propensity scoring with per-feature explanations.",
)
app.include_router(ml_governance_router)
app.include_router(ml_training_router)
app.include_router(operations_router)
PREFIX = "/internal/v1/ml"
ML_SCORE_ROLES = ("DATA_ANALYST", "ADMIN", "SERVICE")
ML_GOVERNANCE_ROLES = ("DATA_ANALYST", "ML_STEWARD", "RULE_APPROVER", "ADMIN", "SERVICE")


class ScoreRequest(BaseModel):
    asOf: date
    featureSetVersion: str = FEATURE_SET_VERSION
    modelVersion: str | None = None


class BatchScoreRequest(ScoreRequest):
    customerIds: list[str] = Field(min_length=1, max_length=1_000)


class OutcomeMaterializationRequest(BaseModel):
    snapshotVersion: str = Field(min_length=3, max_length=40)
    labelDefinitionVersion: str = Field(min_length=3, max_length=80)
    targetOutcome: str = Field(min_length=3, max_length=80)
    horizonDays: int = Field(gt=0, le=3650)
    population: dict[str, Any] = Field(min_length=1)
    observationAsOf: date
    labelAvailableFrom: date


class DatasetManifestRequest(BaseModel):
    manifestVersion: str = Field(min_length=3, max_length=80)
    snapshotVersion: str = Field(min_length=3, max_length=40)
    labelDefinitionVersion: str = Field(min_length=3, max_length=80)
    purpose: str = Field(min_length=3, max_length=60)
    targetOutcome: str = Field(min_length=3, max_length=80)
    horizonDays: int = Field(gt=0, le=3650)
    population: dict[str, Any] = Field(min_length=1)
    exclusions: list[str] = Field(default_factory=list)
    trainingCutoff: date


async def _score_customer(
    session: Session,
    customer_id: str,
    payload: ScoreRequest,
    http_request: Request,
) -> dict[str, Any]:
    feature_store_url = os.getenv("FEATURE_STORE_SERVICE_URL")
    if feature_store_url:
        feature_payload = await service_request(
            "POST",
            f"{feature_store_url.rstrip('/')}/internal/v1/features/customers/"
            f"{customer_id}/materialize",
            correlation_id=correlation_id(http_request),
            params={
                "asOf": payload.asOf.isoformat(),
                "featureSetVersion": payload.featureSetVersion,
            },
            incoming_authorization=http_request.headers.get("Authorization"),
        )
        features = FeatureMaterialization(
            id=deterministic_uuid(
                "feature-materialization",
                deterministic_uuid("customer", customer_id),
                payload.asOf,
                payload.featureSetVersion,
            ),
            customer_id=deterministic_uuid("customer", customer_id),
            customer_ref=customer_id,
            as_of_date=payload.asOf,
            feature_set_version=str(feature_payload["featureSetVersion"]),
            values_json=feature_payload["values"],
            sources_json=feature_payload["sources"],
            lineage_json=feature_payload["lineage"],
            checksum=str(feature_payload["checksum"]),
            created_by="feature-store-service",
        )
    else:
        # Test-only in-process path. Runtime Compose always configures the service URL.
        features = materialize_customer(
            session,
            customer_id,
            payload.asOf,
            payload.featureSetVersion,
        )
    score = score_materialization(
        session,
        features,
        model_version=payload.modelVersion,
        prediction_trace_id=correlation_id(http_request),
    )
    return serialize_score(score)


@app.post(
    f"{PREFIX}/customers/{{customer_id}}/score",
    dependencies=[Depends(require_roles(*ML_SCORE_ROLES))],
    tags=["ML Scoring"],
)
async def score_customer(
    customer_id: str,
    payload: ScoreRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return await _score_customer(session, customer_id, payload, request)


@app.post(
    f"{PREFIX}/scores/batch",
    dependencies=[Depends(require_roles(*ML_SCORE_ROLES))],
    tags=["ML Scoring"],
)
async def score_batch(
    payload: BatchScoreRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    score_request = ScoreRequest(
        asOf=payload.asOf,
        featureSetVersion=payload.featureSetVersion,
        modelVersion=payload.modelVersion,
    )
    data = [
        await _score_customer(session, customer_id, score_request, request)
        for customer_id in payload.customerIds
    ]
    return {
        "data": data,
        "meta": {
            "customers": len(data),
            "asOf": payload.asOf.isoformat(),
            "scoreType": "SALES_PROPENSITY",
        },
    }


@app.get(
    f"{PREFIX}/models",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Model Registry"],
)
def list_models(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Registre complet des modèles (actifs, candidats, retirés) pour l'écran de gouvernance ML."""
    records = list(
        session.scalars(select(ModelRegistry).order_by(ModelRegistry.model_version.desc()))
    )
    data = [
        {
            **serialize_model(record),
            "createdAt": record.created_at.isoformat(),
            "updatedAt": record.updated_at.isoformat(),
        }
        for record in records
    ]
    return {"data": data, "meta": {"totalCount": len(data), "scoreType": "SALES_PROPENSITY"}}


@app.get(
    f"{PREFIX}/models/active",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Model Registry"],
)
def get_active_model(session: Session = Depends(get_session)) -> dict[str, Any]:
    return serialize_model(active_model(session))


@app.get(
    f"{PREFIX}/models/{{model_version}}",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Model Registry"],
)
def get_model(
    model_version: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return serialize_model(active_model(session, model_version))


@app.get(
    f"{PREFIX}/outcomes/snapshots",
    dependencies=[Depends(require_roles(*ML_GOVERNANCE_ROLES))],
    tags=["Future Outcome Labels"],
)
def outcome_snapshots(
    snapshot_version: Annotated[str | None, Query(alias="snapshotVersion")] = None,
    available_on: Annotated[date | None, Query(alias="availableOn")] = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(OutcomeLabelSnapshot)
    if snapshot_version:
        stmt = stmt.where(OutcomeLabelSnapshot.snapshot_version == snapshot_version)
    if available_on:
        stmt = stmt.where(OutcomeLabelSnapshot.label_available_from <= available_on)
    records = list(
        session.scalars(
            stmt.order_by(
                OutcomeLabelSnapshot.label_available_from,
                OutcomeLabelSnapshot.customer_ref,
            )
        )
    )
    data = [
        {
            "snapshotVersion": item.snapshot_version,
            "datasetVersion": item.dataset_version,
            "customerId": item.customer_ref,
            "opportunityId": item.opportunity_ref,
            "opportunityType": item.opportunity_type,
            "actionId": str(item.action_id) if item.action_id else None,
            "scoreType": item.score_type,
            "observationAsOf": item.observation_as_of.isoformat(),
            "observedAt": item.observed_at.isoformat(),
            "labelAvailableFrom": item.label_available_from.isoformat(),
            "outcomeLabel": item.outcome_label,
            "outcomeValue": item.outcome_value,
            "source": item.source,
            "sourceKind": item.source_kind,
            "sourceReference": item.source_reference,
            "labelDefinitionVersion": item.label_definition_version,
            "targetOutcome": item.target_outcome,
            "horizonDays": item.horizon_days,
            "population": item.population_json,
            "windowClosed": item.window_closed,
            "candidateOnly": item.candidate_only,
            "featureSnapshotId": str(item.feature_snapshot_id)
            if item.feature_snapshot_id
            else None,
            "featureChecksum": item.feature_checksum,
            "datasetManifestHash": item.dataset_manifest_hash,
            "maturityStatus": (
                "MATURE"
                if item.label_available_from <= datetime.now(timezone.utc).date()
                else "IMMATURE"
            ),
        }
        for item in records
    ]
    return {
        "data": data,
        "meta": {
            "totalCount": len(data),
            "purpose": "FUTURE_LABEL_SNAPSHOT_ONLY",
            "automaticTraining": False,
            "historicalBoaLabelsAvailable": False,
            "trainingReady": False,
        },
    }


@app.post(
    f"{PREFIX}/outcomes/materialize",
    dependencies=[Depends(require_roles("DATA_ANALYST", "ML_STEWARD", "ADMIN", "SERVICE"))],
    tags=["Future Outcome Labels"],
)
def materialize_outcomes(
    payload: OutcomeMaterializationRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if payload.labelAvailableFrom <= payload.observationAsOf:
        raise Problem(
            422,
            "INVALID_LABEL_WINDOW",
            "labelAvailableFrom must be after observationAsOf.",
        )
    labels: dict[str, tuple[str, bool | None]] = {
        "CONTACTED": ("CONTACTED", None),
        "MEETING_SCHEDULED": ("INTERESTED", None),
        "OFFER_CREATED": ("OFFER_CREATED", None),
        "CONVERTED": ("CONVERTED", True),
        "REJECTED": ("NOT_INTERESTED", False),
        "NOT_RELEVANT": ("REVIEW_LATER", None),
    }
    rows = session.execute(
        select(ActionOutcome, OpportunityAction, Opportunity)
        .join(OpportunityAction, OpportunityAction.id == ActionOutcome.action_id)
        .join(Opportunity, Opportunity.id == OpportunityAction.opportunity_id)
        .where(
            ActionOutcome.outcome_type.in_(tuple(labels)),
            ActionOutcome.recorded_at
            >= datetime.combine(payload.observationAsOf, time.min, tzinfo=timezone.utc),
            ActionOutcome.recorded_at
            < datetime.combine(payload.labelAvailableFrom, time.min, tzinfo=timezone.utc),
        )
        .order_by(ActionOutcome.recorded_at, ActionOutcome.id)
    ).all()
    materialized_customers: set[str] = set()
    for outcome, action, opportunity in rows:
        outcome_label, outcome_value = labels[outcome.outcome_type]
        feature_snapshot = session.scalar(
            select(FeatureMaterialization)
            .where(
                FeatureMaterialization.customer_id == action.customer_id,
                FeatureMaterialization.as_of_date <= payload.observationAsOf,
            )
            .order_by(FeatureMaterialization.as_of_date.desc())
        )
        existing = session.scalar(
            select(OutcomeLabelSnapshot).where(
                OutcomeLabelSnapshot.snapshot_version == payload.snapshotVersion,
                OutcomeLabelSnapshot.label_definition_version == payload.labelDefinitionVersion,
                OutcomeLabelSnapshot.customer_id == action.customer_id,
                OutcomeLabelSnapshot.observation_as_of == payload.observationAsOf,
                OutcomeLabelSnapshot.label_available_from == payload.labelAvailableFrom,
            )
        )
        record = existing or OutcomeLabelSnapshot(
            id=deterministic_uuid(
                "outcome-label",
                payload.snapshotVersion,
                payload.labelDefinitionVersion,
                action.customer_id,
                payload.observationAsOf,
                payload.labelAvailableFrom,
            ),
            snapshot_version=payload.snapshotVersion,
            dataset_version=payload.snapshotVersion,
            customer_id=action.customer_id,
            customer_ref=action.customer_ref,
            opportunity_id=opportunity.id,
            opportunity_ref=opportunity.opportunity_ref,
            opportunity_type=opportunity.opportunity_type,
            action_id=action.id,
            score_type="SALES_PROPENSITY",
            observation_as_of=payload.observationAsOf,
            observed_at=outcome.recorded_at,
            label_available_from=payload.labelAvailableFrom,
            outcome_label=outcome_label,
            outcome_value=outcome_value,
            source_reference=f"action-outcome:{outcome.id}",
            source="COMMERCIAL_OUTCOME",
            label_definition_version=payload.labelDefinitionVersion,
            target_outcome=payload.targetOutcome,
            horizon_days=payload.horizonDays,
            population_json=payload.population,
            source_kind="LOCAL_COMMERCIAL_OUTCOME",
            window_closed=payload.labelAvailableFrom <= datetime.now(timezone.utc).date(),
            candidate_only=True,
            feature_snapshot_id=feature_snapshot.id if feature_snapshot else None,
            feature_checksum=feature_snapshot.checksum if feature_snapshot else None,
        )
        record.dataset_version = payload.snapshotVersion
        record.opportunity_id = opportunity.id
        record.opportunity_ref = opportunity.opportunity_ref
        record.opportunity_type = opportunity.opportunity_type
        record.action_id = action.id
        record.observed_at = outcome.recorded_at
        record.outcome_label = outcome_label
        record.outcome_value = outcome_value
        record.source_reference = f"action-outcome:{outcome.id}"
        record.label_definition_version = payload.labelDefinitionVersion
        record.target_outcome = payload.targetOutcome
        record.horizon_days = payload.horizonDays
        record.population_json = payload.population
        record.source_kind = "LOCAL_COMMERCIAL_OUTCOME"
        record.window_closed = payload.labelAvailableFrom <= datetime.now(timezone.utc).date()
        record.candidate_only = True
        record.feature_snapshot_id = feature_snapshot.id if feature_snapshot else None
        record.feature_checksum = feature_snapshot.checksum if feature_snapshot else None
        session.add(record)
        materialized_customers.add(action.customer_ref)
    session.flush()
    return {
        "snapshotVersion": payload.snapshotVersion,
        "labelDefinitionVersion": payload.labelDefinitionVersion,
        "targetOutcome": payload.targetOutcome,
        "horizonDays": payload.horizonDays,
        "labelsWritten": len(materialized_customers),
        "sourceEventsRead": len(rows),
        "observationAsOf": payload.observationAsOf.isoformat(),
        "labelAvailableFrom": payload.labelAvailableFrom.isoformat(),
        "automaticTraining": False,
        "trainingReady": False,
        "activationBlockers": [
            "BOA_HISTORICAL_LABELS_UNAVAILABLE",
            "LOCAL_OUTCOMES_ARE_CANDIDATE_LABELS_ONLY",
        ],
        "purpose": "FUTURE_GOVERNED_LABEL_DATASET",
    }


def _serialize_manifest(record: MLDatasetManifest) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "manifestVersion": record.manifest_version,
        "sourceKind": record.source_kind,
        "purpose": record.purpose,
        "targetOutcome": record.target_outcome,
        "labelDefinitionVersion": record.label_definition_version,
        "horizonDays": record.horizon_days,
        "population": record.population_json,
        "exclusions": record.exclusions_json,
        "trainingCutoff": record.training_cutoff.isoformat(),
        "featureSnapshotIds": record.feature_snapshot_ids_json,
        "labelSnapshotIds": record.label_snapshot_ids_json,
        "rowCount": record.row_count,
        "manifestHash": record.manifest_hash,
        "status": record.status,
        "activationBlockers": record.blockers_json,
        "createdAt": record.created_at.isoformat() if record.created_at else None,
    }


@app.post(
    f"{PREFIX}/datasets/manifests",
    dependencies=[Depends(require_roles("DATA_ANALYST", "ML_STEWARD", "ADMIN", "SERVICE"))],
    tags=["ML Dataset Governance"],
)
def create_dataset_manifest(
    payload: DatasetManifestRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    labels = list(
        session.scalars(
            select(OutcomeLabelSnapshot)
            .where(
                OutcomeLabelSnapshot.snapshot_version == payload.snapshotVersion,
                OutcomeLabelSnapshot.label_definition_version == payload.labelDefinitionVersion,
            )
            .order_by(OutcomeLabelSnapshot.customer_ref, OutcomeLabelSnapshot.id)
        )
    )
    label_payloads = [
        {
            "sourceKind": item.source_kind,
            "candidateOnly": item.candidate_only,
            "windowClosed": item.window_closed,
            "outcomeValue": item.outcome_value,
            "featureSnapshotId": str(item.feature_snapshot_id)
            if item.feature_snapshot_id
            else None,
            "labelAvailableFrom": item.label_available_from.isoformat(),
        }
        for item in labels
    ]
    feature_ids = sorted(
        {str(item.feature_snapshot_id) for item in labels if item.feature_snapshot_id is not None}
    )
    source_kind = (
        labels[0].source_kind
        if labels and all(item.source_kind == labels[0].source_kind for item in labels)
        else "LOCAL_COMMERCIAL_OUTCOME"
    )
    blockers = dataset_manifest_blockers(
        source_kind=source_kind,
        feature_snapshot_ids=feature_ids,
        labels=label_payloads,
        training_cutoff=payload.trainingCutoff.isoformat(),
    )
    manifest_payload = {
        "manifestVersion": payload.manifestVersion,
        "sourceKind": source_kind,
        "purpose": payload.purpose,
        "targetOutcome": payload.targetOutcome,
        "labelDefinitionVersion": payload.labelDefinitionVersion,
        "horizonDays": payload.horizonDays,
        "population": payload.population,
        "exclusions": sorted(payload.exclusions),
        "trainingCutoff": payload.trainingCutoff.isoformat(),
        "featureSnapshotIds": feature_ids,
        "labelSnapshotIds": [str(item.id) for item in labels],
    }
    manifest_hash = canonical_digest(manifest_payload)
    existing = session.scalar(
        select(MLDatasetManifest).where(
            MLDatasetManifest.manifest_version == payload.manifestVersion
        )
    )
    if existing is not None:
        if existing.manifest_hash != manifest_hash:
            raise Problem(
                409,
                "DATASET_MANIFEST_CONFLICT",
                "The manifest version already exists with different point-in-time inputs.",
            )
        return _serialize_manifest(existing)
    record = MLDatasetManifest(
        id=deterministic_uuid("ml-dataset-manifest", payload.manifestVersion),
        manifest_version=payload.manifestVersion,
        source_kind=source_kind,
        purpose=payload.purpose,
        target_outcome=payload.targetOutcome,
        label_definition_version=payload.labelDefinitionVersion,
        horizon_days=payload.horizonDays,
        population_json=payload.population,
        exclusions_json=sorted(payload.exclusions),
        training_cutoff=payload.trainingCutoff,
        feature_snapshot_ids_json=feature_ids,
        label_snapshot_ids_json=[str(item.id) for item in labels],
        row_count=len(labels),
        manifest_hash=manifest_hash,
        status="BLOCKED" if blockers else "CANDIDATE",
        blockers_json=blockers,
        created_by="ml-engine-service",
    )
    session.add(record)
    for item in labels:
        item.dataset_manifest_hash = manifest_hash
    session.flush()
    return _serialize_manifest(record)


@app.get(
    f"{PREFIX}/datasets/manifests",
    dependencies=[Depends(require_roles(*ML_GOVERNANCE_ROLES))],
    tags=["ML Dataset Governance"],
)
def list_dataset_manifests(session: Session = Depends(get_session)) -> dict[str, Any]:
    records = list(
        session.scalars(select(MLDatasetManifest).order_by(MLDatasetManifest.created_at.desc()))
    )
    return {
        "data": [_serialize_manifest(item) for item in records],
        "meta": {"totalCount": len(records), "deploymentMode": "POC_SHADOW"},
    }


__all__ = ["app"]
