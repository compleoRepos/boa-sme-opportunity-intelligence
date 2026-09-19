"""Create the governed, versioned UI label catalog."""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_label_catalog"
down_revision = "0012_portfolio_sync_governance"
branch_labels = None
depends_on = None

DEFAULT_LABELS = (
    ("OPPORTUNITY_TYPE", "INVESTMENT_FINANCING", "Financement d'investissement"),
    ("OPPORTUNITY_TYPE", "TRADE_FINANCE", "Trade finance"),
    ("OPPORTUNITY_TYPE", "CASH_INVESTMENT", "Placement de trésorerie"),
    ("OPPORTUNITY_TYPE", "FINANCIAL_STRESS_SIGNAL", "Signal de tension financière"),
    ("ACTION", "CONTACT_CUSTOMER", "Contact client"),
    ("ACTION", "SCHEDULE_MEETING", "Rendez-vous planifié"),
    ("ACTION", "DEFER_OPPORTUNITY", "Opportunité à revoir"),
    ("ACTION", "MARK_CONVERTED", "Conversion enregistrée"),
    ("STATUS", "OPEN", "Ouvert"),
    ("STATUS", "ACCEPTED", "Acceptée"),
    ("STATUS", "DISMISSED", "Écartée"),
    ("STATUS", "DEFERRED", "À revoir"),
    ("STATUS", "EXPIRED", "Expirée"),
    ("PRIORITY", "P1", "Priorité P1"),
    ("PRIORITY", "P2", "Priorité P2"),
    ("PRIORITY", "P3", "Priorité P3"),
    ("PRIORITY", "P4", "Priorité P4"),
    ("HORIZON", "0-3_MONTHS", "0-3 mois"),
    ("HORIZON", "3-6_MONTHS", "3-6 mois"),
    ("HORIZON", "6-12_MONTHS", "6-12 mois"),
)


def upgrade() -> None:
    op.create_table(
        "label_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("namespace", sa.String(40), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("locale", sa.String(10), nullable=False, server_default="fr-FR"),
        sa.Column("label", sa.String(180), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", sa.String(120), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(120), nullable=False, server_default="migration-0013"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("code", "locale", name="uq_label_catalog_code_locale"),
        sa.CheckConstraint("current_version > 0", name="ck_label_catalog_positive_current_version"),
        schema="config",
    )
    op.create_table(
        "label_catalog_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "catalog_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("config.label_catalog.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(180), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.UniqueConstraint("catalog_entry_id", "version", name="uq_label_catalog_versions_entry"),
        sa.CheckConstraint("version > 0", name="ck_label_catalog_versions_positive_version"),
        schema="config",
    )
    op.create_index(
        "ix_label_catalog_version_created",
        "label_catalog_versions",
        ["catalog_entry_id", "created_at"],
        schema="config",
    )
    catalog = sa.table(
        "label_catalog",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("namespace", sa.String),
        sa.column("code", sa.String),
        sa.column("locale", sa.String),
        sa.column("label", sa.String),
        sa.column("current_version", sa.Integer),
        sa.column("active", sa.Boolean),
        sa.column("updated_by", sa.String),
        sa.column("justification", sa.Text),
        sa.column("created_by", sa.String),
        schema="config",
    )
    versions = sa.table(
        "label_catalog_versions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("catalog_entry_id", postgresql.UUID(as_uuid=True)),
        sa.column("version", sa.Integer),
        sa.column("label", sa.String),
        sa.column("active", sa.Boolean),
        sa.column("created_by", sa.String),
        sa.column("justification", sa.Text),
        schema="config",
    )
    catalog_rows = []
    version_rows = []
    for namespace, code, label in DEFAULT_LABELS:
        entry_id = uuid4()
        catalog_rows.append(
            {
                "id": entry_id,
                "namespace": namespace,
                "code": code,
                "locale": "fr-FR",
                "label": label,
                "current_version": 1,
                "active": True,
                "updated_by": "migration-0013",
                "justification": "Catalogue français initial du pilote",
                "created_by": "migration-0013",
            }
        )
        version_rows.append(
            {
                "id": uuid4(),
                "catalog_entry_id": entry_id,
                "version": 1,
                "label": label,
                "active": True,
                "created_by": "migration-0013",
                "justification": "Catalogue français initial du pilote",
            }
        )
    op.bulk_insert(catalog, catalog_rows)
    op.bulk_insert(versions, version_rows)
    op.execute(
        sa.text(
            "CREATE OR REPLACE FUNCTION config.prevent_label_version_mutation() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION "
            "'label_catalog_versions is append-only'; END; $$"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER label_catalog_versions_immutable BEFORE UPDATE OR DELETE "
            "ON config.label_catalog_versions FOR EACH ROW EXECUTE FUNCTION "
            "config.prevent_label_version_mutation()"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER label_catalog_versions_no_truncate BEFORE TRUNCATE "
            "ON config.label_catalog_versions FOR EACH STATEMENT EXECUTE FUNCTION "
            "config.prevent_label_version_mutation()"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS label_catalog_versions_no_truncate "
            "ON config.label_catalog_versions"
        )
    )
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS label_catalog_versions_immutable "
            "ON config.label_catalog_versions"
        )
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS config.prevent_label_version_mutation()"))
    op.drop_table("label_catalog_versions", schema="config")
    op.drop_table("label_catalog", schema="config")
