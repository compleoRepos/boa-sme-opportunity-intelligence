from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Sector(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "sectors"
    __table_args__ = {"schema": "customer"}
    code: Mapped[str] = mapped_column(String(40), unique=True)
    label: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class RelationshipManager(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "relationship_managers"
    __table_args__ = {"schema": "customer"}
    subject_id: Mapped[str] = mapped_column(String(120), unique=True)
    display_name: Mapped[str] = mapped_column(String(160))
    branch_code: Mapped[str] = mapped_column(String(30))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Customer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','SUSPENDED','CLOSED')", name="status"),
        Index(
            "ix_customers_status_sector_segment",
            "status",
            "sector_code",
            "segment_code",
        ),
        {"schema": "customer"},
    )
    customer_ref: Mapped[str] = mapped_column(String(20), unique=True)
    legal_name: Mapped[str] = mapped_column(String(180))
    sector_code: Mapped[str] = mapped_column(String(40))
    segment_code: Mapped[str] = mapped_column(String(20))
    scenario_code: Mapped[str] = mapped_column(String(40))
    incorporated_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    banking_relationship: Mapped[str | None] = mapped_column(String(20))
    banking_relationship_declared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    banking_relationship_declared_by: Mapped[str | None] = mapped_column(String(120))
    banking_relationship_reason: Mapped[str | None] = mapped_column(Text)
    banking_relationship_source: Mapped[str | None] = mapped_column(String(30))
    declared_turnover: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    declared_turnover_as_of: Mapped[date | None] = mapped_column(Date)
    declared_turnover_entered_by: Mapped[str | None] = mapped_column(String(120))
    declared_turnover_source: Mapped[str | None] = mapped_column(String(30))
    rm_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customer.relationship_managers.id")
    )


class CustomerBankingDeclaration(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "banking_relationship_declarations"
    __table_args__ = (
        Index(
            "ix_banking_declarations_customer_time",
            "customer_id",
            "declared_at",
        ),
        {"schema": "customer"},
    )
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customer.customers.id")
    )
    banking_relationship: Mapped[str] = mapped_column(String(20))
    declared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    declared_by: Mapped[str] = mapped_column(String(120))
    reason: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30))
    declared_turnover: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    declared_turnover_as_of: Mapped[date | None] = mapped_column(Date)
    declared_turnover_source: Mapped[str | None] = mapped_column(String(30))


class PortfolioAssignment(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "portfolio_assignments"
    __table_args__ = (
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="validity"),
        CheckConstraint("assignment_type IN ('PRIMARY')", name="assignment_type"),
        UniqueConstraint("source_system", "source_event_id"),
        Index(
            "uq_portfolio_assignments_active_customer",
            "customer_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
            sqlite_where=text("valid_to IS NULL"),
        ),
        Index(
            "ix_portfolio_assignments_rm_validity",
            "relationship_manager_id",
            "valid_from",
            "valid_to",
        ),
        Index(
            "ix_portfolio_assignments_branch_validity",
            "branch_code",
            "valid_from",
            "valid_to",
        ),
        {"schema": "customer"},
    )
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customer.customers.id", ondelete="CASCADE")
    )
    relationship_manager_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer.relationship_managers.id", ondelete="RESTRICT"),
    )
    branch_code: Mapped[str] = mapped_column(String(30))
    portfolio_id: Mapped[str] = mapped_column(String(80), default="LEGACY")
    assignment_type: Mapped[str] = mapped_column(String(20), default="PRIMARY")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_system: Mapped[str | None] = mapped_column(String(40))
    source_event_id: Mapped[str | None] = mapped_column(String(120))
    source_payload_hash: Mapped[str | None] = mapped_column(String(64))
    source_watermark: Mapped[str | None] = mapped_column(String(120))
    actor: Mapped[str] = mapped_column(String(120))
    reason: Mapped[str] = mapped_column(Text)


class Account(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("account_type IN ('CURRENT','SAVINGS','CREDIT')", name="type"),
        Index("ix_accounts_customer_status", "customer_id", "status"),
        {"schema": "account"},
    )
    account_ref: Mapped[str] = mapped_column(String(34), unique=True)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    account_type: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3))
    opened_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")


class CreditLine(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "credit_lines"
    __table_args__ = (
        CheckConstraint("approved_limit > 0", name="positive_limit"),
        {"schema": "account"},
    )
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("account.accounts.id")
    )
    facility_type: Mapped[str] = mapped_column(String(40))
    approved_limit: Mapped[Decimal] = mapped_column(Numeric(19, 4))
    currency: Mapped[str] = mapped_column(String(3))
    valid_from: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")


class AccountBalance(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "account_balances"
    __table_args__ = (
        UniqueConstraint("account_id", "as_of_date"),
        Index("ix_balances_account_date", "account_id", "as_of_date"),
        {"schema": "account"},
    )
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("account.accounts.id")
    )
    as_of_date: Mapped[date] = mapped_column(Date)
    closing_balance: Mapped[Decimal] = mapped_column(Numeric(19, 4))
    available_balance: Mapped[Decimal] = mapped_column(Numeric(19, 4))
    credit_used: Mapped[Decimal] = mapped_column(Numeric(19, 4), default=0)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(19, 4), default=0)
    currency: Mapped[str] = mapped_column(String(3))


