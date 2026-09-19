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
    rm_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customer.relationship_managers.id")
    )


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


class Product(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "products"
    __table_args__ = {"schema": "product"}
    product_code: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(60))
    family: Mapped[str | None] = mapped_column(String(60), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
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
        UniqueConstraint("deduplication_key"),
        Index(
            "ix_opportunities_active_priority",
            "status",
            "priority_level",
            "priority_score",
            "generated_at",
        ),
        {"schema": "opportunity"},
    )
    opportunity_ref: Mapped[str] = mapped_column(String(80), unique=True)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    customer_ref: Mapped[str] = mapped_column(String(40), default="UNKNOWN")
    customer_name: Mapped[str] = mapped_column(String(180), default="Synthetic SME")
    opportunity_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20))
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
    explanation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    engine_version: Mapped[str] = mapped_column(String(80), default="0.1.0")
    rule_version: Mapped[str] = mapped_column(String(80), default="1")
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
        Index("ix_actions_opportunity_created", "opportunity_id", "created_at"),
        {"schema": "action"},
    )
    action_ref: Mapped[str] = mapped_column(String(80), unique=True)
    opportunity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    opportunity_ref: Mapped[str] = mapped_column(String(80))
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
    engine_version: Mapped[str] = mapped_column(String(80))
    rule_version: Mapped[str] = mapped_column(String(80))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input_reference: Mapped[str] = mapped_column(String(120))
    signals_json: Mapped[list] = mapped_column(JSON)
    metric_snapshots_json: Mapped[list] = mapped_column(JSON)
    confidence_components_json: Mapped[list] = mapped_column(JSON)
    priority_components_json: Mapped[list] = mapped_column(JSON)
    decision_hash: Mapped[str] = mapped_column(String(64), unique=True)


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
    checksum: Mapped[str] = mapped_column(String(64))


class ModelRegistry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "model_registry"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CHALLENGER','ACTIVE','RETIRED')",
            name="status",
        ),
        CheckConstraint("score_type = 'SALES_PROPENSITY'", name="score_type"),
        CheckConstraint("threshold BETWEEN 0 AND 1", name="threshold"),
        Index("ix_model_registry_status", "status"),
        {"schema": "ml"},
    )
    model_version: Mapped[str] = mapped_column(String(40), unique=True)
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
    deployment_mode: Mapped[str] = mapped_column(String(20), default="POC_ASSISTIVE")


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
    calibration: Mapped[str] = mapped_column(String(20))
    segment: Mapped[str] = mapped_column(String(20))
    model_version: Mapped[str] = mapped_column(String(40))
    feature_set_version: Mapped[str] = mapped_column(String(40))
    feature_checksum: Mapped[str] = mapped_column(String(64))
    contributions_json: Mapped[list] = mapped_column(JSON)
    top_factors_json: Mapped[list] = mapped_column(JSON)
    training_dataset_version: Mapped[str] = mapped_column(String(80))
    deployment_mode: Mapped[str] = mapped_column(String(20), default="POC_ASSISTIVE")


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
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    customer_ref: Mapped[str] = mapped_column(String(40))
    score_type: Mapped[str] = mapped_column(String(40), default="SALES_PROPENSITY")
    observation_as_of: Mapped[date] = mapped_column(Date)
    label_available_from: Mapped[date] = mapped_column(Date)
    outcome_label: Mapped[str] = mapped_column(String(80))
    outcome_value: Mapped[bool] = mapped_column(Boolean)
    source_reference: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
