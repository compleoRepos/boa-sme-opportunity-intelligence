from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from boa_oi.api import application_for
from boa_oi.features import (
    FEATURE_ORDER,
    FEATURE_SET_VERSION,
    AnalyticsSnapshot,
    CustomerProfile,
    FeatureBuilder,
)
from boa_oi.ml import LogisticModel, LogisticScorer, stable_sigmoid
from boa_oi.models.entities import (
    Customer,
    ActionOutcome,
    FeatureMaterialization,
    MetricSnapshot,
    ModelRegistry,
    OutcomeLabelSnapshot,
    OpportunityAction,
    PropensityScoreRecord,
    Rule,
    RuleVersion,
    Signal,
)
from boa_oi.technical.ids import deterministic_uuid
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

AS_OF = date(2026, 9, 30)
MODEL_VERSION = "sales-propensity-logit-poc-v1"
COEFFICIENTS = {
    "cash_inflow_growth_90d": 0.8,
    "supplier_payment_growth_90d": 0.35,
    "international_activity_ratio_90d": 1.1,
    "balance_strength_90d": 0.65,
    "activity_density_90d": 0.45,
    "analytics_coverage_90d": 0.3,
    "customer_tenure_ratio": 0.2,
    "segment_medium": 0.25,
    "confirmed_signal_ratio": 0.4,
    "published_rule_match_strength": 0.75,
}


def model() -> LogisticModel:
    return LogisticModel(
        model_version=MODEL_VERSION,
        feature_set_version=FEATURE_SET_VERSION,
        coefficients=COEFFICIENTS,
        intercept=-1.35,
        feature_order=FEATURE_ORDER,
        threshold=0.58,
        validation_metrics={"aucRocSynthetic": 0.78, "brierScoreSynthetic": 0.18},
        status="ACTIVE",
    )


def snapshot(*, inflow_growth: float = 0.4, watermark: str = "analytics-snapshot-42"):
    def metric(current: float, growth: float = 0.1, coverage: float = 0.95):
        return {
            "currentValue": current,
            "growthRate": growth,
            "dataCoverage": coverage,
        }

    return AnalyticsSnapshot(
        customer_id="SME-00125",
        as_of=AS_OF,
        window_days=90,
        calculation_version="analytics-0.1.0",
        values={
            "inflow_amount": metric(2_000_000, inflow_growth),
            "outflow_amount": metric(1_400_000),
            "supplier_payment_amount": metric(700_000, 0.25),
            "international_flow_amount": metric(300_000),
            "average_balance": metric(900_000),
            "transaction_count": metric(850),
        },
        input_watermark=watermark,
    )


def profile() -> CustomerProfile:
    return CustomerProfile(
        customer_id="SME-00125",
        segment_code="MEDIUM",
        incorporated_on=date(2018, 6, 1),
    )


def built_features(**snapshot_overrides):
    return FeatureBuilder().build(profile(), [snapshot(**snapshot_overrides)], AS_OF)


def test_probability_is_bounded_for_extreme_cpu_inputs():
    scorer = LogisticScorer()
    low = scorer.score(
        model(),
        dict.fromkeys(FEATURE_ORDER, -1e6),
        feature_version=FEATURE_SET_VERSION,
        feature_checksum="0" * 64,
        segment="SMALL",
    )
    high = scorer.score(
        model(),
        dict.fromkeys(FEATURE_ORDER, 1e6),
        feature_version=FEATURE_SET_VERSION,
        feature_checksum="1" * 64,
        segment="MEDIUM",
    )
    assert 0.0 <= low.propensity < high.propensity <= 1.0
    assert stable_sigmoid(-1e6) == 0.0
    assert stable_sigmoid(1e6) == 1.0


