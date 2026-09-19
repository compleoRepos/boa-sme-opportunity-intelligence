"""Allow the REGISTERED state used by the governed ML workflow.

Revision ID: 0008_training_status
Revises: 0007_training_run_lineage
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_training_status"
down_revision = "0007_training_run_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE ml.training_runs "
            "DROP CONSTRAINT IF EXISTS ck_training_runs_ck_training_runs_status"
        )
    )
    op.execute(
        sa.text("ALTER TABLE ml.training_runs DROP CONSTRAINT IF EXISTS ck_training_runs_status")
    )
    op.execute(
        sa.text(
            "ALTER TABLE ml.training_runs ADD CONSTRAINT ck_training_runs_status "
            "CHECK (status IN ('DRAFT','REGISTERED','VALIDATING','SUBMITTED','APPROVED',"
            "'CHALLENGER','CHAMPION','RETIRED','REJECTED'))"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("ALTER TABLE ml.training_runs DROP CONSTRAINT IF EXISTS ck_training_runs_status")
    )
    op.execute(
        sa.text(
            "ALTER TABLE ml.training_runs ADD CONSTRAINT ck_training_runs_status "
            "CHECK (status IN ('DRAFT','VALIDATING','SUBMITTED','APPROVED','CHALLENGER',"
            "'CHAMPION','RETIRED','REJECTED'))"
        )
    )
