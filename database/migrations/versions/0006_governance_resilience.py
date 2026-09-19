"""Add governed scoring, resilient fallback, MLOps lineage and monitoring.

Revision ID: 0006_governance_resilience
Revises: 0005_ml_integration_trace
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_governance_resilience"
down_revision = "0005_ml_integration_trace"
branch_labels = None
depends_on = None

POLICY_ID = uuid.UUID("9e6c871a-8dc0-4e66-91a8-06dadcfd6cd0")
POLICY_VERSION_ID = uuid.UUID("4d4f6a12-c905-4c4d-a64a-cd6892fb141d")
POLICY_AUDIT_ID = uuid.UUID("206f8f5c-5aa4-4d87-8ec0-bb01125f2052")


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    opportunity_columns = {
        item["name"] for item in inspector.get_columns("opportunities", schema="opportunity")
    }
    opportunity_additions = (
        sa.Column(
            "scoring_policy_id",
            sa.String(80),
            nullable=False,
            server_default="commercial-hybrid-poc",
        ),
        sa.Column("scoring_policy_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rules_weight", sa.Numeric(8, 6), nullable=False, server_default="0.65"),
        sa.Column("ml_weight", sa.Numeric(8, 6), nullable=False, server_default="0.35"),
        sa.Column("fallback_mode", sa.String(20), nullable=False, server_default="HYBRID_ML"),
        sa.Column("fallback_cause_json", postgresql.JSONB(), nullable=True),
    )
    for column in opportunity_additions:
        if column.name not in opportunity_columns:
            op.add_column("opportunities", column, schema="opportunity")
    opportunity_checks = {
        item["name"]
        for item in inspector.get_check_constraints("opportunities", schema="opportunity")
    }
    if "ck_opportunities_scoring_weights" not in opportunity_checks:
        op.create_check_constraint(
            "ck_opportunities_scoring_weights",
            "opportunities",
            "rules_weight BETWEEN 0 AND 1 AND ml_weight BETWEEN 0 AND 1 "
            "AND rules_weight + ml_weight = 1",
            schema="opportunity",
        )
    if "ck_opportunities_fallback_mode" not in opportunity_checks:
        op.create_check_constraint(
            "ck_opportunities_fallback_mode",
            "opportunities",
            "fallback_mode IN ('HYBRID_ML','RULES_ONLY')",
            schema="opportunity",
        )

    decision_audit_columns = {
        item["name"] for item in inspector.get_columns("decision_audit", schema="opportunity")
    }
    for _name, column in (
        (
            "scoring_policy_id",
            sa.Column(
                "scoring_policy_id",
                sa.String(80),
                nullable=False,
                server_default="commercial-hybrid-poc",
            ),
        ),
        (
            "scoring_policy_version",
            sa.Column("scoring_policy_version", sa.Integer(), nullable=False, server_default="1"),
        ),
        (
            "fallback_mode",
            sa.Column("fallback_mode", sa.String(20), nullable=False, server_default="HYBRID_ML"),
        ),
        (
            "fallback_cause_json",
            sa.Column("fallback_cause_json", postgresql.JSONB(), nullable=True),
        ),
    ):
        if column.name not in decision_audit_columns:
            op.add_column("decision_audit", column, schema="opportunity")

    op.create_table(
        "scoring_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("policy_id", sa.String(80), nullable=False, unique=True),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("active_version", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(120), nullable=False),
        schema="opportunity",
    )
    op.create_table(
        "scoring_policy_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity.scoring_policies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rules_weight", sa.Numeric(8, 6), nullable=False),
        sa.Column("ml_weight", sa.Numeric(8, 6), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("author_id", sa.String(120), nullable=False),
        sa.Column("approver_id", sa.String(120), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_reason", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("simulation_id", sa.String(100), nullable=True),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "policy_id", "version", name="uq_scoring_policy_versions_policy_version"
        ),
        sa.CheckConstraint("rules_weight BETWEEN 0 AND 1", name="ck_scoring_policy_rules_weight"),
        sa.CheckConstraint("ml_weight BETWEEN 0 AND 1", name="ck_scoring_policy_ml_weight"),
        sa.CheckConstraint(
            "rules_weight + ml_weight = 1", name="ck_scoring_policy_normalized_weights"
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','SIMULATED','SUBMITTED','APPROVED','PUBLISHED',"
            "'ACTIVE','DISABLED','ROLLED_BACK')",
            name="ck_scoring_policy_status",
        ),
        schema="opportunity",
    )
    op.create_index(
        "ix_scoring_policy_versions_status",
        "scoring_policy_versions",
        ["status", "effective_from"],
        schema="opportunity",
    )
    op.create_index(
        "uq_scoring_policy_single_active",
        "scoring_policy_versions",
        ["status"],
        unique=True,
        schema="opportunity",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_table(
        "scoring_policy_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity.scoring_policies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("user_id", sa.String(120), nullable=False),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("old_value_json", postgresql.JSONB(), nullable=True),
        sa.Column("new_value_json", postgresql.JSONB(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(100), nullable=False),
        schema="opportunity",
    )
    op.create_index(
        "ix_scoring_policy_audit_policy_time",
        "scoring_policy_audit_logs",
        ["policy_id", "timestamp"],
        schema="opportunity",
    )

    policies = sa.table(
        "scoring_policies",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("policy_id", sa.String()),
        sa.column("current_version", sa.Integer()),
        sa.column("active_version", sa.Integer()),
        sa.column("created_by", sa.String()),
        schema="opportunity",
    )
    versions = sa.table(
        "scoring_policy_versions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("policy_id", postgresql.UUID(as_uuid=True)),
        sa.column("version", sa.Integer()),
        sa.column("rules_weight", sa.Numeric()),
        sa.column("ml_weight", sa.Numeric()),
        sa.column("status", sa.String()),
        sa.column("effective_from", sa.DateTime(timezone=True)),
        sa.column("author_id", sa.String()),
        sa.column("approver_id", sa.String()),
        sa.column("approved_at", sa.DateTime(timezone=True)),
        sa.column("approval_reason", sa.Text()),
        sa.column("reason", sa.Text()),
        sa.column("simulation_id", sa.String()),
        sa.column("checksum", sa.String()),
        schema="opportunity",
    )
    audits = sa.table(
        "scoring_policy_audit_logs",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("policy_id", postgresql.UUID(as_uuid=True)),
        sa.column("policy_version", sa.Integer()),
        sa.column("action", sa.String()),
        sa.column("user_id", sa.String()),
        sa.column("old_value_json", postgresql.JSONB()),
        sa.column("new_value_json", postgresql.JSONB()),
        sa.column("reason", sa.Text()),
        sa.column("trace_id", sa.String()),
        schema="opportunity",
    )
    now = sa.func.now()
    op.execute(
        postgresql.insert(policies).values(
            id=POLICY_ID,
            policy_id="commercial-hybrid-poc",
            current_version=1,
            active_version=1,
            created_by="migration-0006-system-bootstrap",
        )
    )
    op.execute(
        postgresql.insert(versions).values(
            id=POLICY_VERSION_ID,
            policy_id=POLICY_ID,
            version=1,
            rules_weight=0.65,
            ml_weight=0.35,
            status="ACTIVE",
            effective_from=now,
            author_id="migration-0006-system-bootstrap",
            approver_id="migration-0006-system-bootstrap",
            approved_at=now,
            approval_reason="POC bootstrap policy; human governance is required before production.",
            reason="Replace environment-only weights with a versioned assistive POC policy.",
            simulation_id="bootstrap-synthetic-evidence",
            checksum="0fef8fbe976c164b9eca496af3b39fff36cc5e08cca4c471f888540a96c2f07a",
        )
    )
    op.execute(
        postgresql.insert(audits).values(
            id=POLICY_AUDIT_ID,
            policy_id=POLICY_ID,
            policy_version=1,
            action="ACTIVATED",
            user_id="migration-0006-system-bootstrap",
            old_value_json=None,
            new_value_json={"rulesWeight": 0.65, "mlWeight": 0.35, "status": "ACTIVE"},
            reason="POC bootstrap only; not a production approval.",
            trace_id="migration-0006",
        )
    )

    op.add_column(
        "feature_materializations",
        sa.Column(
            "lineage_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        schema="feature_store",
    )

    op.drop_constraint("ck_model_registry_status", "model_registry", schema="ml", type_="check")
    op.create_check_constraint(
        "ck_model_registry_status",
        "model_registry",
        "status IN ('REGISTERED','VALIDATING','SUBMITTED','APPROVED','CHALLENGER',"
        "'CHAMPION','ACTIVE','RETIRED')",
        schema="ml",
    )
    op.add_column(
        "model_registry",
        sa.Column("model_id", sa.String(80), nullable=False, server_default="sales-propensity"),
        schema="ml",
    )
    for _name, column in (
        ("training_period_from", sa.Column("training_period_from", sa.Date(), nullable=True)),
        ("training_period_to", sa.Column("training_period_to", sa.Date(), nullable=True)),
        ("validation_period_from", sa.Column("validation_period_from", sa.Date(), nullable=True)),
        ("validation_period_to", sa.Column("validation_period_to", sa.Date(), nullable=True)),
        (
            "hyperparameters_json",
            sa.Column(
                "hyperparameters_json",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        ),
        ("approved_by", sa.Column("approved_by", sa.String(120), nullable=True)),
        ("approved_at", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)),
        ("retired_at", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True)),
    ):
        op.add_column("model_registry", column, schema="ml")
    op.execute(
        sa.text(
            "UPDATE ml.model_registry SET status='CHAMPION', "
            "approved_by='migration-0006-system-bootstrap', approved_at=now() "
            "WHERE status='ACTIVE'"
        )
    )
    op.create_index(
        "uq_model_registry_single_champion",
        "model_registry",
        ["status"],
        unique=True,
        schema="ml",
        postgresql_where=sa.text("status = 'CHAMPION'"),
    )

    op.add_column(
        "propensity_scores",
        sa.Column(
            "prediction_trace_id", sa.String(100), nullable=False, server_default="legacy-score"
        ),
        schema="ml",
    )

    for _name, column in (
        (
            "dataset_version",
            sa.Column("dataset_version", sa.String(80), nullable=True),
        ),
        ("opportunity_id", sa.Column("opportunity_id", postgresql.UUID(as_uuid=True))),
        ("opportunity_ref", sa.Column("opportunity_ref", sa.String(80))),
        ("opportunity_type", sa.Column("opportunity_type", sa.String(80))),
        ("action_id", sa.Column("action_id", postgresql.UUID(as_uuid=True))),
        ("observed_at", sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True)),
        (
            "source",
            sa.Column("source", sa.String(40), nullable=False, server_default="COMMERCIAL_OUTCOME"),
        ),
    ):
        op.add_column("outcome_label_snapshots", column, schema="ml")
    op.execute(
        sa.text(
            "UPDATE ml.outcome_label_snapshots SET dataset_version=snapshot_version, "
            "observed_at=created_at WHERE dataset_version IS NULL OR observed_at IS NULL"
        )
    )
    op.alter_column("outcome_label_snapshots", "dataset_version", nullable=False, schema="ml")
    op.alter_column("outcome_label_snapshots", "observed_at", nullable=False, schema="ml")
    op.alter_column("outcome_label_snapshots", "outcome_value", nullable=True, schema="ml")

    op.create_table(
        "training_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", sa.String(80), nullable=False),
        sa.Column("model_version", sa.String(40), nullable=False),
        sa.Column("feature_version", sa.String(40), nullable=False),
        sa.Column("dataset_version", sa.String(80), nullable=False),
        sa.Column("training_period_from", sa.Date(), nullable=False),
        sa.Column("training_period_to", sa.Date(), nullable=False),
        sa.Column("validation_period_from", sa.Date(), nullable=False),
        sa.Column("validation_period_to", sa.Date(), nullable=False),
        sa.Column("test_period_from", sa.Date(), nullable=True),
        sa.Column("test_period_to", sa.Date(), nullable=True),
        sa.Column("code_version", sa.String(80), nullable=False),
        sa.Column("hyperparameters_json", postgresql.JSONB(), nullable=False),
        sa.Column("metrics_json", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("approved_by", sa.String(120), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.UniqueConstraint("model_id", "model_version", name="uq_training_runs_model_version"),
        sa.CheckConstraint(
            "status IN ('DRAFT','REGISTERED','VALIDATING','SUBMITTED','APPROVED','CHALLENGER',"
            "'CHAMPION','RETIRED','REJECTED')",
            name="status",
        ),
        schema="ml",
    )
    op.create_table(
        "monitoring_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("domain", sa.String(30), nullable=False),
        sa.Column("metric", sa.String(80), nullable=False),
        sa.Column("value", sa.Numeric(18, 8), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("thresholds_json", postgresql.JSONB(), nullable=False),
        sa.Column("details_json", postgresql.JSONB(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trace_id", sa.String(100), nullable=False),
        schema="ml",
    )
    op.create_index(
        "ix_ml_monitoring_domain_time",
        "monitoring_snapshots",
        ["domain", "observed_at"],
        schema="ml",
    )
    op.create_table(
        "governance_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("user_id", sa.String(120), nullable=False),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("object_type", sa.String(50), nullable=False),
        sa.Column("object_id", sa.String(100), nullable=False),
        sa.Column("object_version", sa.String(80), nullable=False),
        sa.Column("old_value_json", postgresql.JSONB(), nullable=True),
        sa.Column("new_value_json", postgresql.JSONB(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(100), nullable=False),
        schema="ml",
    )
    op.create_index(
        "ix_ml_governance_object_time",
        "governance_audit_logs",
        ["object_type", "object_id", "timestamp"],
        schema="ml",
    )


def downgrade() -> None:
    op.drop_index("ix_ml_governance_object_time", table_name="governance_audit_logs", schema="ml")
    op.drop_table("governance_audit_logs", schema="ml")
    op.drop_index("ix_ml_monitoring_domain_time", table_name="monitoring_snapshots", schema="ml")
    op.drop_table("monitoring_snapshots", schema="ml")
    op.drop_table("training_runs", schema="ml")
    op.execute(sa.text("DELETE FROM ml.outcome_label_snapshots WHERE outcome_value IS NULL"))
    op.alter_column("outcome_label_snapshots", "outcome_value", nullable=False, schema="ml")
    for name in (
        "source",
        "observed_at",
        "action_id",
        "opportunity_type",
        "opportunity_ref",
        "opportunity_id",
        "dataset_version",
    ):
        op.drop_column("outcome_label_snapshots", name, schema="ml")
    op.drop_column("propensity_scores", "prediction_trace_id", schema="ml")
    op.drop_index("uq_model_registry_single_champion", table_name="model_registry", schema="ml")
    for name in (
        "retired_at",
        "approved_at",
        "approved_by",
        "hyperparameters_json",
        "validation_period_to",
        "validation_period_from",
        "training_period_to",
        "training_period_from",
        "model_id",
    ):
        op.drop_column("model_registry", name, schema="ml")
    op.drop_constraint("ck_model_registry_status", "model_registry", schema="ml", type_="check")
    op.execute(
        sa.text(
            "UPDATE ml.model_registry SET status = CASE "
            "WHEN status='CHAMPION' THEN 'ACTIVE' "
            "WHEN status='RETIRED' THEN 'RETIRED' ELSE 'CHALLENGER' END"
        )
    )
    op.create_check_constraint(
        "ck_model_registry_status",
        "model_registry",
        "status IN ('CHALLENGER','ACTIVE','RETIRED')",
        schema="ml",
    )
    op.drop_column("feature_materializations", "lineage_json", schema="feature_store")
    op.drop_index(
        "ix_scoring_policy_audit_policy_time",
        table_name="scoring_policy_audit_logs",
        schema="opportunity",
    )
    op.drop_table("scoring_policy_audit_logs", schema="opportunity")
    op.drop_index(
        "uq_scoring_policy_single_active",
        table_name="scoring_policy_versions",
        schema="opportunity",
    )
    op.drop_index(
        "ix_scoring_policy_versions_status",
        table_name="scoring_policy_versions",
        schema="opportunity",
    )
    op.drop_table("scoring_policy_versions", schema="opportunity")
    op.drop_table("scoring_policies", schema="opportunity")
    for name in (
        "fallback_cause_json",
        "fallback_mode",
        "scoring_policy_version",
        "scoring_policy_id",
    ):
        op.drop_column("decision_audit", name, schema="opportunity")
    op.drop_constraint(
        "ck_opportunities_fallback_mode", "opportunities", schema="opportunity", type_="check"
    )
    op.drop_constraint(
        "ck_opportunities_scoring_weights", "opportunities", schema="opportunity", type_="check"
    )
    for name in (
        "fallback_cause_json",
        "fallback_mode",
        "ml_weight",
        "rules_weight",
        "scoring_policy_version",
        "scoring_policy_id",
    ):
        op.drop_column("opportunities", name, schema="opportunity")
