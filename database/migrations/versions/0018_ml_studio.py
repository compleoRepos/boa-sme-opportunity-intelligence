"""Add the governed ML Studio training job and demonstration dataset support.

Revision ID: 0018_ml_studio
Revises: 0017_ml_shadow_governance
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_ml_studio"
down_revision = "0017_ml_shadow_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_dataset_manifests_source_kind", "dataset_manifests", schema="ml", type_="check"
    )
    op.create_check_constraint(
        "ck_dataset_manifests_source_kind",
        "dataset_manifests",
        "source_kind IN ('LOCAL_COMMERCIAL_OUTCOME','BOA_HISTORICAL_OBSERVED','SYNTHETIC',"
        "'DEMO_SYNTHETIC_LABELS')",
        schema="ml",
    )
    op.drop_constraint(
        "ck_dataset_manifests_status", "dataset_manifests", schema="ml", type_="check"
    )
    op.create_check_constraint(
        "ck_dataset_manifests_status",
        "dataset_manifests",
        "status IN ('BLOCKED','CANDIDATE','VALIDATED','TRAINING_READY')",
        schema="ml",
    )

    # Older revisions used both convention-expanded and literal constraint names.
    # Raw SQL makes this migration safe on databases created at either point in time.
    op.execute(
        sa.text(
            "ALTER TABLE ml.model_registry "
            "DROP CONSTRAINT IF EXISTS ck_model_registry_ck_model_registry_status"
        )
    )
    op.execute(
        sa.text("ALTER TABLE ml.model_registry DROP CONSTRAINT IF EXISTS ck_model_registry_status")
    )
    op.execute(
        sa.text(
            "ALTER TABLE ml.model_registry ADD CONSTRAINT ck_model_registry_status "
            "CHECK (status IN ('REGISTERED','VALIDATING','SUBMITTED','APPROVED','CHALLENGER',"
            "'CHAMPION','ACTIVE','RETIRED','DEMO_ONLY'))"
        )
    )
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
            "'CHALLENGER','CHAMPION','RETIRED','REJECTED','DEMO_ONLY'))"
        )
    )

    op.create_table(
        "training_examples",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "manifest_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ml.dataset_manifests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_ref", sa.String(80), nullable=False),
        sa.Column("split", sa.String(20), nullable=False),
        sa.Column("observation_as_of", sa.Date(), nullable=False),
        sa.Column("label_available_from", sa.Date(), nullable=False),
        sa.Column("feature_values_json", postgresql.JSONB(), nullable=False),
        sa.Column("label", sa.Boolean(), nullable=False),
        sa.Column("source_kind", sa.String(40), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "manifest_id", "entity_ref", "observation_as_of", name="uq_ml_training_example"
        ),
        sa.CheckConstraint("split IN ('TRAIN','TEST')", name="ck_ml_training_examples_split"),
        sa.CheckConstraint(
            "source_kind IN ('BOA_HISTORICAL_OBSERVED','DEMO_SYNTHETIC_LABELS')",
            name="ck_ml_training_examples_source",
        ),
        sa.CheckConstraint(
            "label_available_from > observation_as_of",
            name="ck_ml_training_examples_label_time",
        ),
        schema="ml",
    )
    op.create_index(
        "ix_ml_training_examples_manifest_split",
        "training_examples",
        ["manifest_id", "split"],
        schema="ml",
    )

    op.create_table(
        "training_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "manifest_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ml.dataset_manifests.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("algorithm", sa.String(40), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("current_step", sa.String(80), nullable=True),
        sa.Column("percentage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "steps_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("result_json", postgresql.JSONB(), nullable=True),
        sa.Column("error_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "cancellation_requested", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("author", sa.String(120), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False, unique=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','INSUFFICIENT_DATA','CANCELLED')",
            name="ck_ml_training_jobs_status",
        ),
        sa.CheckConstraint("percentage BETWEEN 0 AND 100", name="ck_ml_training_jobs_percentage"),
        sa.CheckConstraint(
            "algorithm = 'LOGISTIC_REGRESSION'", name="ck_ml_training_jobs_algorithm"
        ),
        schema="ml",
    )
    op.create_index(
        "ix_ml_training_jobs_created",
        "training_jobs",
        ["created_at"],
        schema="ml",
    )
    op.create_index(
        "uq_ml_training_jobs_active_manifest",
        "training_jobs",
        ["manifest_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED','RUNNING')"),
        schema="ml",
    )


def downgrade() -> None:
    op.drop_index("uq_ml_training_jobs_active_manifest", table_name="training_jobs", schema="ml")
    op.drop_index("ix_ml_training_jobs_created", table_name="training_jobs", schema="ml")
    op.drop_table("training_jobs", schema="ml")
    op.drop_index(
        "ix_ml_training_examples_manifest_split", table_name="training_examples", schema="ml"
    )
    op.drop_table("training_examples", schema="ml")

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
    op.execute(
        sa.text("ALTER TABLE ml.model_registry DROP CONSTRAINT IF EXISTS ck_model_registry_status")
    )
    op.execute(
        sa.text(
            "ALTER TABLE ml.model_registry ADD CONSTRAINT ck_model_registry_status "
            "CHECK (status IN ('REGISTERED','VALIDATING','SUBMITTED','APPROVED','CHALLENGER',"
            "'CHAMPION','ACTIVE','RETIRED'))"
        )
    )
    op.drop_constraint(
        "ck_dataset_manifests_status", "dataset_manifests", schema="ml", type_="check"
    )
    op.create_check_constraint(
        "ck_dataset_manifests_status",
        "dataset_manifests",
        "status IN ('BLOCKED','CANDIDATE','VALIDATED')",
        schema="ml",
    )
    op.drop_constraint(
        "ck_dataset_manifests_source_kind", "dataset_manifests", schema="ml", type_="check"
    )
    op.create_check_constraint(
        "ck_dataset_manifests_source_kind",
        "dataset_manifests",
        "source_kind IN ('LOCAL_COMMERCIAL_OUTCOME','BOA_HISTORICAL_OBSERVED','SYNTHETIC')",
        schema="ml",
    )
