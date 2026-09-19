"""Widen hybrid Rule Engine and ML version traces.

Revision ID: 0005_ml_integration_trace
Revises: 0004_ml_and_portfolio
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_ml_integration_trace"
down_revision = "0004_ml_and_portfolio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "opportunities",
        "engine_version",
        existing_type=sa.String(30),
        type_=sa.String(100),
        existing_nullable=False,
        schema="opportunity",
    )
    op.alter_column(
        "decision_audit",
        "engine_version",
        existing_type=sa.String(30),
        type_=sa.String(100),
        existing_nullable=False,
        schema="opportunity",
    )


def downgrade() -> None:
    op.alter_column(
        "decision_audit",
        "engine_version",
        existing_type=sa.String(100),
        type_=sa.String(30),
        existing_nullable=False,
        schema="opportunity",
    )
    op.alter_column(
        "opportunities",
        "engine_version",
        existing_type=sa.String(100),
        type_=sa.String(30),
        existing_nullable=False,
        schema="opportunity",
    )