class Counterparty(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "counterparties"
    __table_args__ = {"schema": "transaction"}
    counterparty_ref_hash: Mapped[str] = mapped_column(String(64), unique=True)
    display_name_synthetic: Mapped[str] = mapped_column(String(160))
    country_code: Mapped[str] = mapped_column(String(2))
    counterparty_type: Mapped[str] = mapped_column(String(20))
    is_supplier: Mapped[bool] = mapped_column(Boolean, default=False)


class Transaction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount"),
        CheckConstraint("direction IN ('CREDIT','DEBIT')", name="direction"),
        UniqueConstraint("source_system", "transaction_ref"),
        Index("ix_tx_customer_date", "customer_id", "value_date"),
        Index("ix_tx_account_date", "account_id", "value_date"),
        Index("ix_tx_customer_int_date", "customer_id", "is_international", "value_date"),
        Index("ix_tx_customer_category_date", "customer_id", "category", "value_date"),
        Index("ix_transactions_import_batch", "import_batch_id"),
        {"schema": "transaction"},
    )
    transaction_ref: Mapped[str] = mapped_column(String(80))
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    booked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    value_date: Mapped[date] = mapped_column(Date)
    direction: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4))
    currency: Mapped[str] = mapped_column(String(3))
    transaction_type: Mapped[str] = mapped_column(String(30))
    category: Mapped[str] = mapped_column(String(40))
    is_international: Mapped[bool] = mapped_column(Boolean, default=False)
    country_code: Mapped[str] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(20), default="BOOKED")
    source_system: Mapped[str] = mapped_column(String(40), default="MOCK_PAYMENTS")
    counterparty_name: Mapped[str | None] = mapped_column(String(180))
    remittance_information: Mapped[str | None] = mapped_column(String(500))
    externally_domiciled: Mapped[bool] = mapped_column(Boolean, default=False)
    import_batch_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("integration.import_batches.id")
    )
    source_record_hash: Mapped[str | None] = mapped_column(String(64))
    category_version: Mapped[str | None] = mapped_column(String(30))


class TransactionCategory(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "transaction_categories"
    __table_args__ = (
        UniqueConstraint("category_code", "version"),
        Index("ix_transaction_categories_active", "category_code", "active"),
        CheckConstraint(
            "provenance IN ('SYNTHETIC_POC','BOA_APPROVED','EXTERNAL_CONTRACT')",
            name="provenance",
        ),
        {"schema": "config"},
    )
    category_code: Mapped[str] = mapped_column(String(40))
    version: Mapped[str] = mapped_column(String(30))
    label: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    provenance: Mapped[str] = mapped_column(String(30))
    checksum: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(120))


class Product(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "products"
    __table_args__ = {"schema": "product"}
    product_code: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(60))
    family: Mapped[str] = mapped_column(String(80), nullable=False, default="UNCLASSIFIED")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_url: Mapped[str | None] = mapped_column(String(500))
    eligibility_rules_json: Mapped[dict] = mapped_column(JSON, default=dict)
    target_segments_json: Mapped[list] = mapped_column(JSON, default=list)
    currencies_json: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CustomerProduct(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "customer_products"
    __table_args__ = (
        Index("ix_customer_products_customer_status", "customer_id", "status"),
        {"schema": "product"},
    )
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("product.products.id")
    )
    status: Mapped[str] = mapped_column(String(20))
    opened_on: Mapped[date] = mapped_column(Date)
    utilization_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))