def test_positive_coefficient_is_monotonic():
    scorer = LogisticScorer()
    baseline = dict.fromkeys(FEATURE_ORDER, 0.0)
    increased = baseline | {"cash_inflow_growth_90d": 0.8}
    first = scorer.score(
        model(),
        baseline,
        feature_version=FEATURE_SET_VERSION,
        feature_checksum="a" * 64,
        segment="SMALL",
    )
    second = scorer.score(
        model(),
        increased,
        feature_version=FEATURE_SET_VERSION,
        feature_checksum="b" * 64,
        segment="SMALL",
    )
    assert second.propensity > first.propensity


def test_explanation_reconstructs_logit_and_orders_top_factors():
    vector = built_features()
    result = LogisticScorer().score(
        model(),
        vector.values,
        feature_version=vector.feature_set_version,
        feature_checksum=vector.checksum,
        segment="MEDIUM",
    )
    reconstructed = model().intercept + sum(item.contribution for item in result.contributions)
    assert result.propensity == pytest.approx(stable_sigmoid(reconstructed))
    assert [item.feature for item in result.contributions] == list(FEATURE_ORDER)
    assert len(result.top_factors) == 3
    assert [abs(item.contribution) for item in result.top_factors] == sorted(
        (abs(item.contribution) for item in result.contributions), reverse=True
    )[:3]
    assert result.score_type == "SALES_PROPENSITY"
    assert result.segment == "MEDIUM"
    assert result.calibration in {"LOW", "MEDIUM", "HIGH"}


def test_materialized_features_are_deterministic_versioned_and_checksum_sensitive():
    first = built_features()
    repeated = built_features()
    changed = built_features(inflow_growth=0.5)
    lineage_changed = built_features(watermark="analytics-snapshot-43")
    assert first == repeated
    assert first.feature_set_version == FEATURE_SET_VERSION
    assert tuple(first.values) == FEATURE_ORDER
    assert len(first.checksum) == 64
    assert first.checksum != changed.checksum
    assert first.checksum != lineage_changed.checksum
    assert {item["sourceType"] for item in first.sources} == {
        "ANALYTICS_SNAPSHOT",
        "CUSTOMER_PROFILE",
        "SIGNAL_SERVICE",
        "RULE_STUDIO",
    }


def memory_factory():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        Customer.__mapper__.local_table,
        MetricSnapshot.__mapper__.local_table,
        FeatureMaterialization.__mapper__.local_table,
        ModelRegistry.__mapper__.local_table,
        PropensityScoreRecord.__mapper__.local_table,
        OutcomeLabelSnapshot.__mapper__.local_table,
        Signal.__mapper__.local_table,
        Rule.__mapper__.local_table,
        RuleVersion.__mapper__.local_table,
        OpportunityAction.__mapper__.local_table,
        ActionOutcome.__mapper__.local_table,
    ]
    with engine.connect() as connection:
        for schema in (
            "customer",
            "analytics",
            "signal",
            "rule",
            "feature_store",
            "ml",
            "action",
        ):
            connection.exec_driver_sql(f"ATTACH DATABASE ':memory:' AS '{schema}'")
        for table in tables:
            cast(Table, table).create(connection)
    return sessionmaker(bind=engine, expire_on_commit=False)


def seed_api_data(factory) -> None:
    customer_id = deterministic_uuid("customer", "SME-00125")
    with factory.begin() as session:
        session.add(
            Customer(
                id=customer_id,
                customer_ref="SME-00125",
                legal_name="Synthetic SME 125",
                sector_code="TRADE",
                segment_code="MEDIUM",
                scenario_code="GROWTH",
                incorporated_on=profile().incorporated_on,
                status="ACTIVE",
                rm_id=deterministic_uuid("rm", 1),
            )
        )
        session.add(
            MetricSnapshot(
                id=deterministic_uuid("metric", customer_id, AS_OF, 90),
                customer_id=customer_id,
                as_of_date=AS_OF,
                window_days=90,
                calculation_version="analytics-0.1.0",
                values_json=snapshot().values,
                input_watermark="analytics-snapshot-42",
                created_by="analytics-service",
            )
        )
        session.add(
            ModelRegistry(
                id=deterministic_uuid("model", MODEL_VERSION),
                model_version=MODEL_VERSION,
                score_type="SALES_PROPENSITY",
                algorithm="LOGISTIC_REGRESSION",
                status="ACTIVE",
                feature_set_version=FEATURE_SET_VERSION,
                feature_order_json=list(FEATURE_ORDER),
                coefficients_json=COEFFICIENTS,
                intercept=Decimal("-1.35"),
                threshold=Decimal("0.58"),
                validation_metrics_json={
                    "evaluationMode": "POC_SHADOW",
                    "productionPerformanceClaim": False,
                },
                training_dataset_version="synthetic-demo-20260918-v1",
                training_code_version="manual-baseline-coefficients-v1",
                deployment_mode="POC_ASSISTIVE",
                created_by="unit-test",
            )
        )


