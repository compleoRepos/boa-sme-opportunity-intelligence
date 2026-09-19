"""Govern dated portfolio synchronization and event provenance."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_portfolio_sync_governance"
down_revision = "0011_action_transition_saga"
branch_labels = None
depends_on = None

SCHEMA = "customer"
TABLE = "portfolio_assignments"


def upgrade() -> None:
    op.create_table(
        "portfolio_sync_receipts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("source_system", sa.String(length=40), nullable=False),
        sa.Column("batch_ref", sa.String(length=120), nullable=False),
        sa.Column("source_watermark", sa.String(length=120), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("source_system", "batch_ref"),
        schema=SCHEMA,
    )
    op.create_table(
        "portfolio_sync_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_system", sa.String(length=40), nullable=False),
        sa.Column("source_event_id", sa.String(length=120), nullable=False),
        sa.Column("batch_ref", sa.String(length=120), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("customer_ref", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("assignment_id", sa.UUID(), nullable=True),
        sa.Column("correlation_id", sa.String(length=100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_system", "source_event_id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_portfolio_sync_events_batch",
        "portfolio_sync_events",
        ["source_system", "batch_ref"],
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("portfolio_id", sa.String(length=80), nullable=False, server_default="LEGACY"),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column(
            "assignment_type",
            sa.String(length=20),
            nullable=False,
            server_default="PRIMARY",
        ),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.true()),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("source_system", sa.String(length=40), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("source_event_id", sa.String(length=120), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("source_payload_hash", sa.String(length=64), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("source_watermark", sa.String(length=120), nullable=True),
        schema=SCHEMA,
    )
    op.execute(
        sa.text(
            "UPDATE customer.portfolio_assignments "
            "SET portfolio_id = 'PORTFOLIO-' || branch_code, "
            "source_system = COALESCE(source_system, 'MIGRATION_0012')"
        )
    )
    op.create_check_constraint(
        op.f("ck_portfolio_assignments_assignment_type"),
        TABLE,
        "assignment_type IN ('PRIMARY')",
        schema=SCHEMA,
    )
    op.create_unique_constraint(
        op.f("uq_portfolio_assignments_source_system"),
        TABLE,
        ["source_system", "source_event_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_portfolio_assignments_portfolio_validity",
        TABLE,
        ["portfolio_id", "valid_from", "valid_to"],
        schema=SCHEMA,
    )
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
    op.execute(
        sa.text(
            "ALTER TABLE customer.portfolio_assignments "
            "ADD CONSTRAINT ex_portfolio_assignments_no_overlap "
            "EXCLUDE USING gist ("
            "customer_id WITH =, "
            "tstzrange(valid_from, COALESCE(valid_to, 'infinity'::timestamptz), '[)') WITH &&"
            ")"
        )
    )
    op.execute(
        sa.text(
            "CREATE OR REPLACE FUNCTION audit.prevent_audit_log_mutation() "
            "RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN RAISE EXCEPTION 'audit.audit_logs is append-only'; END; $$"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_audit_logs_append_only "
            "BEFORE UPDATE OR DELETE ON audit.audit_logs "
            "FOR EACH ROW EXECUTE FUNCTION audit.prevent_audit_log_mutation()"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_audit_logs_append_only ON audit.audit_logs"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS audit.prevent_audit_log_mutation()"))
    op.execute(
        sa.text(
            "ALTER TABLE customer.portfolio_assignments "
            "DROP CONSTRAINT IF EXISTS ex_portfolio_assignments_no_overlap"
        )
    )
    op.drop_index(
        "ix_portfolio_assignments_portfolio_validity",
        table_name=TABLE,
        schema=SCHEMA,
    )
    op.drop_constraint(
        op.f("uq_portfolio_assignments_source_system"),
        TABLE,
        schema=SCHEMA,
        type_="unique",
    )
    op.drop_constraint(
        op.f("ck_portfolio_assignments_assignment_type"),
        TABLE,
        schema=SCHEMA,
        type_="check",
    )
    for column in (
        "source_watermark",
        "source_payload_hash",
        "source_event_id",
        "source_system",
        "is_primary",
        "assignment_type",
        "portfolio_id",
    ):
        op.drop_column(TABLE, column, schema=SCHEMA)
    op.drop_index(
        "ix_portfolio_sync_events_batch",
        table_name="portfolio_sync_events",
        schema=SCHEMA,
    )
    op.drop_table("portfolio_sync_events", schema=SCHEMA)
    op.drop_table("portfolio_sync_receipts", schema=SCHEMA)
