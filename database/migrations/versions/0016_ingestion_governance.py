"""Add governed ingestion manifests, quarantine and transaction categories.

Revision ID: 0016_ingestion_governance
Revises: 0015_customer_search_performance
"""

from __future__ import annotations

import hashlib
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016_ingestion_governance"
down_revision = "0015_customer_search_performance"
branch_labels = None
depends_on = None


def columns(table: str, schema: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table, schema=schema)}


def tables(schema: str) -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names(schema=schema))


def constraints(table: str, schema: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {
        str(item["name"])
        for item in (
            inspector.get_check_constraints(table, schema=schema)
            + inspector.get_unique_constraints(table, schema=schema)
            + inspector.get_foreign_keys(table, schema=schema)
        )
        if item.get("name")
    }


def indexes(table: str, schema: str) -> set[str]:
    return {
        str(item["name"])
        for item in sa.inspect(op.get_bind()).get_indexes(table, schema=schema)
        if item.get("name")
    }


def foreign_key_for_columns(table: str, schema: str, constrained: list[str]) -> str | None:
    for item in sa.inspect(op.get_bind()).get_foreign_keys(table, schema=schema):
        if item.get("constrained_columns") == constrained:
            return str(item["name"]) if item.get("name") else None
    return None


def add_column_if_missing(table: str, schema: str, column: sa.Column) -> None:
    if column.name not in columns(table, schema):
        op.add_column(table, column, schema=schema)


def upgrade() -> None:
    import_batch_columns = (
        sa.Column("contract_version", sa.String(20), nullable=True),
        sa.Column("external_batch_id", sa.String(120), nullable=True),
        sa.Column("source_watermark", sa.String(120), nullable=True),
        sa.Column("produced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expected_row_count", sa.Integer(), nullable=True),
        sa.Column("received_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quarantined_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quality_status", sa.String(20), nullable=False, server_default="UNKNOWN"),
        sa.Column("freshness_status", sa.String(20), nullable=False, server_default="UNKNOWN"),
        sa.Column("freshness_lag_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "quality_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    for column in import_batch_columns:
        add_column_if_missing("import_batches", "integration", column)

    batch_constraints = constraints("import_batches", "integration")
    if "ck_import_batches_governed_status" not in batch_constraints:
        op.create_check_constraint(
            op.f("ck_import_batches_governed_status"),
            "import_batches",
            "status IN ('RECEIVED','VALIDATING','APPLYING','COMPLETED','REJECTED',"
            "'QUARANTINED','RETRYABLE_FAILED','PARTIAL','RETRY_REQUIRED')",
            schema="integration",
        )
    if "ck_import_batches_quality_status" not in batch_constraints:
        op.create_check_constraint(
            op.f("ck_import_batches_quality_status"),
            "import_batches",
            "quality_status IN ('UNKNOWN','PASS','WARNING','FAIL')",
            schema="integration",
        )
    if "ck_import_batches_freshness_status" not in batch_constraints:
        op.create_check_constraint(
            op.f("ck_import_batches_freshness_status"),
            "import_batches",
            "freshness_status IN ('UNKNOWN','CURRENT','STALE')",
            schema="integration",
        )
    if "ck_import_batches_non_negative_counts" not in batch_constraints:
        op.create_check_constraint(
            op.f("ck_import_batches_non_negative_counts"),
            "import_batches",
            "row_count >= 0 AND received_row_count >= 0 AND accepted_count >= 0 "
            "AND duplicate_count >= 0 AND rejected_count >= 0 AND quarantined_count >= 0",
            schema="integration",
        )

    batch_indexes = indexes("import_batches", "integration")
    if "ix_import_batches_source_status" not in batch_indexes:
        op.create_index(
            "ix_import_batches_source_status",
            "import_batches",
            ["source_system", "status", "received_at"],
            schema="integration",
        )

    if "transaction_categories" not in tables("config"):
        op.create_table(
            "transaction_categories",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("category_code", sa.String(40), nullable=False),
            sa.Column("version", sa.String(30), nullable=False),
            sa.Column("label", sa.String(120), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("provenance", sa.String(30), nullable=False),
            sa.Column("checksum", sa.String(64), nullable=False),
            sa.Column("reason", sa.String(500), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("created_by", sa.String(120), nullable=False),
            sa.UniqueConstraint("category_code", "version", name="uq_tx_category_version"),
            sa.CheckConstraint(
                "provenance IN ('SYNTHETIC_POC','BOA_APPROVED','EXTERNAL_CONTRACT')",
                name="ck_tx_category_provenance",
            ),
            schema="config",
        )
        op.create_index(
            "ix_transaction_categories_active",
            "transaction_categories",
            ["category_code", "active"],
            schema="config",
        )
        op.create_index(
            "uq_transaction_categories_one_active",
            "transaction_categories",
            ["category_code"],
            unique=True,
            schema="config",
            postgresql_where=sa.text("active"),
        )

    category_table = sa.table(
        "transaction_categories",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("category_code", sa.String()),
        sa.column("version", sa.String()),
        sa.column("label", sa.String()),
        sa.column("active", sa.Boolean()),
        sa.column("provenance", sa.String()),
        sa.column("checksum", sa.String()),
        sa.column("reason", sa.String()),
        sa.column("created_by", sa.String()),
        schema="config",
    )
    existing_synthetic_categories = (
        ("CUSTOMER_RECEIPT", "Encaissement client"),
        ("SUPPLIER_PAYMENT", "Paiement fournisseur"),
        ("OPERATING_EXPENSE", "Charge d'exploitation"),
    )
    for code, label in existing_synthetic_categories:
        payload = f"SYNTHETIC_POC|{code}|existing-synthetic-v1|{label}"
        statement = postgresql.insert(category_table).values(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"boa-sme-oi:transaction-category:{code}:v1"),
            category_code=code,
            version="existing-synthetic-v1",
            label=label,
            active=True,
            provenance="SYNTHETIC_POC",
            checksum=hashlib.sha256(payload.encode()).hexdigest(),
            reason="Catégorie déjà émise par le générateur synthétique du POC ; non approuvée BOA.",
            created_by="migration-0016",
        )
        op.execute(statement.on_conflict_do_nothing(index_elements=["category_code", "version"]))

    if "import_rejections" not in tables("integration"):
        op.create_table(
            "import_rejections",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "batch_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("integration.import_batches.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("domain", sa.String(40), nullable=False),
            sa.Column("row_number", sa.Integer(), nullable=False),
            sa.Column("source_record_ref", sa.String(120), nullable=True),
            sa.Column("row_hash", sa.String(64), nullable=False),
            sa.Column("reason_code", sa.String(80), nullable=False),
            sa.Column("field_name", sa.String(80), nullable=True),
            sa.Column(
                "safe_details_json",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("status", sa.String(20), nullable=False, server_default="QUARANTINED"),
            sa.Column("correlation_id", sa.String(100), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("batch_id", "domain", "row_number", name="uq_import_rejection_row"),
            sa.CheckConstraint(
                "status IN ('QUARANTINED','RESOLVED','DISMISSED')",
                name="ck_import_rejection_status",
            ),
            schema="integration",
        )
        op.create_index(
            "ix_import_rejections_batch_status",
            "import_rejections",
            ["batch_id", "status"],
            schema="integration",
        )

    transaction_columns = (
        sa.Column("import_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_record_hash", sa.String(64), nullable=True),
        sa.Column("category_version", sa.String(30), nullable=True),
    )
    for column in transaction_columns:
        add_column_if_missing("transactions", "transaction", column)
    if foreign_key_for_columns("transactions", "transaction", ["import_batch_id"]) is None:
        op.create_foreign_key(
            "fk_transactions_import_batch",
            "transactions",
            "import_batches",
            ["import_batch_id"],
            ["id"],
            source_schema="transaction",
            referent_schema="integration",
            ondelete="RESTRICT",
        )
    transaction_indexes = indexes("transactions", "transaction")
    if "ix_transactions_import_batch" not in transaction_indexes:
        op.create_index(
            "ix_transactions_import_batch",
            "transactions",
            ["import_batch_id"],
            schema="transaction",
        )


def downgrade() -> None:
    transaction_indexes = indexes("transactions", "transaction")
    if "ix_transactions_import_batch" in transaction_indexes:
        op.drop_index(
            "ix_transactions_import_batch", table_name="transactions", schema="transaction"
        )
    import_batch_foreign_key = foreign_key_for_columns(
        "transactions", "transaction", ["import_batch_id"]
    )
    if import_batch_foreign_key is not None:
        op.drop_constraint(
            import_batch_foreign_key,
            "transactions",
            schema="transaction",
            type_="foreignkey",
        )
    for name in ("category_version", "source_record_hash", "import_batch_id"):
        if name in columns("transactions", "transaction"):
            op.drop_column("transactions", name, schema="transaction")

    if "import_rejections" in tables("integration"):
        op.drop_table("import_rejections", schema="integration")
    if "transaction_categories" in tables("config"):
        op.drop_table("transaction_categories", schema="config")

    batch_constraints = constraints("import_batches", "integration")
    for name in (
        "ck_import_batches_non_negative_counts",
        "ck_import_batches_freshness_status",
        "ck_import_batches_quality_status",
        "ck_import_batches_governed_status",
    ):
        if name in batch_constraints:
            op.drop_constraint(op.f(name), "import_batches", schema="integration", type_="check")
    batch_indexes = indexes("import_batches", "integration")
    if "ix_import_batches_source_status" in batch_indexes:
        op.drop_index(
            "ix_import_batches_source_status", table_name="import_batches", schema="integration"
        )
    for name in (
        "quality_json",
        "freshness_lag_seconds",
        "freshness_status",
        "quality_status",
        "quarantined_count",
        "rejected_count",
        "duplicate_count",
        "accepted_count",
        "received_row_count",
        "expected_row_count",
        "received_at",
        "produced_at",
        "source_watermark",
        "external_batch_id",
        "contract_version",
    ):
        if name in columns("import_batches", "integration"):
            op.drop_column("import_batches", name, schema="integration")


__all__ = ["downgrade", "upgrade"]
