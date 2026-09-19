"""Add trigram indexes for scalable customer search.

Revision ID: 0015_customer_search_performance
Revises: 0014_email_notifications
"""

from alembic import op

revision = "0015_customer_search_performance"
down_revision = "0014_email_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customers_customer_ref_trgm "
        "ON customer.customers USING gin (customer_ref gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customers_legal_name_trgm "
        "ON customer.customers USING gin (legal_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customers_sector_code_trgm "
        "ON customer.customers USING gin (sector_code gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS customer.ix_customers_sector_code_trgm")
    op.execute("DROP INDEX IF EXISTS customer.ix_customers_legal_name_trgm")
    op.execute("DROP INDEX IF EXISTS customer.ix_customers_customer_ref_trgm")
    # pg_trgm is deliberately retained because another database object may use it.


__all__ = ["downgrade", "upgrade"]
