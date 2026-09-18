"""Add versioned feature materializations and explainable sales propensity ML."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_ml_and_portfolio"
down_revision = "0003_rule_studio"
branch_labels = None
depends_on = None

MODEL_VERSION = "sales-propensity-logit-poc-v1"
FEATURE_SET_VERSION = "sales-features-v2"
MODEL_ID = uuid.UUID("ff12c33f-50e8-5c81-8369-70f9e48e1480")
FEATURE_ORDER = (
    "cash_inflow_growth_90d",
    "supplier_payment_growth_90d",
    "international_activity_ratio_90d",
    "balance_strength_90d",
    "activity_density_90d",
    "analytics_coverage_90d",
    "customer_tenure_ratio",
    "segment_medium",
    "confirmed_signal_ratio",
    "published_rule_match_strength",
)
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
VALIDATION_METRICS = {
    "evaluationMode": "POC_SHADOW",
    "datasetKind": "SYNTHETIC",
    "validationStatus": "NOT_PRODUCTION_VALIDATED",
    "productionPerformanceClaim": False,
}


def upgrade() -> None:
    op.execute(sa.text('CREATE SCHEMA IF NOT EXISTS "feature_store"'))
    op.execute(sa.text('CREATE SCHEMA IF NOT EXISTS "ml"'))

    op.create_table(
        "feature_materializations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_ref", sa.String(40), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("feature_set_version", sa.String(40), nullable=False),
        sa.Column("values_json", postgresql.JSONB(), nullable=False),
        sa.Column("sources_json", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.UniqueConstraint(
            "customer_id",
            "as_of_date",
            "feature_set_version",
            name="uq_feature_materializations_customer_as_of_version",
        ),
        sa.CheckConstraint("char_length(checksum) = 64", name="ck_feature_checksum_sha256"),
        schema="feature_store",
    )
    op.create_index(
        "ix_feature_materializations_customer_as_of",
        "feature_materializations",
        ["customer_id", "as_of_date"],
        schema="feature_store",
    )

    op.create_table(
        "model_registry",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_version", sa.String(40), nullable=False, unique=True),
        sa.Column(
            "score_type",
            sa.String(40),
            nullable=False,
            server_default="SALES_PROPENSITY",
        ),
        sa.Column(
            "algorithm",
            sa.String(40),
            nullable=False,
            server_default="LOGISTIC_REGRESSION",
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("feature_set_version", sa.String(40), nullable=False),
        sa.Column("feature_order_json", postgresql.JSONB(), nullable=False),
        sa.Column("coefficients_json", postgresql.JSONB(), nullable=False),
        sa.Column("intercept", sa.Numeric(18, 10), nullable=False),
        sa.Column("threshold", sa.Numeric(8, 6), nullable=False),
        sa.Column("validation_metrics_json", postgresql.JSONB(), nullable=False),
        sa.Column("training_dataset_version", sa.String(80), nullable=False),
        sa.Column("training_code_version", sa.String(80), nullable=False),
        sa.Column("deployment_mode", sa.String(20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.CheckConstraint(
            "status IN ('CHALLENGER','ACTIVE','RETIRED')",
            name="ck_model_registry_status",
        ),
        sa.CheckConstraint(
            "score_type = 'SALES_PROPENSITY'",
            name="ck_model_registry_score_type",
        ),
        sa.CheckConstraint(
            "algorithm = 'LOGISTIC_REGRESSION'",
            name="ck_model_registry_algorithm",
        ),
        sa.CheckConstraint(
            "threshold BETWEEN 0 AND 1",
            name="ck_model_registry_threshold",
        ),
        sa.CheckConstraint(
            "deployment_mode IN ('POC_SHADOW','POC_ASSISTIVE','PRODUCTION')",
            name="ck_model_registry_deployment_mode",
        ),
        schema="ml",
    )
    op.create_index("ix_model_registry_status", "model_registry", ["status"], schema="ml")
    op.create_index(
        "uq_model_registry_single_active",
        "model_registry",
        ["status"],
        unique=True,
        schema="ml",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "propensity_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_ref", sa.String(40), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column(
            "score_type",
            sa.String(40),
            nullable=False,
            server_default="SALES_PROPENSITY",
        ),
        sa.Column("score", sa.Numeric(12, 10), nullable=False),
        sa.Column("threshold", sa.Numeric(8, 6), nullable=False),
        sa.Column("above_threshold", sa.Boolean(), nullable=False),
        sa.Column("calibration", sa.String(20), nullable=False),
        sa.Column("segment", sa.String(20), nullable=False),
        sa.Column("model_version", sa.String(40), nullable=False),
        sa.Column("feature_set_version", sa.String(40), nullable=False),
        sa.Column("feature_checksum", sa.String(64), nullable=False),
        sa.Column("contributions_json", postgresql.JSONB(), nullable=False),
        sa.Column("top_factors_json", postgresql.JSONB(), nullable=False),
        sa.Column("training_dataset_version", sa.String(80), nullable=False),
        sa.Column("deployment_mode", sa.String(20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.UniqueConstraint(
            "customer_id",
            "as_of_date",
            "model_version",
            "feature_checksum",
            name="uq_propensity_scores_reproducible_input",
        ),
        sa.CheckConstraint(
            "score_type = 'SALES_PROPENSITY'",
            name="ck_propensity_scores_score_type",
        ),
        sa.CheckConstraint("score BETWEEN 0 AND 1", name="ck_propensity_scores_score"),
        sa.CheckConstraint(
            "threshold BETWEEN 0 AND 1", name="ck_propensity_scores_threshold"
        ),
        sa.CheckConstraint(
            "calibration IN ('LOW','MEDIUM','HIGH')",
            name="ck_propensity_scores_calibration",
        ),
        sa.CheckConstraint(
            "deployment_mode IN ('POC_SHADOW','POC_ASSISTIVE','PRODUCTION')",
            name="ck_propensity_scores_deployment_mode",
        ),
        schema="ml",
    )
    op.create_index(
        "ix_propensity_scores_customer_as_of",
        "propensity_scores",
        ["customer_id", "as_of_date"],
        schema="ml",
    )

    op.create_table(
        "outcome_label_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_version", sa.String(40), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_ref", sa.String(40), nullable=False),
        sa.Column(
            "score_type",
            sa.String(40),
            nullable=False,
            server_default="SALES_PROPENSITY",
        ),
        sa.Column("observation_as_of", sa.Date(), nullable=False),
        sa.Column("label_available_from", sa.Date(), nullable=False),
        sa.Column("outcome_label", sa.String(80), nullable=False),
        sa.Column("outcome_value", sa.Boolean(), nullable=False),
        sa.Column("source_reference", sa.String(120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "snapshot_version",
            "customer_id",
            "observation_as_of",
            "label_available_from",
            name="uq_outcome_labels_snapshot_customer_time",
        ),
        sa.CheckConstraint(
            "score_type = 'SALES_PROPENSITY'",
            name="ck_outcome_labels_score_type",
        ),
        sa.CheckConstraint(
            "label_available_from > observation_as_of",
            name="ck_outcome_labels_future_only",
        ),
        schema="ml",
    )
    op.create_index(
        "ix_outcome_labels_snapshot_available",
        "outcome_label_snapshots",
        ["snapshot_version", "label_available_from"],
        schema="ml",
    )

    model_registry = sa.table(
        "model_registry",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("model_version", sa.String()),
        sa.column("score_type", sa.String()),
        sa.column("algorithm", sa.String()),
        sa.column("status", sa.String()),
        sa.column("feature_set_version", sa.String()),
        sa.column("feature_order_json", postgresql.JSONB()),
        sa.column("coefficients_json", postgresql.JSONB()),
        sa.column("intercept", sa.Numeric()),
        sa.column("threshold", sa.Numeric()),
        sa.column("validation_metrics_json", postgresql.JSONB()),
        sa.column("training_dataset_version", sa.String()),
        sa.column("training_code_version", sa.String()),
        sa.column("deployment_mode", sa.String()),
        sa.column("created_by", sa.String()),
        schema="ml",
    )
    insert = postgresql.insert(model_registry).values(
        id=MODEL_ID,
        model_version=MODEL_VERSION,
        score_type="SALES_PROPENSITY",
        algorithm="LOGISTIC_REGRESSION",
        status="ACTIVE",
        feature_set_version=FEATURE_SET_VERSION,
        feature_order_json=list(FEATURE_ORDER),
        coefficients_json=COEFFICIENTS,
        intercept=-1.35,
        threshold=0.58,
        validation_metrics_json=VALIDATION_METRICS,
        training_dataset_version="synthetic-demo-20260918-v1",
        training_code_version="manual-baseline-coefficients-v1",
        deployment_mode="POC_ASSISTIVE",
        created_by="migration-0004",
    )
    op.execute(insert.on_conflict_do_nothing(index_elements=["model_version"]))


def downgrade() -> None:
    op.drop_table("outcome_label_snapshots", schema="ml")
    op.drop_table("propensity_scores", schema="ml")
    op.drop_table("model_registry", schema="ml")
    op.drop_table("feature_materializations", schema="feature_store")
    op.execute(sa.text('DROP SCHEMA IF EXISTS "ml"'))
    op.execute(sa.text('DROP SCHEMA IF EXISTS "feature_store"'))
