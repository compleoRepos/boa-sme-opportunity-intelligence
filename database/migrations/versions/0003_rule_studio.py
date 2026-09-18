"""Create the versioned Rule Studio persistence model."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_rule_studio"
down_revision = "0002_service_api_persistence"
branch_labels = None
depends_on = None

STATUS = (
    "status IN ('DRAFT','VALIDATED','SIMULATED','SUBMITTED','APPROVED',"
    "'PUBLISHED','ACTIVE','DISABLED','RETIRED')"
)


def upgrade() -> None:
    op.execute(sa.text('CREATE SCHEMA IF NOT EXISTS "rule"'))
    op.create_table(
        "rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rule_id", sa.String(80), nullable=False, unique=True),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("active_version", sa.Integer(), nullable=True),
        sa.Column("disabled_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.CheckConstraint("current_version > 0", name="ck_rules_positive_current_version"),
        sa.CheckConstraint(STATUS, name="ck_rules_status"),
        schema="rule",
    )
    op.create_index("ix_rules_status_updated", "rules", ["status", "updated_at"], schema="rule")
    op.create_table(
        "rule_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rule.rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "scope_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("logic", sa.String(10), nullable=False, server_default="AND"),
        sa.Column("configuration_json", postgresql.JSONB(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.UniqueConstraint("rule_id", "version", name="uq_rule_versions_rule_id"),
        sa.CheckConstraint("version > 0", name="ck_rule_versions_positive_version"),
        sa.CheckConstraint(STATUS, name="ck_rule_versions_status"),
        schema="rule",
    )
    op.create_index(
        "ix_rule_versions_rule_status", "rule_versions", ["rule_id", "status"], schema="rule"
    )
    op.create_table(
        "rule_conditions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "rule_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rule.rule_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_condition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rule.rule_conditions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("path", sa.String(240), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("node_type", sa.String(20), nullable=False),
        sa.Column("logic", sa.String(10), nullable=True),
        sa.Column("metric_code", sa.String(80), nullable=True),
        sa.Column("operator", sa.String(30), nullable=True),
        sa.Column("value_json", postgresql.JSONB(), nullable=True),
        sa.Column("unit", sa.String(30), nullable=True),
        sa.Column("period", sa.String(30), nullable=True),
        sa.UniqueConstraint("rule_version_id", "path", name="uq_rule_conditions_version_path"),
        sa.CheckConstraint(
            "node_type IN ('GROUP','CONDITION')", name="ck_rule_conditions_node_type"
        ),
        schema="rule",
    )
    op.create_index(
        "ix_rule_conditions_version_position",
        "rule_conditions",
        ["rule_version_id", "position"],
        schema="rule",
    )
    op.create_table(
        "rule_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "rule_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rule.rule_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("opportunity_type_code", sa.String(80), nullable=False),
        sa.Column(
            "product_codes_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("horizon_code", sa.String(30), nullable=True),
        sa.UniqueConstraint("rule_version_id", "position", name="uq_rule_actions_version_position"),
        schema="rule",
    )
    op.create_table(
        "rule_confidence_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "rule_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rule.rule_versions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("base_score", sa.Numeric(8, 6), nullable=False, server_default="0"),
        sa.Column(
            "weights_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            "base_score BETWEEN 0 AND 1", name="ck_rule_confidence_configurations_base_score_range"
        ),
        schema="rule",
    )
    op.create_table(
        "rule_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "rule_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rule.rule_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("actor_subject_id", sa.String(120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "decided_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "rule_version_id", "decision", name="uq_rule_approvals_version_decision"
        ),
        sa.CheckConstraint(
            "decision IN ('SUBMITTED','APPROVED','REJECTED')", name="ck_rule_approvals_decision"
        ),
        schema="rule",
    )
    op.create_table(
        "rule_simulations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "rule_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rule.rule_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column(
            "population_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("result_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.CheckConstraint("period_from <= period_to", name="ck_rule_simulations_period"),
        schema="rule",
    )
    op.create_index(
        "ix_rule_simulations_version_created",
        "rule_simulations",
        ["rule_version_id", "created_at"],
        schema="rule",
    )
    op.create_table(
        "rule_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rule.rules.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("user_id", sa.String(120), nullable=False),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("old_value_json", postgresql.JSONB(), nullable=True),
        sa.Column("new_value_json", postgresql.JSONB(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "action IN ('CREATED','UPDATED','VALIDATED','SIMULATED','SUBMITTED','APPROVED',"
            "'PUBLISHED','ACTIVATED','DISABLED','RETIRED','ROLLED_BACK')",
            name="ck_rule_audit_logs_action",
        ),
        schema="rule",
    )
    op.create_index(
        "ix_rule_audit_rule_time", "rule_audit_logs", ["rule_id", "timestamp"], schema="rule"
    )
    op.execute(
        sa.text(
            "CREATE OR REPLACE FUNCTION rule.prevent_rule_audit_mutation() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION "
            "'rule_audit_logs is append-only'; END; $$"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER rule_audit_immutable BEFORE UPDATE OR DELETE ON rule.rule_audit_logs "
            "FOR EACH ROW EXECUTE FUNCTION rule.prevent_rule_audit_mutation()"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS rule_audit_immutable ON rule.rule_audit_logs"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS rule.prevent_rule_audit_mutation()"))
    for table in (
        "rule_audit_logs",
        "rule_simulations",
        "rule_approvals",
        "rule_confidence_configurations",
        "rule_actions",
        "rule_conditions",
        "rule_versions",
        "rules",
    ):
        op.drop_table(table, schema="rule")
    op.execute(sa.text('DROP SCHEMA IF EXISTS "rule"'))