class CustomerImportReceipt(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "import_receipts"
    __table_args__ = {"schema": "customer"}
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    correlation_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PortfolioSyncReceipt(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "portfolio_sync_receipts"
    __table_args__ = (
        UniqueConstraint("source_system", "batch_ref"),
        {"schema": "customer"},
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    source_system: Mapped[str] = mapped_column(String(40))
    batch_ref: Mapped[str] = mapped_column(String(120))
    source_watermark: Mapped[str | None] = mapped_column(String(120))
    row_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    response_json: Mapped[dict] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PortfolioSyncEvent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "portfolio_sync_events"
    __table_args__ = (
        UniqueConstraint("source_system", "source_event_id"),
        Index("ix_portfolio_sync_events_batch", "source_system", "batch_ref"),
        {"schema": "customer"},
    )
    source_system: Mapped[str] = mapped_column(String(40))
    source_event_id: Mapped[str] = mapped_column(String(120))
    batch_ref: Mapped[str] = mapped_column(String(120))
    payload_hash: Mapped[str] = mapped_column(String(64))
    customer_ref: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    assignment_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    correlation_id: Mapped[str] = mapped_column(String(100))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AccountImportReceipt(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "import_receipts"
    __table_args__ = {"schema": "account"}
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    correlation_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TransactionImportReceipt(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "import_receipts"
    __table_args__ = {"schema": "transaction"}
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    correlation_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProductImportReceipt(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "import_receipts"
    __table_args__ = {"schema": "product"}
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    correlation_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MetricSnapshot(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "metric_snapshots"
    __table_args__ = (
        UniqueConstraint("customer_id", "as_of_date", "window_days", "calculation_version"),
        Index(
            "ix_metrics_customer_date_window",
            "customer_id",
            "as_of_date",
            "window_days",
        ),
        {"schema": "analytics"},
    )
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    as_of_date: Mapped[date] = mapped_column(Date)
    window_days: Mapped[int] = mapped_column(SmallInteger)
    calculation_version: Mapped[str] = mapped_column(String(30))
    values_json: Mapped[dict] = mapped_column(JSON)
    input_watermark: Mapped[str] = mapped_column(String(100))


class MetricDefinition(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "metric_definitions"
    __table_args__ = {"schema": "analytics"}
    metric_code: Mapped[str] = mapped_column(String(80), unique=True)
    unit: Mapped[str] = mapped_column(String(20))
    aggregation: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class FlowVisibilitySnapshot(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "flow_visibility_snapshots"
    __table_args__ = (
        UniqueConstraint("customer_id", "as_of_date", "calculation_version"),
        Index("ix_flow_visibility_customer_asof", "customer_id", "as_of_date"),
        {"schema": "analytics"},
    )
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    customer_ref: Mapped[str] = mapped_column(String(40))
    as_of_date: Mapped[date] = mapped_column(Date)
    level: Mapped[str] = mapped_column(String(20))
    estimated_share: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    method: Mapped[str] = mapped_column(String(40))
    evidence_json: Mapped[list] = mapped_column(JSON, default=list)
    fingerprint_count_90d: Mapped[int] = mapped_column(Integer, default=0)
    fingerprint_previous_90d: Mapped[int] = mapped_column(Integer, default=0)
    categorization_coverage: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=0)
    calculation_version: Mapped[str] = mapped_column(String(40))
    input_watermark: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(120))


class FlowVisibilityPolicy(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "flow_visibility_policies"
    __table_args__ = (
        UniqueConstraint("policy_id", "version"),
        Index(
            "uq_flow_visibility_policy_active",
            "policy_id",
            unique=True,
            postgresql_where=text("active = true"),
            sqlite_where=text("active = 1"),
        ),
        {"schema": "analytics"},
    )
    policy_id: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    configuration_json: Mapped[dict] = mapped_column(JSON)
    justification: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(120))


class MetricValue(Base):
    __tablename__ = "metric_values"
    __table_args__ = {"schema": "analytics"}
    snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("analytics.metric_snapshots.id"),
        primary_key=True,
    )
    metric_definition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("analytics.metric_definitions.id"),
        primary_key=True,
    )
    current_value: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    previous_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    growth_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 10))
    baseline_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    sample_size: Mapped[int] = mapped_column(Integer)
    data_coverage: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    quality_status: Mapped[str] = mapped_column(String(30))


class SignalRule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "signal_rules"
    __table_args__ = (UniqueConstraint("rule_code", "version"), {"schema": "signal"})
    rule_code: Mapped[str] = mapped_column(String(80))
    version: Mapped[str] = mapped_column(String(30))
    configuration_json: Mapped[dict] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Signal(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "signals"
    __table_args__ = (
        Index("ix_signals_customer_detected", "customer_id", "detected_at"),
        Index("ix_signals_type_detected", "signal_type", "detected_at"),
        {"schema": "signal"},
    )
    signal_ref: Mapped[str] = mapped_column(String(80), unique=True)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    customer_ref: Mapped[str] = mapped_column(String(40), default="UNKNOWN")
    signal_type: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(10))
    value: Mapped[Decimal] = mapped_column(Numeric(18, 10))
    threshold: Mapped[Decimal] = mapped_column(Numeric(18, 10))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence_json: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))


class OpportunityRule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "opportunity_rules"
    __table_args__ = (
        UniqueConstraint("opportunity_type", "version"),
        {"schema": "opportunity"},
    )
    opportunity_type: Mapped[str] = mapped_column(String(80))
    version: Mapped[str] = mapped_column(String(30))
    configuration_json: Mapped[dict] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Opportunity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint("confidence_score BETWEEN 0 AND 1", name="confidence"),
        CheckConstraint("priority_score BETWEEN 0 AND 100", name="priority"),
        CheckConstraint(
            "status IN ('OPEN','ACCEPTED','CONTACTED','CONVERTED',"
            "'DISMISSED','DEFERRED','EXPIRED')",
            name="lifecycle",
        ),
        UniqueConstraint("deduplication_key"),
        Index(
            "ix_opportunities_active_priority",
            "status",
            "priority_level",
            "priority_score",
            "generated_at",
        ),
        Index(
            "ix_opportunities_customer_type_status",
            "customer_id",
            "opportunity_type",
            "status",
        ),
        Index("ix_opportunities_expiration", "status", "expires_at"),
        Index("ix_opportunities_cooldown", "customer_id", "opportunity_type", "cooldown_until"),
        {"schema": "opportunity"},
    )
    opportunity_ref: Mapped[str] = mapped_column(String(80), unique=True)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    customer_ref: Mapped[str] = mapped_column(String(40), default="UNKNOWN")
    customer_name: Mapped[str] = mapped_column(String(180), default="Synthetic SME")
    opportunity_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    status_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status_reason: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    horizon: Mapped[str] = mapped_column(String(30))
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    confidence_level: Mapped[str] = mapped_column(String(10))
    confidence_components_json: Mapped[list] = mapped_column(JSON)
    priority_score: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    priority_level: Mapped[str] = mapped_column(String(4))
    priority_components_json: Mapped[list] = mapped_column(JSON)
    why_json: Mapped[list] = mapped_column(JSON, default=list)
    what_text: Mapped[str] = mapped_column(Text, default="")
    when_text: Mapped[str] = mapped_column(Text, default="")
    recommended_products_json: Mapped[list] = mapped_column(JSON, default=list)
    recommendation_nature: Mapped[str] = mapped_column(
        String(30), default="NEED_DISCOVERY", server_default="NEED_DISCOVERY"
    )
    explanation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    engine_version: Mapped[str] = mapped_column(String(100), default="0.1.0")
    rule_version: Mapped[str] = mapped_column(String(80), default="1")
    scoring_policy_id: Mapped[str] = mapped_column(
        String(80), default="commercial-rules-shadow-poc"
    )
    scoring_policy_version: Mapped[int] = mapped_column(Integer, default=1)
    rules_weight: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("1"))
    ml_weight: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0"))
    fallback_mode: Mapped[str] = mapped_column(String(20), default="RULES_ONLY")
    fallback_cause_json: Mapped[dict | None] = mapped_column(JSON)
    rule_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("opportunity.opportunity_rules.id")
    )
    deduplication_key: Mapped[str] = mapped_column(String(160))


class OpportunityEvidence(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "opportunity_evidence"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "position"),
        {"schema": "opportunity"},
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("opportunity.opportunities.id")
    )
    metric_code: Mapped[str] = mapped_column(String(80))
    observed_value: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    threshold: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    comparison_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    why_text: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(SmallInteger)


class OpportunityRecommendation(Base):
    __tablename__ = "opportunity_recommendations"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "rank"),
        {"schema": "opportunity"},
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("opportunity.opportunities.id"),
        primary_key=True,
    )
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    rank: Mapped[int] = mapped_column(SmallInteger)
    reason_code: Mapped[str] = mapped_column(String(80))
    recommended: Mapped[bool] = mapped_column(Boolean, default=True)


