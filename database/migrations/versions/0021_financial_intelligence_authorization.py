"""Add Financial Intelligence authorization, portfolio membership and access audit.

Revision ID: 0021_financial_intelligence
Revises: 0020_multibank_visibility

RLS is deliberately not enabled here: the current service-role topology owns each schema
and has no reviewed, transaction-scoped tenant context. Backend deny-by-default isolation is
implemented and tested; PostgreSQL RLS remains BLOCKED pending that architecture decision.
Runtime roles and grants are bootstrapped outside Alembic by 00-init-service-schemas.sh.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_financial_intelligence"
down_revision = "0020_multibank_visibility"
branch_labels = None
depends_on = None

SCHEMA = "financial_intelligence"


def upgrade() -> None:
    # Le provisioning crée le schéma et le rôle sur une base neuve. Alembic doit aussi
    # fonctionner sur une base administrateur seule, sans dépendre de ce bootstrap.
    op.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
    op.create_table(
        "external_consumers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consumer_ref", sa.String(80), nullable=False, unique=True),
        sa.Column("display_name", sa.String(180), nullable=False),
        sa.Column("consumer_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "allowed_scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("synthetic_data", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','SUSPENDED','CLOSED')", name="ck_external_consumers_status"
        ),
        sa.CheckConstraint(
            "consumer_type IN ('FUND','HOLDING','PARTNER')",
            name="ck_external_consumers_type",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_fi_consumers_status", "external_consumers", ["status"], schema=SCHEMA)

    op.create_table(
        "external_portfolios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "consumer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.external_consumers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("portfolio_ref", sa.String(80), nullable=False),
        sa.Column("fund_ref", sa.String(80), nullable=False, unique=True),
        sa.Column("display_name", sa.String(180), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','SUSPENDED','CLOSED')", name="ck_external_portfolios_status"
        ),
        sa.UniqueConstraint("id", "consumer_id", name="uq_fi_portfolio_id_consumer"),
        sa.UniqueConstraint("consumer_id", "portfolio_ref", name="uq_fi_portfolio_consumer_ref"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_fi_portfolios_consumer_status",
        "external_portfolios",
        ["consumer_id", "status"],
        schema=SCHEMA,
    )

    op.create_table(
        "external_portfolio_companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.external_portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("company_ref", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_fi_company_status"),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from", name="ck_fi_company_validity"
        ),
        sa.CheckConstraint(
            "status <> 'INACTIVE' OR valid_until IS NOT NULL",
            name="ck_fi_company_inactive_requires_valid_until",
        ),
        sa.UniqueConstraint("portfolio_id", "company_ref", name="uq_fi_portfolio_company"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_fi_portfolio_companies_company_status",
        "external_portfolio_companies",
        ["company_ref", "status", "valid_from", "valid_until"],
        schema=SCHEMA,
    )

    op.create_table(
        "data_access_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("grant_ref", sa.String(100), nullable=False, unique=True),
        sa.Column(
            "consumer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.external_consumers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("subject_id", sa.String(120), nullable=False),
        sa.Column("client_id", sa.String(120), nullable=False),
        sa.Column("scope", sa.String(80), nullable=False),
        sa.Column("purpose", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("authorization_reference", sa.String(160), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','EXPIRED','REVOKED')", name="ck_data_access_grants_status"
        ),
        sa.CheckConstraint("valid_until > valid_from", name="ck_data_access_grants_validity"),
        sa.CheckConstraint(
            "purpose = 'SYNTHETIC_PORTFOLIO_MONITORING'",
            name="ck_data_access_grants_purpose",
        ),
        sa.CheckConstraint(
            "(status = 'REVOKED' AND revoked_at IS NOT NULL) OR "
            "(status <> 'REVOKED' AND revoked_at IS NULL)",
            name="ck_data_access_grants_revocation_state",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id", "consumer_id"],
            [
                f"{SCHEMA}.external_portfolios.id",
                f"{SCHEMA}.external_portfolios.consumer_id",
            ],
            name="fk_fi_grant_portfolio_consumer",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "consumer_id",
            "subject_id",
            "client_id",
            "portfolio_id",
            "scope",
            "purpose",
            "valid_from",
            name="uq_fi_grant_subject_portfolio_scope_from",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_fi_grants_subject_status_validity",
        "data_access_grants",
        ["subject_id", "client_id", "status", "valid_from", "valid_until"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_fi_grants_portfolio_scope",
        "data_access_grants",
        ["portfolio_id", "scope"],
        schema=SCHEMA,
    )

    op.create_table(
        "access_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consumer_id", postgresql.UUID(as_uuid=True)),
        sa.Column("subject_id", sa.String(120)),
        sa.Column("client_id", sa.String(120)),
        sa.Column("portfolio_ref", sa.String(80)),
        sa.Column("company_ref", sa.String(40)),
        sa.Column("endpoint", sa.String(200), nullable=False),
        sa.Column("required_scope", sa.String(80), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("trace_id", sa.String(128), nullable=False),
        sa.Column("result", sa.String(10), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("authorization_reference", sa.String(160)),
        sa.Column("purpose", sa.String(120)),
        sa.Column("safe_details", sa.Text()),
        sa.CheckConstraint("result IN ('ALLOW','DENY')", name="ck_fi_access_audit_result"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_fi_audit_consumer_time",
        "access_audit",
        ["consumer_id", "occurred_at"],
        schema=SCHEMA,
    )
    op.create_index("ix_fi_audit_trace", "access_audit", ["trace_id"], schema=SCHEMA)
    op.create_index(
        "ix_fi_audit_subject_time",
        "access_audit",
        ["subject_id", "occurred_at"],
        schema=SCHEMA,
    )

    # Defense in depth for append-only audit. The service role can INSERT/SELECT but
    # UPDATE/DELETE/TRUNCATE are denied by triggers even if a future grant is too broad.
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {SCHEMA}.reject_access_audit_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
              IF TG_OP = 'TRUNCATE'
                 AND current_setting('boa.allow_fi_audit_truncate', true) = 'true' THEN
                RETURN NULL;
              END IF;
              RAISE EXCEPTION 'financial intelligence access audit is append-only';
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER trg_fi_access_audit_append_only
            BEFORE UPDATE OR DELETE ON {SCHEMA}.access_audit
            FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.reject_access_audit_mutation()
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER trg_fi_access_audit_no_truncate
            BEFORE TRUNCATE ON {SCHEMA}.access_audit
            FOR EACH STATEMENT EXECUTE FUNCTION {SCHEMA}.reject_access_audit_mutation()
            """
        )
    )


