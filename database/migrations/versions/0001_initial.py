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
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade():
    from boa_oi.models import Base

    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
    for schema in reversed(SCHEMAS):
        op.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
