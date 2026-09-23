from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from boa_oi.models.base import Base, UUIDPrimaryKeyMixin


class ExternalConsumer(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "external_consumers"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','SUSPENDED','CLOSED')", name="status"),
        CheckConstraint("consumer_type IN ('FUND','HOLDING','PARTNER')", name="type"),
        Index("ix_fi_consumers_status", "status"),
        {"schema": "financial_intelligence"},
    )

    consumer_ref: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    consumer_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    allowed_scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    synthetic_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ExternalPortfolio(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "external_portfolios"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','SUSPENDED','CLOSED')", name="status"),
        UniqueConstraint("id", "consumer_id", name="uq_fi_portfolio_id_consumer"),
        UniqueConstraint("consumer_id", "portfolio_ref", name="uq_fi_portfolio_consumer_ref"),
        Index("ix_fi_portfolios_consumer_status", "consumer_id", "status"),
        {"schema": "financial_intelligence"},
    )

    consumer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("financial_intelligence.external_consumers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    portfolio_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    fund_ref: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ExternalPortfolioCompany(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "external_portfolio_companies"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="status"),
        CheckConstraint("valid_until IS NULL OR valid_until > valid_from", name="validity"),
        CheckConstraint(
            "status <> 'INACTIVE' OR valid_until IS NOT NULL",
            name="inactive_requires_valid_until",
        ),
        UniqueConstraint("portfolio_id", "company_ref", name="uq_fi_portfolio_company"),
        Index(
            "ix_fi_portfolio_companies_company_status",
            "company_ref",
            "status",
            "valid_from",
            "valid_until",
        ),
        {"schema": "financial_intelligence"},
    )

    portfolio_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("financial_intelligence.external_portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_ref: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DataAccessGrant(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "data_access_grants"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','EXPIRED','REVOKED')", name="status"),
        CheckConstraint("valid_until > valid_from", name="validity"),
        CheckConstraint(
            "purpose = 'SYNTHETIC_PORTFOLIO_MONITORING'",
            name="purpose",
        ),
        CheckConstraint(
            "(status = 'REVOKED' AND revoked_at IS NOT NULL) OR "
            "(status <> 'REVOKED' AND revoked_at IS NULL)",
            name="revocation_state",
        ),
        ForeignKeyConstraint(
            ["portfolio_id", "consumer_id"],
            [
                "financial_intelligence.external_portfolios.id",
                "financial_intelligence.external_portfolios.consumer_id",
            ],
            name="fk_fi_grant_portfolio_consumer",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "consumer_id",
            "subject_id",
            "client_id",
            "portfolio_id",
            "scope",
            "purpose",
            "valid_from",
            name="uq_fi_grant_subject_portfolio_scope_from",
        ),
        Index(
            "ix_fi_grants_subject_status_validity",
            "subject_id",
            "client_id",
            "status",
            "valid_from",
            "valid_until",
        ),
        Index("ix_fi_grants_portfolio_scope", "portfolio_id", "scope"),
        {"schema": "financial_intelligence"},
    )

    grant_ref: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    consumer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("financial_intelligence.external_consumers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    portfolio_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    subject_id: Mapped[str] = mapped_column(String(120), nullable=False)
    client_id: Mapped[str] = mapped_column(String(120), nullable=False)
    scope: Mapped[str] = mapped_column(String(80), nullable=False)
    purpose: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authorization_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FinancialIntelligenceAccessAudit(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "access_audit"
    __table_args__ = (
        CheckConstraint("result IN ('ALLOW','DENY')", name="result"),
        Index("ix_fi_audit_consumer_time", "consumer_id", "occurred_at"),
        Index("ix_fi_audit_trace", "trace_id"),
        Index("ix_fi_audit_subject_time", "subject_id", "occurred_at"),
        {"schema": "financial_intelligence"},
    )

    consumer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    subject_id: Mapped[str | None] = mapped_column(String(120))
    client_id: Mapped[str | None] = mapped_column(String(120))
    portfolio_ref: Mapped[str | None] = mapped_column(String(80))
    company_ref: Mapped[str | None] = mapped_column(String(40))
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    required_scope: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    result: Mapped[str] = mapped_column(String(10), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    authorization_reference: Mapped[str | None] = mapped_column(String(160))
    purpose: Mapped[str | None] = mapped_column(String(120))
    safe_details: Mapped[str | None] = mapped_column(Text)


__all__ = [
    "DataAccessGrant",
    "ExternalConsumer",
    "ExternalPortfolio",
    "ExternalPortfolioCompany",
    "FinancialIntelligenceAccessAudit",
]
