"""Lock ML to governed shadow mode and persist defensible evaluation lineage.

Revision ID: 0017_ml_shadow_governance
Revises: 0016_ingestion_governance
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017_ml_shadow_governance"
down_revision = "0016_ingestion_governance"
branch_labels = None
depends_on = None

RULES_ONLY_POLICY_CHECKSUM = "08416e02224d35ce84e62e59b24c9b993891a7af27ee90d353125c6547ace44e"


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE ml.model_registry SET deployment_mode='POC_SHADOW' "
            "WHERE deployment_mode <> 'POC_SHADOW'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE ml.model_registry SET validation_metrics_json = "
            "validation_metrics_json || jsonb_build_object("
            "'evaluationMode','POC_SHADOW',"
            "'productionPerformanceClaim',false,"
            "'calibrationStatus','NOT_VALIDATED')"
        )
    )
    op.drop_constraint(
        "ck_model_registry_deployment_mode",
        "model_registry",
        schema="ml",
        type_="check",
    )
    op.create_check_constraint(
        "ck_model_registry_deployment_mode",
        "model_registry",
        "deployment_mode = 'POC_SHADOW'",
        schema="ml",
    )
    op.alter_column(
        "model_registry",
        "deployment_mode",
        schema="ml",
        server_default="POC_SHADOW",
    )
    for column in (
        sa.Column(
            "target_outcome",
            sa.String(80),
            nullable=False,
            server_default="ANY_COMMERCIAL_OPPORTUNITY",
        ),
        sa.Column("horizon_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column(
            "score_interpretation",
            sa.String(30),
            nullable=False,
            server_default="RANKING_ONLY",
        ),
        sa.Column(
            "calibration_status",
            sa.String(30),
            nullable=False,
            server_default="NOT_VALIDATED",
        ),
        sa.Column("dataset_manifest_hash", sa.String(64), nullable=True),
        sa.Column("artifact_checksum", sa.String(64), nullable=True),
        sa.Column("contract_version", sa.String(20), nullable=False, server_default="1.0"),
    ):
        op.add_column("model_registry", column, schema="ml")
    op.create_check_constraint(
        "ck_model_registry_score_interpretation",
        "model_registry",
        "score_interpretation = 'RANKING_ONLY'",
        schema="ml",
    )
    op.create_check_constraint(
        "ck_model_registry_calibration_status",
        "model_registry",
        "calibration_status IN ('NOT_VALIDATED','VALIDATED')",
        schema="ml",
    )

    op.execute(
        sa.text(
            "UPDATE ml.propensity_scores SET deployment_mode='POC_SHADOW' "
            "WHERE deployment_mode <> 'POC_SHADOW'"
        )
    )
    op.drop_constraint(
        "ck_propensity_scores_deployment_mode",
        "propensity_scores",
        schema="ml",
        type_="check",
    )
    op.create_check_constraint(
        "ck_propensity_scores_deployment_mode",
        "propensity_scores",
        "deployment_mode = 'POC_SHADOW'",
        schema="ml",
    )
    op.alter_column(
        "propensity_scores",
        "deployment_mode",
        schema="ml",
        server_default="POC_SHADOW",
    )
    op.drop_constraint(
        "ck_propensity_scores_calibration",
        "propensity_scores",
        schema="ml",
        type_="check",
    )
    op.alter_column(
        "propensity_scores",
        "calibration",
        new_column_name="score_band",
        schema="ml",
        existing_type=sa.String(20),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_propensity_scores_score_band",
        "propensity_scores",
        "score_band IN ('LOW','MEDIUM','HIGH')",
        schema="ml",
    )
    for column in (
        sa.Column(
            "target_outcome",
            sa.String(80),
            nullable=False,
            server_default="ANY_COMMERCIAL_OPPORTUNITY",
        ),
        sa.Column("horizon_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column(
            "opportunity_type",
            sa.String(80),
            nullable=False,
            server_default="ANY_COMMERCIAL_OPPORTUNITY",
        ),
        sa.Column(
            "score_interpretation",
            sa.String(30),
            nullable=False,
            server_default="RANKING_ONLY",
        ),
        sa.Column("feature_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("feature_watermark", sa.String(120), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("contract_version", sa.String(20), nullable=False, server_default="1.0"),
        sa.Column("dataset_manifest_hash", sa.String(64), nullable=True),
        sa.Column("artifact_checksum", sa.String(64), nullable=True),
    ):
        op.add_column("propensity_scores", column, schema="ml")
    op.execute(sa.text("UPDATE ml.propensity_scores SET valid_until=as_of_date"))
    op.create_check_constraint(
        "ck_propensity_scores_interpretation",
        "propensity_scores",
        "score_interpretation = 'RANKING_ONLY'",
        schema="ml",
    )

    op.drop_constraint(
        "uq_outcome_labels_snapshot_customer_time",
        "outcome_label_snapshots",
        schema="ml",
        type_="unique",
    )
    for column in (
        sa.Column(
            "label_definition_version",
            sa.String(80),
            nullable=False,
            server_default="legacy-unversioned",
        ),
        sa.Column(
            "target_outcome",
            sa.String(80),
            nullable=False,
            server_default="ANY_COMMERCIAL_OPPORTUNITY",
        ),
        sa.Column("horizon_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column(
            "population_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "source_kind",
            sa.String(40),
            nullable=False,
            server_default="LOCAL_COMMERCIAL_OUTCOME",
        ),
        sa.Column("window_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("candidate_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("feature_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("feature_checksum", sa.String(64), nullable=True),
        sa.Column("dataset_manifest_hash", sa.String(64), nullable=True),
    ):
        op.add_column("outcome_label_snapshots", column, schema="ml")
    op.create_unique_constraint(
        "uq_outcome_labels_definition_customer_time",
        "outcome_label_snapshots",
        (
            "snapshot_version",
            "label_definition_version",
            "customer_id",
            "observation_as_of",
            "label_available_from",
        ),
        schema="ml",
    )
    op.create_check_constraint(
        "ck_outcome_labels_source_kind",
        "outcome_label_snapshots",
        "source_kind IN ('LOCAL_COMMERCIAL_OUTCOME','BOA_HISTORICAL_OBSERVED','SYNTHETIC')",
        schema="ml",
    )
    op.create_check_constraint(
        "ck_outcome_labels_candidate_guard",
        "outcome_label_snapshots",
        "source_kind = 'BOA_HISTORICAL_OBSERVED' OR candidate_only",
        schema="ml",
    )

    for column in (
        sa.Column(
            "deployment_mode",
            sa.String(20),
            nullable=False,
            server_default="POC_SHADOW",
        ),
        sa.Column("dataset_manifest_hash", sa.String(64), nullable=True),
        sa.Column(
            "activation_gate_status",
            sa.String(30),
            nullable=False,
            server_default="BLOCKED",
        ),
        sa.Column("artifact_checksum", sa.String(64), nullable=True),
    ):
        op.add_column("training_runs", column, schema="ml")
    op.create_check_constraint(
        "ck_training_runs_deployment_mode",
        "training_runs",
        "deployment_mode = 'POC_SHADOW'",
        schema="ml",
    )
    op.create_check_constraint(
        "ck_training_runs_activation_gate",
        "training_runs",
        "activation_gate_status IN ('BLOCKED','ELIGIBLE')",
        schema="ml",
    )

    op.create_table(
        "dataset_manifests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("manifest_version", sa.String(80), nullable=False, unique=True),
        sa.Column("source_kind", sa.String(40), nullable=False),
        sa.Column("purpose", sa.String(60), nullable=False),
        sa.Column("target_outcome", sa.String(80), nullable=False),
        sa.Column("label_definition_version", sa.String(80), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("population_json", postgresql.JSONB(), nullable=False),
        sa.Column("exclusions_json", postgresql.JSONB(), nullable=False),
        sa.Column("training_cutoff", sa.Date(), nullable=False),
        sa.Column("feature_snapshot_ids_json", postgresql.JSONB(), nullable=False),
        sa.Column("label_snapshot_ids_json", postgresql.JSONB(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("blockers_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.CheckConstraint(
            "source_kind IN ('LOCAL_COMMERCIAL_OUTCOME','BOA_HISTORICAL_OBSERVED','SYNTHETIC')",
            name="ck_dataset_manifests_source_kind",
        ),
        sa.CheckConstraint(
            "status IN ('BLOCKED','CANDIDATE','VALIDATED')",
            name="ck_dataset_manifests_status",
        ),
        sa.CheckConstraint("row_count >= 0", name="ck_dataset_manifests_row_count"),
        sa.CheckConstraint("horizon_days > 0", name="ck_dataset_manifests_horizon"),
        schema="ml",
    )
    op.create_index(
        "ix_dataset_manifests_status_created",
        "dataset_manifests",
        ["status", "created_at"],
        schema="ml",
    )

    op.create_table(
        "evaluation_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("evaluation_ref", sa.String(100), nullable=False, unique=True),
        sa.Column("model_version", sa.String(40), nullable=False),
        sa.Column("dataset_manifest_hash", sa.String(64), nullable=False),
        sa.Column("source_kind", sa.String(40), nullable=False),
        sa.Column("evaluation_period_from", sa.Date(), nullable=False),
        sa.Column("evaluation_period_to", sa.Date(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("positive_count", sa.Integer(), nullable=False),
        sa.Column("negative_count", sa.Integer(), nullable=False),
        sa.Column("metrics_json", postgresql.JSONB(), nullable=False),
        sa.Column("calibration_json", postgresql.JSONB(), nullable=False),
        sa.Column("acceptance_criteria_json", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("blockers_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.CheckConstraint(
            "status IN ('BLOCKED','NOT_VALIDATED','VALIDATED')",
            name="ck_evaluation_snapshots_status",
        ),
        sa.CheckConstraint(
            "sample_count >= 0 AND positive_count >= 0 AND negative_count >= 0",
            name="ck_evaluation_snapshots_counts",
        ),
        sa.CheckConstraint(
            "evaluation_period_to >= evaluation_period_from",
            name="ck_evaluation_snapshots_period",
        ),
        schema="ml",
    )
    op.create_index(
        "ix_evaluation_snapshots_model_created",
        "evaluation_snapshots",
        ["model_version", "created_at"],
        schema="ml",
    )

    op.create_table(
        "_0017_opportunity_backup",
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scoring_policy_id", sa.String(80), nullable=False),
        sa.Column("rules_weight", sa.Numeric(8, 6), nullable=False),
        sa.Column("ml_weight", sa.Numeric(8, 6), nullable=False),
        sa.Column("fallback_mode", sa.String(30), nullable=False),
        sa.Column("priority_score", sa.Numeric(8, 4), nullable=False),
        sa.Column("priority_level", sa.String(10), nullable=False),
        sa.Column("priority_components_json", postgresql.JSONB(), nullable=False),
        sa.Column("explanation_json", postgresql.JSONB(), nullable=False),
        sa.Column("engine_version", sa.String(80), nullable=False),
        schema="opportunity",
    )
    op.execute(
        sa.text(
            "INSERT INTO opportunity._0017_opportunity_backup "
            "SELECT id, scoring_policy_id, rules_weight, ml_weight, fallback_mode, "
            "priority_score, priority_level, priority_components_json::jsonb, "
            "explanation_json::jsonb, engine_version FROM opportunity.opportunities"
        )
    )
    op.create_table(
        "_0017_policy_backup",
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_policy_id", sa.String(80), nullable=False),
        schema="opportunity",
    )
    op.execute(
        sa.text(
            "INSERT INTO opportunity._0017_policy_backup "
            "SELECT id, policy_id FROM opportunity.scoring_policies"
        )
    )
    op.create_table(
        "_0017_policy_version_backup",
        sa.Column("policy_version_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rules_weight", sa.Numeric(8, 6), nullable=False),
        sa.Column("ml_weight", sa.Numeric(8, 6), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        schema="opportunity",
    )
    op.execute(
        sa.text(
            "INSERT INTO opportunity._0017_policy_version_backup "
            "SELECT id, rules_weight, ml_weight, checksum "
            "FROM opportunity.scoring_policy_versions"
        )
    )
    op.execute(
        sa.text(
            "UPDATE opportunity.scoring_policy_versions SET rules_weight=1, ml_weight=0, "
            "checksum=:checksum WHERE status='ACTIVE'"
        ).bindparams(checksum=RULES_ONLY_POLICY_CHECKSUM)
    )
    op.execute(
        sa.text(
            "UPDATE opportunity.scoring_policies SET policy_id='commercial-rules-shadow-poc' "
            "WHERE policy_id='commercial-hybrid-poc'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE opportunity.opportunities SET "
            "scoring_policy_id='commercial-rules-shadow-poc', rules_weight=1, ml_weight=0, "
            "fallback_mode='RULES_ONLY'"
        )
    )
    op.execute(
        sa.text(
            "WITH rules AS ("
            " SELECT o.id,"
            " coalesce(sum(CASE"
            "   WHEN component ? 'contribution' THEN (component->>'contribution')::numeric"
            "   WHEN component ? 'weighted_value' THEN"
            "     (component->>'weighted_value')::numeric * 100"
            "   ELSE 0 END), 0) AS rules_score,"
            " coalesce(jsonb_agg(component) FILTER "
            "   (WHERE component->>'name' <> 'sales_propensity_ml'), '[]'::jsonb) AS components"
            " FROM opportunity.opportunities o"
            " LEFT JOIN LATERAL jsonb_array_elements(o.priority_components_json::jsonb)"
            "   AS component ON true"
            " WHERE o.engine_version LIKE '%ml-rerank-poc-v1%'"
            "   AND coalesce(component->>'name','') <> 'sales_propensity_ml'"
            " GROUP BY o.id"
            ") UPDATE opportunity.opportunities o SET"
            " priority_score=least(100, greatest(0, rules.rules_score)),"
            " priority_level=CASE"
            "   WHEN rules.rules_score >= 80 THEN 'P1'"
            "   WHEN rules.rules_score >= 60 THEN 'P2'"
            "   WHEN rules.rules_score >= 40 THEN 'P3' ELSE 'P4' END,"
            " priority_components_json=rules.components,"
            " engine_version=replace(o.engine_version, '+ml-rerank-poc-v1', '') || '+rules-only',"
            " explanation_json=(o.explanation_json::jsonb - 'propensity' - 'combination')"
            "   || jsonb_build_object('propensityShadow', o.explanation_json::jsonb->'propensity')"
            "   || jsonb_build_object('combination',"
            "      coalesce(o.explanation_json::jsonb->'combination','{}'::jsonb)"
            "      || jsonb_build_object("
            "        'method','RULES_ONLY','mlObservationMode','POC_SHADOW',"
            "        'mlWeight',0,'rulesWeight',1,'shadowReadOnly',true))"
            " FROM rules WHERE o.id=rules.id"
        )
    )
    op.create_check_constraint(
        "ck_scoring_policy_active_shadow_only",
        "scoring_policy_versions",
        "status <> 'ACTIVE' OR (rules_weight = 1 AND ml_weight = 0)",
        schema="opportunity",
    )
    op.create_check_constraint(
        "ck_scoring_policy_effective_window",
        "scoring_policy_versions",
        "effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from",
        schema="opportunity",
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_scoring_policy_single_active "
            "ON opportunity.scoring_policy_versions (status) WHERE status = 'ACTIVE'"
        )
    )
    op.create_check_constraint(
        "ck_opportunities_shadow_operational",
        "opportunities",
        "rules_weight = 1 AND ml_weight = 0 AND fallback_mode = 'RULES_ONLY'",
        schema="opportunity",
    )
    op.alter_column(
        "opportunities",
        "scoring_policy_id",
        schema="opportunity",
        server_default="commercial-rules-shadow-poc",
    )
    op.alter_column("opportunities", "rules_weight", schema="opportunity", server_default="1")
    op.alter_column("opportunities", "ml_weight", schema="opportunity", server_default="0")
    op.alter_column(
        "opportunities", "fallback_mode", schema="opportunity", server_default="RULES_ONLY"
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS opportunity.uq_scoring_policy_single_active"))
    op.drop_constraint(
        "ck_scoring_policy_effective_window",
        "scoring_policy_versions",
        schema="opportunity",
        type_="check",
    )
    op.drop_constraint(
        "ck_opportunities_shadow_operational", "opportunities", schema="opportunity", type_="check"
    )
    op.drop_constraint(
        "ck_scoring_policy_active_shadow_only",
        "scoring_policy_versions",
        schema="opportunity",
        type_="check",
    )
    op.execute(
        sa.text(
            "UPDATE opportunity.opportunities o SET "
            "scoring_policy_id=b.scoring_policy_id, rules_weight=b.rules_weight, "
            "ml_weight=b.ml_weight, fallback_mode=b.fallback_mode, "
            "priority_score=b.priority_score, priority_level=b.priority_level, "
            "priority_components_json=b.priority_components_json, "
            "explanation_json=b.explanation_json, engine_version=b.engine_version "
            "FROM opportunity._0017_opportunity_backup b WHERE o.id=b.opportunity_id"
        )
    )
    op.execute(
        sa.text(
            "UPDATE opportunity.scoring_policy_versions v SET "
            "rules_weight=b.rules_weight, ml_weight=b.ml_weight, checksum=b.checksum "
            "FROM opportunity._0017_policy_version_backup b WHERE v.id=b.policy_version_id"
        )
    )
    op.execute(
        sa.text(
            "UPDATE opportunity.scoring_policies p SET policy_id=b.external_policy_id "
            "FROM opportunity._0017_policy_backup b WHERE p.id=b.policy_id"
        )
    )
    op.drop_table("_0017_policy_version_backup", schema="opportunity")
    op.drop_table("_0017_policy_backup", schema="opportunity")
    op.drop_table("_0017_opportunity_backup", schema="opportunity")
    op.alter_column(
        "opportunities", "fallback_mode", schema="opportunity", server_default="HYBRID_ML"
    )
    op.alter_column("opportunities", "ml_weight", schema="opportunity", server_default="0.35")
    op.alter_column("opportunities", "rules_weight", schema="opportunity", server_default="0.65")
    op.alter_column(
        "opportunities",
        "scoring_policy_id",
        schema="opportunity",
        server_default="commercial-hybrid-poc",
    )
    op.drop_table("evaluation_snapshots", schema="ml")
    op.drop_table("dataset_manifests", schema="ml")
    op.drop_constraint(
        "ck_training_runs_activation_gate", "training_runs", schema="ml", type_="check"
    )
    op.drop_constraint(
        "ck_training_runs_deployment_mode", "training_runs", schema="ml", type_="check"
    )
    for column in (
        "artifact_checksum",
        "activation_gate_status",
        "dataset_manifest_hash",
        "deployment_mode",
    ):
        op.drop_column("training_runs", column, schema="ml")
    op.drop_constraint(
        "ck_outcome_labels_candidate_guard",
        "outcome_label_snapshots",
        schema="ml",
        type_="check",
    )
    op.drop_constraint(
        "ck_outcome_labels_source_kind",
        "outcome_label_snapshots",
        schema="ml",
        type_="check",
    )
    op.drop_constraint(
        "uq_outcome_labels_definition_customer_time",
        "outcome_label_snapshots",
        schema="ml",
        type_="unique",
    )
    for column in (
        "dataset_manifest_hash",
        "feature_checksum",
        "feature_snapshot_id",
        "candidate_only",
        "window_closed",
        "source_kind",
        "population_json",
        "horizon_days",
        "target_outcome",
        "label_definition_version",
    ):
        op.drop_column("outcome_label_snapshots", column, schema="ml")
    op.create_unique_constraint(
        "uq_outcome_labels_snapshot_customer_time",
        "outcome_label_snapshots",
        ("snapshot_version", "customer_id", "observation_as_of", "label_available_from"),
        schema="ml",
    )
    op.drop_constraint(
        "ck_propensity_scores_interpretation",
        "propensity_scores",
        schema="ml",
        type_="check",
    )
    for column in (
        "artifact_checksum",
        "dataset_manifest_hash",
        "contract_version",
        "valid_until",
        "feature_watermark",
        "feature_snapshot_id",
        "score_interpretation",
        "opportunity_type",
        "horizon_days",
        "target_outcome",
    ):
        op.drop_column("propensity_scores", column, schema="ml")
    op.drop_constraint(
        "ck_propensity_scores_score_band",
        "propensity_scores",
        schema="ml",
        type_="check",
    )
    op.alter_column(
        "propensity_scores",
        "score_band",
        new_column_name="calibration",
        schema="ml",
        existing_type=sa.String(20),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_propensity_scores_calibration",
        "propensity_scores",
        "calibration IN ('LOW','MEDIUM','HIGH')",
        schema="ml",
    )
    op.drop_constraint(
        "ck_propensity_scores_deployment_mode",
        "propensity_scores",
        schema="ml",
        type_="check",
    )
    op.create_check_constraint(
        "ck_propensity_scores_deployment_mode",
        "propensity_scores",
        "deployment_mode IN ('POC_SHADOW','POC_ASSISTIVE','PRODUCTION')",
        schema="ml",
    )
    op.drop_constraint(
        "ck_model_registry_calibration_status", "model_registry", schema="ml", type_="check"
    )
    op.drop_constraint(
        "ck_model_registry_score_interpretation", "model_registry", schema="ml", type_="check"
    )
    for column in (
        "contract_version",
        "artifact_checksum",
        "dataset_manifest_hash",
        "calibration_status",
        "score_interpretation",
        "horizon_days",
        "target_outcome",
    ):
        op.drop_column("model_registry", column, schema="ml")
    op.drop_constraint(
        "ck_model_registry_deployment_mode", "model_registry", schema="ml", type_="check"
    )
    op.create_check_constraint(
        "ck_model_registry_deployment_mode",
        "model_registry",
        "deployment_mode IN ('POC_SHADOW','POC_ASSISTIVE','PRODUCTION')",
        schema="ml",
    )
