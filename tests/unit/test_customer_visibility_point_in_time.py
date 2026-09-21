from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import cast

from boa_oi.customer_api import (
    latest_banking_declarations,
    latest_flow_visibility,
    serialize,
)
from boa_oi.models.entities import (
    Customer,
    CustomerBankingDeclaration,
    FlowVisibilitySnapshot,
)
from boa_oi.technical.ids import deterministic_uuid
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def test_customer_visibility_and_declaration_are_point_in_time() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        for schema in ("customer", "analytics"):
            connection.exec_driver_sql(f"ATTACH DATABASE ':memory:' AS '{schema}'")
        for table in (
            Customer.__mapper__.local_table,
            CustomerBankingDeclaration.__mapper__.local_table,
            FlowVisibilitySnapshot.__mapper__.local_table,
        ):
            cast(Table, table).create(connection)

    customer_id = deterministic_uuid("customer", "SME-PTI-001")
    with Session(engine) as session:
        customer = Customer(
            id=customer_id,
            customer_ref="SME-PTI-001",
            legal_name="PME Point In Time",
            sector_code="SERVICES",
            segment_code="SME",
            scenario_code="MULTIBANK",
            incorporated_on=date(2015, 1, 1),
            status="ACTIVE",
            banking_relationship="SECONDARY",
            banking_relationship_declared_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
            banking_relationship_declared_by="cc-current",
            banking_relationship_reason="Déclaration courante",
            banking_relationship_source="RELATIONSHIP_MANAGER",
            declared_turnover=Decimal("2000000"),
            declared_turnover_as_of=date(2026, 9, 20),
            declared_turnover_entered_by="cc-current",
            declared_turnover_source="RELATIONSHIP_MANAGER",
            rm_id=deterministic_uuid("rm", "RM-PTI"),
        )
        session.add(customer)
        session.add_all(
            [
                CustomerBankingDeclaration(
                    id=deterministic_uuid("declaration", "SME-PTI-001", "2026-08-01"),
                    customer_id=customer_id,
                    banking_relationship="PRIMARY",
                    declared_turnover=Decimal("1500000"),
                    declared_turnover_as_of=date(2026, 8, 1),
                    declared_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                    declared_by="cc-historical",
                    reason="Déclaration historique",
                    source="RELATIONSHIP_MANAGER",
                    declared_turnover_source="RELATIONSHIP_MANAGER",
                ),
                CustomerBankingDeclaration(
                    id=deterministic_uuid("declaration", "SME-PTI-001", "2026-08-25"),
                    customer_id=customer_id,
                    banking_relationship="EXCLUSIVE",
                    declared_turnover=Decimal("3000000"),
                    declared_turnover_as_of=date(2026, 9, 15),
                    declared_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
                    declared_by="cc-relation-only-at-cutoff",
                    reason="Relation valable mais CA postérieur à la coupe",
                    source="RELATIONSHIP_MANAGER",
                    declared_turnover_source="RELATIONSHIP_MANAGER",
                ),
                CustomerBankingDeclaration(
                    id=deterministic_uuid("declaration", "SME-PTI-001", "2026-09-20"),
                    customer_id=customer_id,
                    banking_relationship="SECONDARY",
                    declared_turnover=Decimal("2000000"),
                    declared_turnover_as_of=date(2026, 9, 20),
                    declared_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
                    declared_by="cc-current",
                    reason="Déclaration courante",
                    source="RELATIONSHIP_MANAGER",
                    declared_turnover_source="RELATIONSHIP_MANAGER",
                ),
                FlowVisibilitySnapshot(
                    id=deterministic_uuid("visibility", "SME-PTI-001", "2026-08-31"),
                    customer_id=customer_id,
                    customer_ref="SME-PTI-001",
                    as_of_date=date(2026, 8, 31),
                    level="PARTIAL",
                    estimated_share=Decimal("0.500000"),
                    method="TURNOVER_RATIO",
                    evidence_json=[],
                    fingerprint_count_90d=0,
                    fingerprint_previous_90d=0,
                    categorization_coverage=Decimal("1.000000"),
                    calculation_version="test-v1",
                    input_watermark="historical",
                    created_by="test",
                ),
                FlowVisibilitySnapshot(
                    id=deterministic_uuid("visibility", "SME-PTI-001", "2026-09-30"),
                    customer_id=customer_id,
                    customer_ref="SME-PTI-001",
                    as_of_date=date(2026, 9, 30),
                    level="LOW",
                    estimated_share=Decimal("0.200000"),
                    method="TURNOVER_RATIO",
                    evidence_json=[],
                    fingerprint_count_90d=0,
                    fingerprint_previous_90d=0,
                    categorization_coverage=Decimal("1.000000"),
                    calculation_version="test-v2",
                    input_watermark="current",
                    created_by="test",
                ),
            ]
        )
        session.commit()

        as_of = date(2026, 8, 31)
        declaration, turnover_declaration = latest_banking_declarations(
            session, customer, as_of=as_of
        )
        visibility = latest_flow_visibility(session, customer, as_of=as_of)
        payload = serialize(
            customer,
            flow_visibility=visibility,
            declaration=declaration,
            turnover_declaration=turnover_declaration,
            as_of=as_of,
        )

    assert payload["bankingRelationship"] == "EXCLUSIVE"
    assert payload["bankingRelationshipDeclaration"]["declaredBy"] == "cc-relation-only-at-cutoff"
    assert payload["declaredTurnover"] == 1500000.0
    assert payload["flowVisibility"]["level"] == "PARTIAL"
    assert payload["flowVisibility"]["asOf"] == "2026-08-31"
    engine.dispose()


def test_historical_read_without_declaration_does_not_fall_back_to_current() -> None:
    customer = Customer(
        id=deterministic_uuid("customer", "SME-PTI-002"),
        customer_ref="SME-PTI-002",
        legal_name="PME Sans Historique",
        sector_code="SERVICES",
        segment_code="SME",
        scenario_code="MULTIBANK",
        incorporated_on=date(2015, 1, 1),
        status="ACTIVE",
        banking_relationship="SECONDARY",
        banking_relationship_declared_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
        banking_relationship_declared_by="cc-current",
        banking_relationship_reason="Déclaration future",
        banking_relationship_source="RELATIONSHIP_MANAGER",
        declared_turnover=Decimal("2000000"),
        declared_turnover_as_of=date(2026, 9, 20),
        declared_turnover_entered_by="cc-current",
        declared_turnover_source="RELATIONSHIP_MANAGER",
        rm_id=deterministic_uuid("rm", "RM-PTI"),
    )

    payload = serialize(customer, declaration=None, as_of=date(2026, 8, 31))

    assert payload["bankingRelationship"] == "UNKNOWN"
    assert payload["bankingRelationshipDeclaration"] is None
    assert payload["declaredTurnover"] is None
    assert payload["declaredTurnoverAsOf"] is None
    assert payload["flowVisibility"] == {}
