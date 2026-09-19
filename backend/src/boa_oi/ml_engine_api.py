from __future__ import annotations

import os
from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from boa_oi.features import FEATURE_SET_VERSION
from boa_oi.features.service import materialize_customer
from boa_oi.http_clients import service_request
from boa_oi.ml.service import active_model, score_materialization, serialize_model, serialize_score
from boa_oi.models.entities import (
    ActionOutcome,
    FeatureMaterialization,
    OpportunityAction,
    OutcomeLabelSnapshot,
)
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
PREFIX = "/internal/v1/ml"
ML_SCORE_ROLES = ("DATA_ANALYST", "ADMIN", "SERVICE")


class ScoreRequest(BaseModel):
    asOf: date
    featureSetVersion: str = FEATURE_SET_VERSION
    modelVersion: str | None = None


class BatchScoreRequest(ScoreRequest):
    customerIds: list[str] = Field(min_length=1, max_length=1_000)


class OutcomeMaterializationRequest(BaseModel):
    snapshotVersion: str = Field(min_length=3, max_length=40)
    observationAsOf: date
    labelAvailableFrom: date


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
    dependencies=[Depends(require_roles(*READ_ROLES))],
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
            "customerId": item.customer_ref,
            "scoreType": item.score_type,
            "observationAsOf": item.observation_as_of.isoformat(),
            "labelAvailableFrom": item.label_available_from.isoformat(),
            "outcomeLabel": item.outcome_label,
            "outcomeValue": item.outcome_value,
            "sourceReference": item.source_reference,
        }
        for item in records
    ]
    return {
        "data": data,
        "meta": {
            "totalCount": len(data),
            "purpose": "FUTURE_LABEL_SNAPSHOT_ONLY",
            "automaticTraining": False,
        },
    }


@app.post(
    f"{PREFIX}/outcomes/materialize",
    dependencies=[Depends(require_roles("DATA_ANALYST", "ADMIN", "SERVICE"))],
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
    terminal = {"CONVERTED": True, "REJECTED": False, "NOT_RELEVANT": False}
    rows = session.execute(
        select(ActionOutcome, OpportunityAction)
        .join(OpportunityAction, OpportunityAction.id == ActionOutcome.action_id)
        .where(
            ActionOutcome.outcome_type.in_(tuple(terminal)),
            ActionOutcome.recorded_at < payload.labelAvailableFrom,
        )
        .order_by(ActionOutcome.recorded_at, ActionOutcome.id)
    ).all()
    materialized_customers: set[str] = set()
    for outcome, action in rows:
        existing = session.scalar(
            select(OutcomeLabelSnapshot).where(
                OutcomeLabelSnapshot.snapshot_version == payload.snapshotVersion,
                OutcomeLabelSnapshot.customer_id == action.customer_id,
                OutcomeLabelSnapshot.observation_as_of == payload.observationAsOf,
                OutcomeLabelSnapshot.label_available_from == payload.labelAvailableFrom,
            )
        )
        record = existing or OutcomeLabelSnapshot(
            id=deterministic_uuid(
                "outcome-label",
                payload.snapshotVersion,
                action.customer_id,
                payload.observationAsOf,
                payload.labelAvailableFrom,
            ),
            snapshot_version=payload.snapshotVersion,
            customer_id=action.customer_id,
            customer_ref=action.customer_ref,
            score_type="SALES_PROPENSITY",
            observation_as_of=payload.observationAsOf,
            label_available_from=payload.labelAvailableFrom,
            outcome_label="COMMERCIAL_CONVERSION",
            outcome_value=terminal[outcome.outcome_type],
            source_reference=f"action-outcome:{outcome.id}",
        )
        record.outcome_value = terminal[outcome.outcome_type]
        record.source_reference = f"action-outcome:{outcome.id}"
        session.add(record)
        materialized_customers.add(action.customer_ref)
    session.flush()
    return {
        "snapshotVersion": payload.snapshotVersion,
        "labelsWritten": len(materialized_customers),
        "sourceEventsRead": len(rows),
        "observationAsOf": payload.observationAsOf.isoformat(),
        "labelAvailableFrom": payload.labelAvailableFrom.isoformat(),
        "automaticTraining": False,
        "trainingReady": False,
        "purpose": "FUTURE_GOVERNED_LABEL_DATASET",
    }


__all__ = ["app"]
