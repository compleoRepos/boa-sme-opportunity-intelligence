"""Initial domain schemas and useful persistence tables."""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None
SCHEMAS = (
    "customer",
    "account",
    "transaction",
    "product",
    "analytics",
    "signal",
    "opportunity",
    "action",
    "audit",
    "config",
    "integration",
)


def upgrade():
    for schema in SCHEMAS:
        op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    from boa_oi.models import Base

    bind = op.get_bind()
    # Seules les tables des schémas de cette révision : les schémas rule, feature_store,
    # ml et portfolio sont créés par 0003 et 0004, sinon la chaîne échoue sur base vide.
    future_governance_tables = {
        "portfolio_assignments",
        "portfolio_sync_events",
        "portfolio_sync_receipts",
        "scoring_policies",
        "scoring_policy_versions",
        "scoring_policy_audit_logs",
        "label_catalog",
        "label_catalog_versions",
        "transaction_categories",
        "import_rejections",
        "training_examples",
        "training_jobs",
    }
    owned = [
        table
        for table in Base.metadata.sorted_tables
        if table.schema in SCHEMAS and table.name not in future_governance_tables
    ]
    Base.metadata.create_all(bind=bind, tables=owned, checkfirst=True)
    # Les modèles ORM reflètent toujours la tête courante. Retirer ici les colonnes
    # et largeurs introduites seulement en 0018 afin qu'une base vierge traverse
    # réellement le même historique qu'une base existante.
    op.execute(sa.text('ALTER TABLE "product"."products" DROP COLUMN IF EXISTS "source_url"'))
    op.execute(sa.text('ALTER TABLE "product"."products" DROP COLUMN IF EXISTS "description"'))
    op.execute(sa.text('ALTER TABLE "product"."products" DROP COLUMN IF EXISTS "family"'))
    op.alter_column(
        "opportunities",
        "rule_version",
        schema="opportunity",
        existing_type=sa.String(length=80),
        type_=sa.String(length=30),
        existing_nullable=False,
    )
    op.alter_column(
        "decision_audit",
        "rule_version",
        schema="opportunity",
        existing_type=sa.String(length=80),
        type_=sa.String(length=30),
        existing_nullable=False,
    )


def downgrade():
    from boa_oi.models import Base

    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
    for schema in reversed(SCHEMAS):
        op.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
