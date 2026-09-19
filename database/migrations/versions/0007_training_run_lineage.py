"""Persist complete point-in-time lineage for governed ML training runs.

Revision ID: 0007_training_run_lineage
Revises: 0006_governance_resilience
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_training_run_lineage"
down_revision = "0006_governance_resilience"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "training_runs",
        sa.Column(
            "lineage_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema="ml",
    )


def downgrade() -> None:
    op.drop_column("training_runs", "lineage_json", schema="ml")