def downgrade() -> None:
    # A downgrade destroys authorization and audit evidence. It must be explicitly opted into.
    bind = op.get_bind()
    allow_destructive = bind.execute(
        sa.text("SELECT current_setting('boa.allow_fi_destructive_downgrade', true)")
    ).scalar_one_or_none()
    if allow_destructive != "true":
        raise RuntimeError(
            "Refusing destructive FI downgrade. Set "
            "boa.allow_fi_destructive_downgrade=true in this migration session after backup."
        )
    op.execute(sa.text(f"DROP TRIGGER trg_fi_access_audit_no_truncate ON {SCHEMA}.access_audit"))
    op.execute(sa.text(f"DROP TRIGGER trg_fi_access_audit_append_only ON {SCHEMA}.access_audit"))
    op.execute(sa.text(f"DROP FUNCTION {SCHEMA}.reject_access_audit_mutation()"))
    op.drop_table("access_audit", schema=SCHEMA)
    op.drop_table("data_access_grants", schema=SCHEMA)
    op.drop_table("external_portfolio_companies", schema=SCHEMA)
    op.drop_table("external_portfolios", schema=SCHEMA)
    op.drop_table("external_consumers", schema=SCHEMA)
    op.execute(sa.text(f"DROP SCHEMA IF EXISTS {SCHEMA}"))
