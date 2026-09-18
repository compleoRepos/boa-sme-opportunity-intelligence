from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from boa_oi.features import FEATURE_SET_VERSION
from boa_oi.features.service import find_customer, materialize_customer, serialize_feature
from boa_oi.models.entities import FeatureMaterialization
from boa_oi.platform import (
    ANALYTICS_ROLES,
    READ_ROLES,
    create_service_app,
    get_session,
    not_found,
    require_roles,
)

app = create_service_app(
    "feature-store-service",
    "Versioned features derived from Analytics, Signals, "
    "published Rule Studio evaluations and profiles.",
)
PREFIX = "/internal/v1/features"


class MaterializeRequest(BaseModel):
    customerIds: list[str] = Field(min_length=1, max_length=1_000)
    asOf: date
    featureSetVersion: str = FEATURE_SET_VERSION


@app.post(
    f"{PREFIX}/materialize",
    dependencies=[Depends(require_roles(*ANALYTICS_ROLES))],
    tags=["Feature Store"],
)
def materialize(
    payload: MaterializeRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    records = [
        materialize_customer(
            session,
            customer_id,
            payload.asOf,
            payload.featureSetVersion,
        )
        for customer_id in payload.customerIds
    ]
    return {
        "data": [serialize_feature(item) for item in records],
        "meta": {
            "customers": len(records),
            "asOf": payload.asOf.isoformat(),
            "featureSetVersion": payload.featureSetVersion,
        },
    }


@app.post(
    f"{PREFIX}/customers/{{customer_id}}/materialize",
    dependencies=[Depends(require_roles(*ANALYTICS_ROLES))],
    tags=["Feature Store"],
)
def materialize_one(
    customer_id: str,
    as_of: Annotated[date, Query(alias="asOf")],
    feature_set_version: Annotated[str, Query(alias="featureSetVersion")] = FEATURE_SET_VERSION,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return serialize_feature(materialize_customer(session, customer_id, as_of, feature_set_version))


@app.get(
    f"{PREFIX}/customers/{{customer_id}}",
    dependencies=[Depends(require_roles(*READ_ROLES))],
    tags=["Feature Store"],
)
def get_materialized(
    customer_id: str,
    as_of: Annotated[date, Query(alias="asOf")],
    feature_set_version: Annotated[str, Query(alias="featureSetVersion")] = FEATURE_SET_VERSION,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    customer = find_customer(session, customer_id)
    record = session.scalar(
        select(FeatureMaterialization).where(
            FeatureMaterialization.customer_id == customer.id,
            FeatureMaterialization.as_of_date == as_of,
            FeatureMaterialization.feature_set_version == feature_set_version,
        )
    )
    if record is None:
        raise not_found("Feature materialization")
    return serialize_feature(record)


__all__ = ["app"]