def test_internal_materialize_score_batch_model_and_outcome_endpoints(monkeypatch):
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")
    factory = memory_factory()
    seed_api_data(factory)
    feature_app = application_for("feature-store-service")
    feature_app.state.session_factory = factory
    ml_app = application_for("ml-engine-service")
    ml_app.state.session_factory = factory

    feature_client = TestClient(feature_app)
    created = feature_client.post(
        "/internal/v1/features/materialize",
        json={"customerIds": ["SME-00125"], "asOf": AS_OF.isoformat()},
    )
    assert created.status_code == 200
    feature = created.json()["data"][0]
    assert feature["featureSetVersion"] == FEATURE_SET_VERSION
    assert len(feature["checksum"]) == 64

    ml_client = TestClient(ml_app)
    scored = ml_client.post(
        "/internal/v1/ml/customers/SME-00125/score",
        json={"asOf": AS_OF.isoformat()},
    )
    assert scored.status_code == 200
    body = scored.json()
    assert 0.0 <= body["propensity"] <= 1.0
    assert body["modelVersion"] == MODEL_VERSION
    assert body["featureVersion"] == FEATURE_SET_VERSION
    assert len(body["contributions"]) == len(FEATURE_ORDER)
    assert len(body["topFactors"]) == 3

    batch = ml_client.post(
        "/internal/v1/ml/scores/batch",
        json={"customerIds": ["SME-00125"], "asOf": AS_OF.isoformat()},
    )
    assert batch.status_code == 200
    assert batch.json()["data"][0] == body

    registry = ml_client.get("/internal/v1/ml/models/active").json()
    assert registry["status"] == "ACTIVE"
    assert registry["algorithm"] == "LOGISTIC_REGRESSION"
    assert registry["automaticTraining"] is False
    assert registry["deploymentMode"] == "POC_ASSISTIVE"
    assert registry["productionPerformanceClaim"] is False
    assert registry["featureOrder"] == list(FEATURE_ORDER)
    assert body["trainingDatasetVersion"] == "synthetic-demo-20260918-v1"
    assert body["deploymentMode"] == "POC_ASSISTIVE"
    assert body["traceId"]

    outcomes = ml_client.get("/internal/v1/ml/outcomes/snapshots").json()
    assert outcomes["data"] == []
    assert outcomes["meta"]["purpose"] == "FUTURE_LABEL_SNAPSHOT_ONLY"
    assert outcomes["meta"]["automaticTraining"] is False


def test_owned_ml_implementation_has_no_forbidden_phrase():
    root = Path(__file__).parents[2]
    owned = [
        *sorted((root / "backend/src/boa_oi/features").glob("*.py")),
        *sorted((root / "backend/src/boa_oi/ml").glob("*.py")),
        root / "backend/src/boa_oi/feature_store_api.py",
        root / "backend/src/boa_oi/ml_engine_api.py",
        root / "database/migrations/versions/0004_ml_and_portfolio.py",
    ]
    forbidden = "credit" + " risk"
    assert all(forbidden not in path.read_text().lower() for path in owned)
