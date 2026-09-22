"""Persist resumable Action to Opportunity transition commands.

Revision ID: 0011_action_transition_saga
Revises: 0010_opportunity_lifecycle
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_action_transition_saga"
down_revision = "0010_opportunity_lifecycle"
branch_labels = None
depends_on = None

SCHEMA = "action"
TABLE = "opportunity_actions"
CHECK = "ck_action_transition_status"
INDEX = "ix_actions_transition_status_updated"
UNIQUE = "uq_action_transition_command_id"


def upgrade() -> None:
    """Upgrade legacy databases and databases bootstrapped from current metadata in 0001."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns(TABLE, schema=SCHEMA)}
    additions = (
        sa.Column(
            "transition_status",
            sa.String(20),
            nullable=False,
            server_default="NOT_REQUIRED",
        ),
        sa.Column("transition_target", sa.String(20), nullable=True),
        sa.Column("transition_command_id", sa.String(200), nullable=True),
        sa.Column(
            "transition_attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("transition_error", sa.Text(), nullable=True),
        sa.Column("transition_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pending_outcome_type", sa.String(40), nullable=True),
    )
    for column in additions:
        if column.name not in columns:
            op.add_column(TABLE, column, schema=SCHEMA)

    bind.execute(
        sa.text(
            "UPDATE action.opportunity_actions "
            "SET transition_status = CASE "
            "WHEN action_type IN "
            "('ACCEPT_OPPORTUNITY','DISMISS_OPPORTUNITY','DEFER_OPPORTUNITY','MARK_CONVERTED') "
            "OR outcome_type IS NOT NULL THEN 'APPLIED' ELSE 'NOT_REQUIRED' END "
            "WHERE transition_status IS NULL OR transition_status = 'NOT_REQUIRED'"
        )
    )

    inspector = sa.inspect(bind)
    checks = inspector.get_check_constraints(TABLE, schema=SCHEMA)
    if not any("transition_status" in str(item.get("sqltext")) for item in checks):
        op.create_check_constraint(
            CHECK,
            TABLE,
            "transition_status IN ('NOT_REQUIRED','PENDING','APPLIED','FAILED')",
            schema=SCHEMA,
        )
    unique_constraints = inspector.get_unique_constraints(TABLE, schema=SCHEMA)
    if not any(
        item.get("column_names") == ["transition_command_id"] for item in unique_constraints
    ):
        op.create_unique_constraint(UNIQUE, TABLE, ["transition_command_id"], schema=SCHEMA)
    indexes = {item["name"] for item in inspector.get_indexes(TABLE, schema=SCHEMA)}
    if INDEX not in indexes:
        op.create_index(INDEX, TABLE, ["transition_status", "updated_at"], schema=SCHEMA)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {item["name"] for item in inspector.get_indexes(TABLE, schema=SCHEMA)}
    if INDEX in indexes:
        op.drop_index(INDEX, table_name=TABLE, schema=SCHEMA)
    unique_constraints = inspector.get_unique_constraints(TABLE, schema=SCHEMA)
    transition_unique = next(
        (
            item["name"]
            for item in unique_constraints
            if item.get("column_names") == ["transition_command_id"]
        ),
        None,
    )
    if transition_unique is not None:
        op.drop_constraint(op.f(transition_unique), TABLE, schema=SCHEMA, type_="unique")
    checks = inspector.get_check_constraints(TABLE, schema=SCHEMA)
    transition_check = next(
        (item["name"] for item in checks if "transition_status" in str(item.get("sqltext"))),
        None,
    )
    if transition_check is not None:
        op.drop_constraint(op.f(transition_check), TABLE, schema=SCHEMA, type_="check")
    columns = {item["name"] for item in inspector.get_columns(TABLE, schema=SCHEMA)}
    for name in (
        "pending_outcome_type",
        "transition_requested_at",
        "transition_error",
        "transition_attempt_count",
        "transition_command_id",
        "transition_target",
        "transition_status",
    ):
        if name in columns:
            op.drop_column(TABLE, name, schema=SCHEMA)
