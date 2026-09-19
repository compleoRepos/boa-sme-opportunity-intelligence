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
    }
    owned = [
        table
        for table in Base.metadata.sorted_tables
        if table.schema in SCHEMAS and table.name not in future_governance_tables
    ]
    Base.metadata.create_all(bind=bind, tables=owned, checkfirst=True)


def downgrade():
    from boa_oi.models import Base

    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
    for schema in reversed(SCHEMAS):
        op.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
