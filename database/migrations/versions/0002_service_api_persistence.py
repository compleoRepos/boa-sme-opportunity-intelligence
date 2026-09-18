"""Persist API explanations, local import receipts, action idempotency and outcomes."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_service_api_persistence"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def tables(schema: str) -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names(schema=schema))


def columns(table: str, schema: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table, schema=schema)}


def add(table: str, schema: str, column: sa.Column) -> None:
    if column.name not in columns(table, schema):
        op.add_column(table, column, schema=schema)


def upgrade():
    for schema in ("customer", "account", "transaction", "product"):
        if "import_receipts" not in tables(schema):
            op.create_table(
                "import_receipts",
                sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
                sa.Column("idempotency_key", sa.String(200), nullable=False, unique=True),
                sa.Column("request_hash", sa.String(64), nullable=False),
                sa.Column("row_count", sa.Integer(), nullable=False),
                sa.Column("status", sa.String(20), nullable=False),
                sa.Column("correlation_id", sa.String(100), nullable=False),
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.func.now(),
                ),
                schema=schema,
            )
    for column in (
        sa.Column("customer_ref", sa.String(40), nullable=False, server_default="UNKNOWN"),
        sa.Column(
            "customer_name",
            sa.String(180),
            nullable=False,
            server_default="Synthetic SME",
        ),
        sa.Column(
            "why_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("what_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("when_text", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "recommended_products_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "explanation_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("engine_version", sa.String(30), nullable=False, server_default="0.1.0"),
        sa.Column("rule_version", sa.String(30), nullable=False, server_default="1"),
    ):
        add("opportunities", "opportunity", column)
    add(
        "signals",
        "signal",
        sa.Column("customer_ref", sa.String(40), nullable=False, server_default="UNKNOWN"),
    )
    if "decision_audit" not in tables("opportunity"):
        op.create_table(
            "decision_audit",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("engine_version", sa.String(30), nullable=False),
            sa.Column("rule_version", sa.String(30), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("input_reference", sa.String(120), nullable=False),
            sa.Column("signals_json", postgresql.JSONB(), nullable=False),
            sa.Column("metric_snapshots_json", postgresql.JSONB(), nullable=False),
            sa.Column("confidence_components_json", postgresql.JSONB(), nullable=False),
            sa.Column("priority_components_json", postgresql.JSONB(), nullable=False),
            sa.Column("decision_hash", sa.String(64), nullable=False, unique=True),
            schema="opportunity",
        )
    for column in (
        sa.Column("action_ref", sa.String(80), nullable=True),
        sa.Column("opportunity_ref", sa.String(80), nullable=True),
        sa.Column("customer_ref", sa.String(40), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("assigned_to", sa.String(120), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=True),
        sa.Column("request_hash", sa.String(64), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ):
        add("opportunity_actions", "action", column)
    constraints = {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_unique_constraints(
            "opportunity_actions", schema="action"
        )
    }
    if "uq_opportunity_actions_action_ref" not in constraints:
        op.create_unique_constraint(
            "uq_opportunity_actions_action_ref",
            "opportunity_actions",
            ["action_ref"],
            schema="action",
        )
    if "uq_opportunity_actions_idempotency_key" not in constraints:
        op.create_unique_constraint(
            "uq_opportunity_actions_idempotency_key",
            "opportunity_actions",
            ["idempotency_key"],
            schema="action",
        )
    if "action_outcomes" not in tables("action"):
        op.create_table(
            "action_outcomes",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("outcome_type", sa.String(40), nullable=False),
            sa.Column(
                "recorded_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("recorded_by", sa.String(120), nullable=False),
            sa.Column("correlation_id", sa.String(100), nullable=False),
            sa.Column(
                "metadata_json",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            schema="action",
        )
        op.create_index(
            "ix_action_outcomes_action_time",
            "action_outcomes",
            ["action_id", "recorded_at"],
            schema="action",
        )


def downgrade():
    if "action_outcomes" in tables("action"):
        op.drop_table("action_outcomes", schema="action")
    for schema in ("product", "transaction", "account", "customer"):
        if "import_receipts" in tables(schema):
            op.drop_table("import_receipts", schema=schema)