class OpportunityAction(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "opportunity_actions"
    __table_args__ = (
        UniqueConstraint("idempotency_key"),
        CheckConstraint(
            "transition_status IN ('NOT_REQUIRED','PENDING','APPLIED','FAILED')",
            name="ck_action_transition_status",
        ),
        Index("ix_actions_opportunity_created", "opportunity_id", "created_at"),
        Index("ix_actions_transition_status_updated", "transition_status", "updated_at"),
        {"schema": "action"},
    )
    action_ref: Mapped[str] = mapped_column(String(80), unique=True)
    opportunity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    opportunity_ref: Mapped[str] = mapped_column(String(80))
    opportunity_type: Mapped[str | None] = mapped_column(String(80))
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    customer_ref: Mapped[str] = mapped_column(String(40))
    action_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    actor_subject_id: Mapped[str] = mapped_column(String(120))
    assigned_to: Mapped[str | None] = mapped_column(String(120))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    performed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes_redacted: Mapped[str | None] = mapped_column(Text)
    outcome_type: Mapped[str | None] = mapped_column(String(40))
    transition_status: Mapped[str] = mapped_column(
        String(20), default="NOT_REQUIRED", server_default="NOT_REQUIRED"
    )
    transition_target: Mapped[str | None] = mapped_column(String(20))
    transition_command_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    transition_attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    transition_error: Mapped[str | None] = mapped_column(Text)
    transition_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pending_outcome_type: Mapped[str | None] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    correlation_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ActionOutcome(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "action_outcomes"
    __table_args__ = (
        Index("ix_action_outcomes_action_time", "action_id", "recorded_at"),
        {"schema": "action"},
    )
    action_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    outcome_type: Mapped[str] = mapped_column(String(40))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    recorded_by: Mapped[str] = mapped_column(String(120))
    correlation_id: Mapped[str] = mapped_column(String(100))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class AuditLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_resource_time", "resource_type", "resource_id", "occurred_at"),
        Index("ix_audit_correlation", "correlation_id"),
        {"schema": "audit"},
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    actor_subject_id: Mapped[str | None] = mapped_column(String(120))
    service_name: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(80))
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(100))
    correlation_id: Mapped[str] = mapped_column(String(100))
    result: Mapped[str] = mapped_column(String(30))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class DecisionAudit(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "decision_audit"
    __table_args__ = {"schema": "opportunity"}
    opportunity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    engine_version: Mapped[str] = mapped_column(String(100))
    rule_version: Mapped[str] = mapped_column(String(80))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input_reference: Mapped[str] = mapped_column(String(120))
    signals_json: Mapped[list] = mapped_column(JSON)
    metric_snapshots_json: Mapped[list] = mapped_column(JSON)
    confidence_components_json: Mapped[list] = mapped_column(JSON)
    priority_components_json: Mapped[list] = mapped_column(JSON)
    scoring_policy_id: Mapped[str] = mapped_column(
        String(80), default="commercial-rules-shadow-poc"
    )
    scoring_policy_version: Mapped[int] = mapped_column(Integer, default=1)
    fallback_mode: Mapped[str] = mapped_column(String(20), default="RULES_ONLY")
    fallback_cause_json: Mapped[dict | None] = mapped_column(JSON)
    decision_hash: Mapped[str] = mapped_column(String(64), unique=True)


class ScoringPolicy(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "scoring_policies"
    __table_args__ = ({"schema": "opportunity"},)
    policy_id: Mapped[str] = mapped_column(String(80), unique=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    active_version: Mapped[int | None] = mapped_column(Integer)


class ScoringPolicyVersion(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "scoring_policy_versions"
    __table_args__ = (
        UniqueConstraint("policy_id", "version"),
        CheckConstraint("rules_weight BETWEEN 0 AND 1", name="rules_weight"),
        CheckConstraint("ml_weight BETWEEN 0 AND 1", name="ml_weight"),
        CheckConstraint("rules_weight + ml_weight = 1", name="normalized_weights"),
        CheckConstraint(
            "status IN ('DRAFT','SIMULATED','SUBMITTED','APPROVED','PUBLISHED',"
            "'ACTIVE','DISABLED','ROLLED_BACK')",
            name="status",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from",
            name="effective_window",
        ),
        Index("ix_scoring_policy_versions_status", "status", "effective_from"),
        Index(
            "uq_scoring_policy_single_active",
            "status",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
        {"schema": "opportunity"},
    )
    policy_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("opportunity.scoring_policies.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer)
    rules_weight: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    ml_weight: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    author_id: Mapped[str] = mapped_column(String(120))
    approver_id: Mapped[str | None] = mapped_column(String(120))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_reason: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    simulation_id: Mapped[str | None] = mapped_column(String(100))
    checksum: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ScoringPolicyAuditLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "scoring_policy_audit_logs"
    __table_args__ = (
        Index("ix_scoring_policy_audit_policy_time", "policy_id", "timestamp"),
        {"schema": "opportunity"},
    )
    policy_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("opportunity.scoring_policies.id", ondelete="RESTRICT")
    )
    policy_version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(40))
    user_id: Mapped[str] = mapped_column(String(120))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    old_value_json: Mapped[dict | None] = mapped_column(JSON)
    new_value_json: Mapped[dict | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str] = mapped_column(String(100))


class RuleConfiguration(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "rule_configurations"
    __table_args__ = (
        UniqueConstraint("config_id", "rule_set_version"),
        {"schema": "config"},
    )
    config_id: Mapped[str] = mapped_column(String(80))
    engine_version: Mapped[str] = mapped_column(String(30))
    rule_set_version: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20))
    effective_from: Mapped[date] = mapped_column(Date)
    configuration_json: Mapped[dict] = mapped_column(JSON)
    checksum: Mapped[str] = mapped_column(String(64), unique=True)
    approved_by: Mapped[str] = mapped_column(String(120))


class LabelCatalogEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "label_catalog"
    __table_args__ = (
        UniqueConstraint("code", "locale"),
        CheckConstraint("current_version > 0", name="positive_current_version"),
        {"schema": "config"},
    )
    namespace: Mapped[str] = mapped_column(String(40))
    code: Mapped[str] = mapped_column(String(100))
    locale: Mapped[str] = mapped_column(String(10), default="fr-FR")
    label: Mapped[str] = mapped_column(String(180))
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[str] = mapped_column(String(120))
    justification: Mapped[str] = mapped_column(Text)


class LabelCatalogVersion(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "label_catalog_versions"
    __table_args__ = (
        UniqueConstraint("catalog_entry_id", "version"),
        CheckConstraint("version > 0", name="positive_version"),
        Index("ix_label_catalog_version_created", "catalog_entry_id", "created_at"),
        {"schema": "config"},
    )
    catalog_entry_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("config.label_catalog.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(180))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(120))
    justification: Mapped[str] = mapped_column(Text)


class Rule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "rules"
    __table_args__ = (
        CheckConstraint("current_version > 0", name="positive_current_version"),
        CheckConstraint(
            "status IN ('DRAFT','VALIDATED','SIMULATED','SUBMITTED','APPROVED',"
            "'PUBLISHED','ACTIVE','DISABLED','RETIRED')",
            name="status",
        ),
        Index("ix_rules_status_updated", "status", "updated_at"),
        {"schema": "rule"},
    )
    rule_id: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    active_version: Mapped[int | None] = mapped_column(Integer)
    disabled_reason: Mapped[str | None] = mapped_column(Text)


class RuleVersion(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "rule_versions"
    __table_args__ = (
        UniqueConstraint("rule_id", "version"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint(
            "status IN ('DRAFT','VALIDATED','SIMULATED','SUBMITTED','APPROVED',"
            "'PUBLISHED','ACTIVE','DISABLED','RETIRED')",
            name="status",
        ),
        Index("ix_rule_versions_rule_status", "rule_id", "status"),
        {"schema": "rule"},
    )
    rule_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("rule.rules.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    scope_json: Mapped[dict] = mapped_column(JSON, default=dict)
    logic: Mapped[str] = mapped_column(String(10), default="AND")
    configuration_json: Mapped[dict] = mapped_column(JSON)
    checksum: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class RuleCondition(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "rule_conditions"
    __table_args__ = (
        UniqueConstraint("rule_version_id", "path"),
        Index("ix_rule_conditions_version_position", "rule_version_id", "position"),
        {"schema": "rule"},
    )
    rule_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("rule.rule_versions.id", ondelete="CASCADE")
    )
    parent_condition_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("rule.rule_conditions.id", ondelete="CASCADE")
    )
    path: Mapped[str] = mapped_column(String(240))
    position: Mapped[int] = mapped_column(Integer)
    node_type: Mapped[str] = mapped_column(String(20))
    logic: Mapped[str | None] = mapped_column(String(10))
    metric_code: Mapped[str | None] = mapped_column(String(80))
    operator: Mapped[str | None] = mapped_column(String(30))
    value_json: Mapped[Any | None] = mapped_column(JSON)
    unit: Mapped[str | None] = mapped_column(String(30))
    period: Mapped[str | None] = mapped_column(String(30))


class RuleAction(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "rule_actions"
    __table_args__ = (
        UniqueConstraint("rule_version_id", "position"),
        {"schema": "rule"},
    )
    rule_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("rule.rule_versions.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    opportunity_type_code: Mapped[str] = mapped_column(String(80))
    product_codes_json: Mapped[list] = mapped_column(JSON, default=list)
    horizon_code: Mapped[str | None] = mapped_column(String(30))


class RuleConfidenceConfiguration(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "rule_confidence_configurations"
    __table_args__ = (
        UniqueConstraint("rule_version_id"),
        CheckConstraint("base_score BETWEEN 0 AND 1", name="base_score_range"),
        {"schema": "rule"},
    )
    rule_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("rule.rule_versions.id", ondelete="CASCADE")
    )
    base_score: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=0)
    weights_json: Mapped[dict] = mapped_column(JSON, default=dict)


class RuleApproval(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "rule_approvals"
    __table_args__ = (
        UniqueConstraint("rule_version_id", "decision"),
        CheckConstraint("decision IN ('SUBMITTED','APPROVED','REJECTED')", name="decision"),
        {"schema": "rule"},
    )
    rule_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("rule.rule_versions.id", ondelete="CASCADE")
    )
    decision: Mapped[str] = mapped_column(String(20))
    actor_subject_id: Mapped[str] = mapped_column(String(120))
    reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RuleSimulation(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "rule_simulations"
    __table_args__ = (
        Index("ix_rule_simulations_version_created", "rule_version_id", "created_at"),
        {"schema": "rule"},
    )
    rule_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("rule.rule_versions.id", ondelete="CASCADE")
    )
    period_from: Mapped[date] = mapped_column(Date)
    period_to: Mapped[date] = mapped_column(Date)
    population_json: Mapped[dict] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)


class RuleAuditLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "rule_audit_logs"
    __table_args__ = (
        CheckConstraint(
            "action IN ('CREATED','UPDATED','VALIDATED','SIMULATED','SUBMITTED',"
            "'APPROVED','PUBLISHED','ACTIVATED','DISABLED','RETIRED','ROLLED_BACK')",
            name="action",
        ),
        Index("ix_rule_audit_rule_time", "rule_id", "timestamp"),
        {"schema": "rule"},
    )
    rule_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("rule.rules.id", ondelete="RESTRICT")
    )
    rule_version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(30))
    user_id: Mapped[str] = mapped_column(String(120))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    old_value_json: Mapped[dict | None] = mapped_column(JSON)
    new_value_json: Mapped[dict | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)


class ImportBatch(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "import_batches"
    __table_args__ = (
        UniqueConstraint("source_system", "batch_ref"),
        {"schema": "integration"},
    )
    source_system: Mapped[str] = mapped_column(String(40))
    batch_ref: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_hash: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    correlation_id: Mapped[str] = mapped_column(String(100))
    contract_version: Mapped[str | None] = mapped_column(String(20))
    external_batch_id: Mapped[str | None] = mapped_column(String(120))
    source_watermark: Mapped[str | None] = mapped_column(String(120))
    produced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expected_row_count: Mapped[int | None] = mapped_column(Integer)
    received_row_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    accepted_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rejected_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    quarantined_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    quality_status: Mapped[str] = mapped_column(
        String(20), default="UNKNOWN", server_default="UNKNOWN"
    )
    freshness_status: Mapped[str] = mapped_column(
        String(20), default="UNKNOWN", server_default="UNKNOWN"
    )
    freshness_lag_seconds: Mapped[int | None] = mapped_column(Integer)
    quality_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")


class ImportRejectedRecord(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "import_rejections"
    __table_args__ = (
        UniqueConstraint("batch_id", "domain", "row_number"),
        Index("ix_import_rejections_batch_status", "batch_id", "status"),
        CheckConstraint("status IN ('QUARANTINED','RESOLVED','DISMISSED')", name="status"),
        {"schema": "integration"},
    )
    batch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("integration.import_batches.id", ondelete="RESTRICT")
    )
    domain: Mapped[str] = mapped_column(String(40))
    row_number: Mapped[int] = mapped_column(Integer)
    source_record_ref: Mapped[str | None] = mapped_column(String(120))
    row_hash: Mapped[str] = mapped_column(String(64))
    reason_code: Mapped[str] = mapped_column(String(80))
    field_name: Mapped[str | None] = mapped_column(String(80))
    safe_details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="QUARANTINED")
    correlation_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutboxMessage(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "outbox_messages"
    __table_args__ = (
        Index("ix_outbox_unpublished", "published_at", "occurred_at"),
        {"schema": "integration"},
    )
    event_type: Mapped[str] = mapped_column(String(100))
    aggregate_type: Mapped[str] = mapped_column(String(80))
    aggregate_id: Mapped[str] = mapped_column(String(100))
    payload_json: Mapped[dict] = mapped_column(JSON)
    correlation_id: Mapped[str] = mapped_column(String(100))
    causation_id: Mapped[str | None] = mapped_column(String(100))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    processing_status: Mapped[str | None] = mapped_column(String(20))
    processing_error: Mapped[str | None] = mapped_column(String(100))


class NotificationMessage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "notification_messages"
    __table_args__ = (
        UniqueConstraint("deduplication_key"),
        CheckConstraint(
            "status IN ('PENDING','SENDING','RETRY','SENT','DELIVERY_UNCERTAIN','DEAD_LETTER')",
            name="status",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
        CheckConstraint("max_attempts BETWEEN 1 AND 20", name="max_attempts_range"),
        Index("ix_notification_due", "status", "next_attempt_at", "created_at"),
        {"schema": "notification"},
    )
    deduplication_key: Mapped[str] = mapped_column(String(180))
    event_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    notification_type: Mapped[str] = mapped_column(String(80))
    recipient_email: Mapped[str] = mapped_column(String(254))
    recipient_name: Mapped[str | None] = mapped_column(String(160))
    subject: Mapped[str] = mapped_column(String(200))
    text_body: Mapped[str] = mapped_column(Text)
    html_body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    last_error: Mapped[str | None] = mapped_column(String(500))
    correlation_id: Mapped[str] = mapped_column(String(100))


class NotificationDigestSubscription(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "notification_digest_subscriptions"
    __table_args__ = (
        UniqueConstraint("relationship_manager_id"),
        CheckConstraint("delivery_hour BETWEEN 0 AND 23", name="delivery_hour_range"),
        {"schema": "notification"},
    )
    relationship_manager_id: Mapped[str] = mapped_column(String(120))
    recipient_email: Mapped[str] = mapped_column(String(254))
    timezone_name: Mapped[str] = mapped_column(String(80), default="Africa/Abidjan")
    delivery_hour: Mapped[int] = mapped_column(Integer, default=7)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_digest_date: Mapped[date | None] = mapped_column(Date)
    last_notification_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class NotificationDeliveryAttempt(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "notification_delivery_attempts"
    __table_args__ = (
        UniqueConstraint("notification_id", "attempt_number"),
        CheckConstraint("outcome IN ('SENT','FAILED','UNCERTAIN')", name="outcome"),
        Index("ix_notification_attempt_created", "notification_id", "attempted_at"),
        {"schema": "notification"},
    )
    notification_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("notification.notification_messages.id", ondelete="RESTRICT"),
    )
    attempt_number: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(20))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    error_redacted: Mapped[str | None] = mapped_column(String(500))
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FeatureMaterialization(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "feature_materializations"
    __table_args__ = (
        UniqueConstraint("customer_id", "as_of_date", "feature_set_version"),
        Index(
            "ix_feature_materializations_customer_as_of",
            "customer_id",
            "as_of_date",
        ),
        {"schema": "feature_store"},
    )
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    customer_ref: Mapped[str] = mapped_column(String(40))
    as_of_date: Mapped[date] = mapped_column(Date)
    feature_set_version: Mapped[str] = mapped_column(String(40))
    values_json: Mapped[dict] = mapped_column(JSON)
    sources_json: Mapped[list] = mapped_column(JSON)
    lineage_json: Mapped[list] = mapped_column(JSON, default=list)
    checksum: Mapped[str] = mapped_column(String(64))


class FeatureSetRegistry(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "feature_set_registry"
    __table_args__ = {"schema": "feature_store"}
    feature_set_version: Mapped[str] = mapped_column(String(40), unique=True)
    status: Mapped[str] = mapped_column(String(30))
    definition_json: Mapped[dict] = mapped_column(JSON)
    checksum: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(120))


class ModelRegistry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "model_registry"
    __table_args__ = (
        CheckConstraint(
            "status IN ('REGISTERED','VALIDATING','SUBMITTED','APPROVED','CHALLENGER',"
            "'CHAMPION','ACTIVE','RETIRED','DEMO_ONLY')",
            name="status",
        ),
        CheckConstraint("score_type = 'SALES_PROPENSITY'", name="score_type"),
        CheckConstraint("threshold BETWEEN 0 AND 1", name="threshold"),
        Index("ix_model_registry_status", "status"),
        {"schema": "ml"},
    )
    model_version: Mapped[str] = mapped_column(String(40), unique=True)
    model_id: Mapped[str] = mapped_column(String(80), default="sales-propensity")
    score_type: Mapped[str] = mapped_column(String(40), default="SALES_PROPENSITY")
    algorithm: Mapped[str] = mapped_column(String(40), default="LOGISTIC_REGRESSION")
    status: Mapped[str] = mapped_column(String(20))
    feature_set_version: Mapped[str] = mapped_column(String(40))
    feature_order_json: Mapped[list] = mapped_column(JSON)
    coefficients_json: Mapped[dict] = mapped_column(JSON)
    intercept: Mapped[Decimal] = mapped_column(Numeric(18, 10))
    threshold: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    validation_metrics_json: Mapped[dict] = mapped_column(JSON)
    training_dataset_version: Mapped[str] = mapped_column(String(80))
    training_code_version: Mapped[str] = mapped_column(String(80))
    deployment_mode: Mapped[str] = mapped_column(String(20), default="POC_SHADOW")
    target_outcome: Mapped[str] = mapped_column(String(80), default="ANY_COMMERCIAL_OPPORTUNITY")
    horizon_days: Mapped[int] = mapped_column(Integer, default=90)
    score_interpretation: Mapped[str] = mapped_column(String(30), default="RANKING_ONLY")
    calibration_status: Mapped[str] = mapped_column(String(30), default="NOT_VALIDATED")
    dataset_manifest_hash: Mapped[str | None] = mapped_column(String(64))
    artifact_checksum: Mapped[str | None] = mapped_column(String(64))
    contract_version: Mapped[str] = mapped_column(String(20), default="1.0")
    training_period_from: Mapped[date | None] = mapped_column(Date)
    training_period_to: Mapped[date | None] = mapped_column(Date)
    validation_period_from: Mapped[date | None] = mapped_column(Date)
    validation_period_to: Mapped[date | None] = mapped_column(Date)
    hyperparameters_json: Mapped[dict] = mapped_column(JSON, default=dict)
    approved_by: Mapped[str | None] = mapped_column(String(120))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PropensityScoreRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "propensity_scores"
    __table_args__ = (
        CheckConstraint("score_type = 'SALES_PROPENSITY'", name="score_type"),
        CheckConstraint("score BETWEEN 0 AND 1", name="score"),
        CheckConstraint("threshold BETWEEN 0 AND 1", name="threshold"),
        UniqueConstraint(
            "customer_id",
            "as_of_date",
            "model_version",
            "feature_checksum",
        ),
        Index("ix_propensity_scores_customer_as_of", "customer_id", "as_of_date"),
        {"schema": "ml"},
    )
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    customer_ref: Mapped[str] = mapped_column(String(40))
    as_of_date: Mapped[date] = mapped_column(Date)
    score_type: Mapped[str] = mapped_column(String(40), default="SALES_PROPENSITY")
    score: Mapped[Decimal] = mapped_column(Numeric(12, 10))
    threshold: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    above_threshold: Mapped[bool] = mapped_column(Boolean)
    score_band: Mapped[str] = mapped_column(String(20))
    segment: Mapped[str] = mapped_column(String(20))
    model_version: Mapped[str] = mapped_column(String(40))
    feature_set_version: Mapped[str] = mapped_column(String(40))
    feature_checksum: Mapped[str] = mapped_column(String(64))
    contributions_json: Mapped[list] = mapped_column(JSON)
    top_factors_json: Mapped[list] = mapped_column(JSON)
    training_dataset_version: Mapped[str] = mapped_column(String(80))
    deployment_mode: Mapped[str] = mapped_column(String(20), default="POC_SHADOW")
    prediction_trace_id: Mapped[str] = mapped_column(String(100), default="unknown")
    target_outcome: Mapped[str] = mapped_column(String(80), default="ANY_COMMERCIAL_OPPORTUNITY")
    horizon_days: Mapped[int] = mapped_column(Integer, default=90)
    opportunity_type: Mapped[str] = mapped_column(String(80), default="ANY_COMMERCIAL_OPPORTUNITY")
    score_interpretation: Mapped[str] = mapped_column(String(30), default="RANKING_ONLY")
    feature_snapshot_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    feature_watermark: Mapped[str | None] = mapped_column(String(120))
    valid_until: Mapped[date | None] = mapped_column(Date)
    contract_version: Mapped[str] = mapped_column(String(20), default="1.0")
    dataset_manifest_hash: Mapped[str | None] = mapped_column(String(64))
    artifact_checksum: Mapped[str | None] = mapped_column(String(64))


class OutcomeLabelSnapshot(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "outcome_label_snapshots"
    __table_args__ = (
        CheckConstraint("score_type = 'SALES_PROPENSITY'", name="score_type"),
        UniqueConstraint(
            "snapshot_version",
            "customer_id",
            "observation_as_of",
            "label_available_from",
        ),
        Index(
            "ix_outcome_labels_snapshot_available",
            "snapshot_version",
            "label_available_from",
        ),
        {"schema": "ml"},
    )
    snapshot_version: Mapped[str] = mapped_column(String(40))
    dataset_version: Mapped[str] = mapped_column(String(80))
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    customer_ref: Mapped[str] = mapped_column(String(40))
    opportunity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    opportunity_ref: Mapped[str | None] = mapped_column(String(80))
    opportunity_type: Mapped[str | None] = mapped_column(String(80))
    action_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    score_type: Mapped[str] = mapped_column(String(40), default="SALES_PROPENSITY")
    observation_as_of: Mapped[date] = mapped_column(Date)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    label_available_from: Mapped[date] = mapped_column(Date)
    outcome_label: Mapped[str] = mapped_column(String(80))
    outcome_value: Mapped[bool | None] = mapped_column(Boolean)
    source_reference: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(40), default="COMMERCIAL_OUTCOME")
    label_definition_version: Mapped[str] = mapped_column(String(80), default="legacy-unversioned")
    target_outcome: Mapped[str] = mapped_column(String(80), default="ANY_COMMERCIAL_OPPORTUNITY")
    horizon_days: Mapped[int] = mapped_column(Integer, default=90)
    population_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_kind: Mapped[str] = mapped_column(String(40), default="LOCAL_COMMERCIAL_OUTCOME")
    window_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    candidate_only: Mapped[bool] = mapped_column(Boolean, default=True)
    feature_snapshot_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    feature_checksum: Mapped[str | None] = mapped_column(String(64))
    dataset_manifest_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MLTrainingRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "training_runs"
    __table_args__ = (
        UniqueConstraint("model_id", "model_version"),
        CheckConstraint(
            "status IN ('DRAFT','REGISTERED','VALIDATING','SUBMITTED','APPROVED','CHALLENGER',"
            "'CHAMPION','RETIRED','REJECTED','DEMO_ONLY')",
            name="status",
        ),
        {"schema": "ml"},
    )
    model_id: Mapped[str] = mapped_column(String(80))
    model_version: Mapped[str] = mapped_column(String(40))
    feature_version: Mapped[str] = mapped_column(String(40))
    dataset_version: Mapped[str] = mapped_column(String(80))
    training_period_from: Mapped[date] = mapped_column(Date)
    training_period_to: Mapped[date] = mapped_column(Date)
    validation_period_from: Mapped[date] = mapped_column(Date)
    validation_period_to: Mapped[date] = mapped_column(Date)
    test_period_from: Mapped[date | None] = mapped_column(Date)
    test_period_to: Mapped[date | None] = mapped_column(Date)
    code_version: Mapped[str] = mapped_column(String(80))
    hyperparameters_json: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    lineage_json: Mapped[dict] = mapped_column(JSON, default=dict)
    deployment_mode: Mapped[str] = mapped_column(String(20), default="POC_SHADOW")
    dataset_manifest_hash: Mapped[str | None] = mapped_column(String(64))
    activation_gate_status: Mapped[str] = mapped_column(String(30), default="BLOCKED")
    artifact_checksum: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    approved_by: Mapped[str | None] = mapped_column(String(120))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MLDatasetManifest(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "dataset_manifests"
    __table_args__ = (
        Index("ix_dataset_manifests_status_created", "status", "created_at"),
        {"schema": "ml"},
    )
    manifest_version: Mapped[str] = mapped_column(String(80), unique=True)
    source_kind: Mapped[str] = mapped_column(String(40))
    purpose: Mapped[str] = mapped_column(String(60))
    target_outcome: Mapped[str] = mapped_column(String(80))
    label_definition_version: Mapped[str] = mapped_column(String(80))
    horizon_days: Mapped[int] = mapped_column(Integer)
    population_json: Mapped[dict] = mapped_column(JSON)
    exclusions_json: Mapped[list] = mapped_column(JSON)
    training_cutoff: Mapped[date] = mapped_column(Date)
    feature_snapshot_ids_json: Mapped[list] = mapped_column(JSON)
    label_snapshot_ids_json: Mapped[list] = mapped_column(JSON)
    row_count: Mapped[int] = mapped_column(Integer)
    manifest_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(20))
    blockers_json: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(120))


class MLTrainingExample(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "training_examples"
    __table_args__ = (
        UniqueConstraint("manifest_id", "entity_ref", "observation_as_of"),
        CheckConstraint("split IN ('TRAIN','TEST')", name="split"),
        CheckConstraint(
            "source_kind IN ('BOA_HISTORICAL_OBSERVED','DEMO_SYNTHETIC_LABELS')",
            name="source_kind",
        ),
        CheckConstraint("label_available_from > observation_as_of", name="label_time"),
        Index("ix_ml_training_examples_manifest_split", "manifest_id", "split"),
        {"schema": "ml"},
    )
    manifest_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ml.dataset_manifests.id", ondelete="CASCADE")
    )
    entity_ref: Mapped[str] = mapped_column(String(80))
    split: Mapped[str] = mapped_column(String(20))
    observation_as_of: Mapped[date] = mapped_column(Date)
    label_available_from: Mapped[date] = mapped_column(Date)
    feature_values_json: Mapped[dict] = mapped_column(JSON)
    label: Mapped[bool] = mapped_column(Boolean)
    source_kind: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MLTrainingJob(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "training_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','INSUFFICIENT_DATA','CANCELLED')",
            name="status",
        ),
        CheckConstraint("percentage BETWEEN 0 AND 100", name="percentage"),
        CheckConstraint("algorithm = 'LOGISTIC_REGRESSION'", name="algorithm"),
        Index("ix_ml_training_jobs_created", "created_at"),
        Index(
            "uq_ml_training_jobs_active_manifest",
            "manifest_id",
            unique=True,
            postgresql_where=text("status IN ('QUEUED','RUNNING')"),
            sqlite_where=text("status IN ('QUEUED','RUNNING')"),
        ),
        {"schema": "ml"},
    )
    manifest_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ml.dataset_manifests.id", ondelete="RESTRICT")
    )
    algorithm: Mapped[str] = mapped_column(String(40), default="LOGISTIC_REGRESSION")
    seed: Mapped[int] = mapped_column(Integer)
    justification: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="QUEUED")
    current_step: Mapped[str | None] = mapped_column(String(80))
    percentage: Mapped[int] = mapped_column(Integer, default=0)
    steps_json: Mapped[list] = mapped_column(JSON, default=list)
    result_json: Mapped[dict | None] = mapped_column(JSON)
    error_json: Mapped[dict | None] = mapped_column(JSON)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    author: Mapped[str] = mapped_column(String(120))
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    correlation_id: Mapped[str] = mapped_column(String(128))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MLEvaluationSnapshot(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "evaluation_snapshots"
    __table_args__ = (
        Index("ix_evaluation_snapshots_model_created", "model_version", "created_at"),
        {"schema": "ml"},
    )
    evaluation_ref: Mapped[str] = mapped_column(String(100), unique=True)
    model_version: Mapped[str] = mapped_column(String(40))
    dataset_manifest_hash: Mapped[str] = mapped_column(String(64))
    source_kind: Mapped[str] = mapped_column(String(40))
    evaluation_period_from: Mapped[date] = mapped_column(Date)
    evaluation_period_to: Mapped[date] = mapped_column(Date)
    sample_count: Mapped[int] = mapped_column(Integer)
    positive_count: Mapped[int] = mapped_column(Integer)
    negative_count: Mapped[int] = mapped_column(Integer)
    metrics_json: Mapped[dict] = mapped_column(JSON)
    calibration_json: Mapped[dict] = mapped_column(JSON)
    acceptance_criteria_json: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30))
    blockers_json: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(120))


class MLMonitoringSnapshot(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "monitoring_snapshots"
    __table_args__ = (
        Index("ix_ml_monitoring_domain_time", "domain", "observed_at"),
        {"schema": "ml"},
    )
    domain: Mapped[str] = mapped_column(String(30))
    metric: Mapped[str] = mapped_column(String(80))
    value: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    status: Mapped[str] = mapped_column(String(20))
    thresholds_json: Mapped[dict] = mapped_column(JSON)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trace_id: Mapped[str] = mapped_column(String(100))


class MLGovernanceAuditLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "governance_audit_logs"
    __table_args__ = (
        Index("ix_ml_governance_object_time", "object_type", "object_id", "timestamp"),
        {"schema": "ml"},
    )
    action: Mapped[str] = mapped_column(String(50))
    user_id: Mapped[str] = mapped_column(String(120))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    object_type: Mapped[str] = mapped_column(String(50))
    object_id: Mapped[str] = mapped_column(String(100))
    object_version: Mapped[str] = mapped_column(String(80))
    old_value_json: Mapped[dict | None] = mapped_column(JSON)
    new_value_json: Mapped[dict | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str] = mapped_column(String(100))
