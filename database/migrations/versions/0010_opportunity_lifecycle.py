"""Add the governed opportunity lifecycle and maintenance indexes.

Revision ID: 0010_opportunity_lifecycle
Revises: 0009_pilot_readiness_debts
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_opportunity_lifecycle"
down_revision = "0009_pilot_readiness_debts"
branch_labels = None
depends_on = None

SCHEMA = "opportunity"
TABLE = "opportunities"
LIFECYCLE_CHECK = "ck_opportunities_lifecycle"
INDEXES = {
    "ix_opportunities_customer_type_status": ["customer_id", "opportunity_type", "status"],
    "ix_opportunities_expiration": ["status", "expires_at"],
    "ix_opportunities_cooldown": ["customer_id", "opportunity_type", "cooldown_until"],
}


def upgrade() -> None:
    """Upgrade both legacy databases and databases bootstrapped from current metadata in 0001."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns(TABLE, schema=SCHEMA)}
    additions = (
        sa.Column(
            "status_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_action_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in additions:
        if column.name not in columns:
            op.add_column(TABLE, column, schema=SCHEMA)

    # Existing lifecycle values are preserved. The guard deliberately fails instead of coercing
    # an unknown historical status and thereby rewriting business history.
    invalid_status = bind.execute(
        sa.text(
            "SELECT status FROM opportunity.opportunities "
            "WHERE status NOT IN "
            "('OPEN','ACCEPTED','CONTACTED','CONVERTED','DISMISSED','DEFERRED','EXPIRED') "
            "LIMIT 1"
        )
    ).scalar_one_or_none()
    if invalid_status is not None:
        raise RuntimeError(
            "Cannot install opportunity lifecycle: unsupported historical status "
            f"{invalid_status!r}."
        )

    bind.execute(
        sa.text(
            "UPDATE opportunity.opportunities "
            "SET status_updated_at = "
            "COALESCE(status_updated_at, updated_at, generated_at, created_at)"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE opportunity.opportunities "
            "SET expires_at = COALESCE(expires_at, generated_at + INTERVAL '90 days') "
            "WHERE status IN ('OPEN','ACCEPTED','CONTACTED')"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE opportunity.opportunities "
            "SET cooldown_until = COALESCE(cooldown_until, status_updated_at + INTERVAL '30 days') "
            "WHERE status IN ('CONVERTED','DISMISSED','DEFERRED','EXPIRED')"
        )
    )

    inspector = sa.inspect(bind)
    checks = {item["name"] for item in inspector.get_check_constraints(TABLE, schema=SCHEMA)}
    if LIFECYCLE_CHECK not in checks:
        op.create_check_constraint(
            LIFECYCLE_CHECK,
            TABLE,
            "status IN "
            "('OPEN','ACCEPTED','CONTACTED','CONVERTED','DISMISSED','DEFERRED','EXPIRED')",
            schema=SCHEMA,
        )

    existing_indexes = {item["name"] for item in inspector.get_indexes(TABLE, schema=SCHEMA)}
    for name, column_names in INDEXES.items():
        if name not in existing_indexes:
            op.create_index(name, TABLE, column_names, schema=SCHEMA)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_indexes = {item["name"] for item in inspector.get_indexes(TABLE, schema=SCHEMA)}
    for name in reversed(tuple(INDEXES)):
        if name in existing_indexes:
            op.drop_index(name, table_name=TABLE, schema=SCHEMA)
    checks = {item["name"] for item in inspector.get_check_constraints(TABLE, schema=SCHEMA)}
    if LIFECYCLE_CHECK in checks:
        op.drop_constraint(op.f(LIFECYCLE_CHECK), TABLE, schema=SCHEMA, type_="check")
    columns = {item["name"] for item in inspector.get_columns(TABLE, schema=SCHEMA)}
    for name in (
        "last_action_at",
        "cooldown_until",
        "expires_at",
        "status_reason",
        "status_updated_at",
    ):
        if name in columns:
            op.drop_column(TABLE, name, schema=SCHEMA)
