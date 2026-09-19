"""Persist dated customer, relationship-manager, and branch assignments.

Revision ID: 0009_pilot_readiness_debts
Revises: 0008_training_status
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from boa_oi.technical.ids import deterministic_uuid
from sqlalchemy.dialects import postgresql

revision = "0009_pilot_readiness_debts"
down_revision = "0008_training_status"
branch_labels = None
depends_on = None

INITIAL_VALID_FROM = datetime(2025, 10, 1, tzinfo=timezone.utc)


def upgrade() -> None:
    op.create_table(
        "portfolio_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer.customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "relationship_manager_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer.relationship_managers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("branch_code", sa.String(30), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actor", sa.String(120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_portfolio_assignments_validity",
        ),
        schema="customer",
    )
    op.create_index(
        "uq_portfolio_assignments_active_customer",
        "portfolio_assignments",
        ["customer_id"],
        unique=True,
        schema="customer",
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index(
        "ix_portfolio_assignments_rm_validity",
        "portfolio_assignments",
        ["relationship_manager_id", "valid_from", "valid_to"],
        schema="customer",
    )
    op.create_index(
        "ix_portfolio_assignments_branch_validity",
        "portfolio_assignments",
        ["branch_code", "valid_from", "valid_to"],
        schema="customer",
    )

    assignments = sa.table(
        "portfolio_assignments",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("customer_id", postgresql.UUID(as_uuid=True)),
        sa.column("relationship_manager_id", postgresql.UUID(as_uuid=True)),
        sa.column("branch_code", sa.String()),
        sa.column("valid_from", sa.DateTime(timezone=True)),
        sa.column("valid_to", sa.DateTime(timezone=True)),
        sa.column("actor", sa.String()),
        sa.column("reason", sa.Text()),
        schema="customer",
    )
    customers = sa.table(
        "customers",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("rm_id", postgresql.UUID(as_uuid=True)),
        schema="customer",
    )
    managers = sa.table(
        "relationship_managers",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("branch_code", sa.String()),
        schema="customer",
    )
    rows = op.get_bind().execute(
        sa.select(customers.c.id, customers.c.rm_id, managers.c.branch_code).select_from(
            customers.join(managers, customers.c.rm_id == managers.c.id)
        )
    )
    op.bulk_insert(
        assignments,
        [
            {
                "id": deterministic_uuid("portfolio-assignment", customer_id, INITIAL_VALID_FROM),
                "customer_id": customer_id,
                "relationship_manager_id": relationship_manager_id,
                "branch_code": branch_code,
                "valid_from": INITIAL_VALID_FROM,
                "valid_to": None,
                "actor": "migration-0009",
                "reason": "Initial assignment migrated from customer.rm_id",
            }
            for customer_id, relationship_manager_id, branch_code in rows
        ],
    )


def downgrade() -> None:
    op.drop_table("portfolio_assignments", schema="customer")
