from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from boa_oi.catalog import BOA_PRODUCTS, PRODUCTS_BY_CODE, demo_ownerships
from boa_oi.models.entities import (
    Account,
    AccountBalance,
    Customer,
    CustomerProduct,
    Opportunity,
    OpportunityRule,
    OutboxMessage,
    PortfolioAssignment,
    Product,
    RelationshipManager,
    Rule,
    RuleAction,
    RuleCondition,
    RuleConfidenceConfiguration,
    RuleConfiguration,
    RuleVersion,
    Sector,
    SignalRule,
    Transaction,
)
from boa_oi.technical.config import load_rule_set
from boa_oi.technical.ids import deterministic_uuid
from sqlalchemy import create_engine, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from database.seed.naming import (
    customer_name,
    relationship_manager_index,
    relationship_manager_name,
)

SEED = "boa-sme-oi-2026-v1"
START_DATE = date(2025, 10, 1)
END_DATE = date(2026, 9, 30)
CUSTOMER_COUNT = 500
MIN_TRANSACTIONS = 300_000
SECTORS = (
    "INDUSTRIE",
    "IMPORT_EXPORT",
    "DISTRIBUTION",
    "SERVICES",
    "BTP",
    "AGRICULTURE",
    "COMMERCE",
    "TECHNOLOGIE",
)
SCENARIOS = (
    "GROWTH_COMPANY",
    "STABLE_COMPANY",
    "INTERNATIONAL_GROWTH",
    "CASH_SURPLUS",
    "FINANCIAL_STRESS",
    "NORMAL_CUSTOMER",
    "FALSE_POSITIVE_SEASONAL",
    "FALSE_POSITIVE_ONE_OFF",
)


@dataclass(frozen=True)
class GeneratedRow:
    table: str
    values: dict


def rng_for(*parts: object) -> random.Random:
    digest = hashlib.sha256("|".join(map(str, (SEED, *parts))).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def scenario_for(index: int) -> str:
    return SCENARIOS[(index - 1) % len(SCENARIOS)]


def monthly_multiplier(scenario: str, month_index: int, sector: str) -> float:
    recent = month_index >= 9
    base = 1.0
    if scenario == "GROWTH_COMPANY" and recent:
        base = 1.42
    elif scenario == "INTERNATIONAL_GROWTH" and recent:
        base = 1.50
    elif scenario == "FINANCIAL_STRESS" and recent:
        base = 0.65
    elif scenario == "FALSE_POSITIVE_SEASONAL" and month_index == 2:
        base = 1.65
    if sector in {"COMMERCE", "DISTRIBUTION"} and month_index == 2:
        base *= 1.15
    if sector == "AGRICULTURE" and month_index in {5, 6}:
        base *= 1.25
    return base


def generate_transaction_rows(
    customer_index: int, customer_id: UUID, account_id: UUID
) -> Iterator[dict]:
    customer_ref = f"SME-{customer_index:05d}"
    scenario = scenario_for(customer_index)
    sector = SECTORS[(customer_index - 1) % len(SECTORS)]
    rng = rng_for(customer_ref, "transactions")
    current = START_DATE
    sequence = 0
    while current <= END_DATE:
        month_index = (current.year - START_DATE.year) * 12 + current.month - START_DATE.month
        mult = monthly_multiplier(scenario, month_index, sector)
        daily_count = 2 if current.weekday() < 5 else 1
        if sector in {"COMMERCE", "DISTRIBUTION"}:
            daily_count += 1
        if scenario == "GROWTH_COMPANY" and month_index >= 9:
            daily_count += 1
        # 500 * 365 * avg > 1.6 => comfortably above 300k without random volume risk.
        for item_no in range(daily_count):
            sequence += 1
            is_credit = item_no == 0 or rng.random() < 0.38
            direction = "CREDIT" if is_credit else "DEBIT"
            category = (
                "CUSTOMER_RECEIPT"
                if is_credit
                else (
                    "SUPPLIER_PAYMENT"
                    if rng.random() < (0.65 if sector in {"INDUSTRIE", "BTP"} else 0.40)
                    else "OPERATING_EXPENSE"
                )
            )
            international_base = 0.20 if sector == "IMPORT_EXPORT" else 0.015
            international = rng.random() < international_base
            if scenario == "INTERNATIONAL_GROWTH" and month_index >= 9:
                international = rng.random() < 0.48
            if scenario == "FALSE_POSITIVE_ONE_OFF":
                international = current == date(2026, 8, 17) and item_no == 0
            amount_base = 26000.0 if is_credit else 16500.0
            if category == "SUPPLIER_PAYMENT" and scenario == "GROWTH_COMPANY" and month_index >= 9:
                amount_base *= 1.32
            amount = Decimal(str(round(max(100, amount_base * mult * rng.uniform(0.65, 1.35)), 2)))
            if scenario == "FALSE_POSITIVE_ONE_OFF" and international:
                amount = Decimal("1750000.00")
            tx_ref = f"TX-{customer_index:05d}-{current:%Y%m%d}-{item_no:02d}"
            yield {
                "id": deterministic_uuid("transaction", tx_ref),
                "transaction_ref": tx_ref,
                "customer_id": customer_id,
                "account_id": account_id,
                "booked_at": datetime.combine(current, time(12), tzinfo=timezone.utc),
                "value_date": current,
                "direction": direction,
                "amount": amount,
                "currency": "MAD",
                "transaction_type": "TRANSFER" if international else "PAYMENT",
                "category": category,
                "is_international": international,
                "country_code": "FR" if international else "MA",
                "status": "BOOKED",
                "source_system": "MOCK_PAYMENTS",
                "created_by": "demo-data-generator",
            }
        current += timedelta(days=1)


def generate_balance_rows(customer_index: int, account_id: UUID) -> Iterator[dict]:
    scenario = scenario_for(customer_index)
    rng = rng_for(customer_index, "balances")
    balance = (
        Decimal(1800000)
        if scenario == "CASH_SURPLUS"
        else Decimal(str(250000 + customer_index * 500))
    )
    current = START_DATE
    while current <= END_DATE:
        progress = Decimal((current - START_DATE).days) / Decimal((END_DATE - START_DATE).days)
        if scenario == "FINANCIAL_STRESS":
            balance -= Decimal(600) if current < date(2026, 7, 1) else Decimal(2600)
        elif scenario == "CASH_SURPLUS":
            balance += Decimal(str(rng.randint(-2500, 3500)))
        else:
            balance += Decimal(str(rng.randint(-6000, 6500)))
        limit = Decimal(1000000)
        used = (
            (
                Decimal(150000)
                if current < date(2026, 7, 1)
                else Decimal(650000) + Decimal(250000) * progress
            )
            if scenario == "FINANCIAL_STRESS"
            else Decimal(100000)
        )
        yield {
            "id": deterministic_uuid("balance", account_id, current),
            "account_id": account_id,
            "as_of_date": current,
            "closing_balance": balance,
            "available_balance": balance + limit - used,
            "credit_used": used,
            "credit_limit": limit,
            "currency": "MAD",
        }
        current += timedelta(days=1)


def manifest() -> dict:
    return {
        "seed": SEED,
        "start_date": START_DATE.isoformat(),
        "end_date": END_DATE.isoformat(),
        "customers": CUSTOMER_COUNT,
        "minimum_transactions": MIN_TRANSACTIONS,
        "sectors": list(SECTORS),
        "scenarios": list(SCENARIOS),
        "opportunities": 0,
    }


PRODUCT_UPDATABLE_FIELDS = (
    "name",
    "category",
    "family",
    "description",
    "source_url",
    "eligibility_rules_json",
    "target_segments_json",
    "currencies_json",
    "active",
)

LEGACY_PRODUCT_CODES = {
    "INVESTMENT_FINANCING",
    "WORKING_CAPITAL_FACILITY",
    "OVERDRAFT",
    "TRADE_FINANCE",
    "CASH_MANAGEMENT",
    "TERM_DEPOSIT",
    "LIQUIDITY_INVESTMENT",
}


def product_row(code: str) -> dict:
    item = PRODUCTS_BY_CODE[code]
    return {
        "id": deterministic_uuid("product", code),
        "product_code": code,
        "name": item.name,
        "category": item.category,
        "family": item.family,
        "description": item.description,
        "source_url": item.source_url,
        "eligibility_rules_json": dict(item.eligibility),
        "target_segments_json": list(item.target_segments),
        "currencies_json": ["MAD"],
        "active": True,
        "created_by": "demo-data-generator",
    }


def seed_products(session: Session) -> dict[str, dict]:
    """Insère ou met à jour le catalogue BANK OF AFRICA ; renvoie les lignes par code."""
    rows = {item.code: product_row(item.code) for item in BOA_PRODUCTS}
    for row in rows.values():
        session.execute(
            pg_insert(Product)
            .values(**row)
            .on_conflict_do_update(
                index_elements=[Product.product_code],
                set_={key: row[key] for key in PRODUCT_UPDATABLE_FIELDS},
            )
        )
    # Les anciens codes génériques (catalogue de démonstration initial) sont désactivés,
    # jamais supprimés : des détentions ou des opportunités peuvent encore y renvoyer.
    session.execute(
        update(Product).where(Product.product_code.in_(LEGACY_PRODUCT_CODES)).values(active=False)
    )
    return rows


def seed_products_only(database_url: str) -> dict:
    engine = create_engine(database_url, pool_pre_ping=True)
    with Session(engine) as session, session.begin():
        rows = seed_products(session)
        session.execute(
            delete(CustomerProduct).where(CustomerProduct.created_by == "demo-data-generator")
        )
        count = 0
        for index in range(1, CUSTOMER_COUNT + 1):
            ref = f"SME-{index:05d}"
            customer_id = deterministic_uuid("customer", ref)
            for code in demo_ownerships(ref, scenario_for(index)):
                product = rows[code]
                session.execute(
                    pg_insert(CustomerProduct)
                    .values(
                        id=deterministic_uuid("customer-product", customer_id, product["id"]),
                        customer_id=customer_id,
                        product_id=product["id"],
                        status="ACTIVE",
                        opened_on=START_DATE - timedelta(days=200),
                        utilization_ratio=Decimal("0.55"),
                        created_by="demo-data-generator",
                    )
                    .on_conflict_do_nothing(index_elements=[CustomerProduct.id])
                )
                count += 1
    return {"products": len(rows), "ownerships": count}


def seed(database_url: str, batch_size: int = 1000) -> dict:
    engine = create_engine(database_url, pool_pre_ping=True)
    rules = load_rule_set(Path(__file__).with_name("rules.yaml"))
    with Session(engine) as session, session.begin():
        existing_opportunities = session.scalar(select(func.count()).select_from(Opportunity))
        if existing_opportunities:
            raise RuntimeError("seed refuses to run while opportunities exist")
        for code in SECTORS:
            session.execute(
                pg_insert(Sector)
                .values(
                    id=deterministic_uuid("sector", code),
                    code=code,
                    label=code.replace("_", " ").title(),
                    active=True,
                )
                .on_conflict_do_nothing(index_elements=[Sector.code])
            )
        rms = []
        for index in range(1, 26):
            row = {
                "id": deterministic_uuid("rm", index),
                "subject_id": f"rm-{index:02d}",
                "display_name": relationship_manager_name(index),
                "branch_code": f"BR-{(index - 1) // 5 + 1:02d}",
                "created_by": "demo-data-generator",
            }
            rms.append(row)
            session.execute(
                pg_insert(RelationshipManager)
                .values(**row)
                .on_conflict_do_nothing(index_elements=[RelationshipManager.subject_id])
            )
        product_rows = seed_products(session)
        config_row = {
            "id": deterministic_uuid("config", rules.config_id, rules.rule_set_version),
            "config_id": rules.config_id,
            "engine_version": rules.engine_version,
            "rule_set_version": rules.rule_set_version,
            "status": rules.status,
            "effective_from": date.fromisoformat(rules.effective_from),
            "configuration_json": rules.model_dump(mode="json"),
            "checksum": rules.checksum(),
            "approved_by": rules.approved_by,
            "created_by": "demo-data-generator",
        }
        session.execute(
            pg_insert(RuleConfiguration)
            .values(**config_row)
            .on_conflict_do_nothing(index_elements=[RuleConfiguration.checksum])
        )
        for code, signal_rule in rules.signal_rules.items():
            session.execute(
                pg_insert(SignalRule)
                .values(
                    id=deterministic_uuid("signal-rule", code, signal_rule.version),
                    rule_code=code,
                    version=signal_rule.version,
                    configuration_json=signal_rule.model_dump(mode="json"),
                    active=signal_rule.enabled,
                    created_by="demo-data-generator",
                )
                .on_conflict_do_nothing(index_elements=[SignalRule.rule_code, SignalRule.version])
            )
        for code, opportunity_rule in rules.opportunity_rules.items():
            session.execute(
                pg_insert(OpportunityRule)
                .values(
                    id=deterministic_uuid("opp-rule", code, opportunity_rule.version),
                    opportunity_type=code,
                    version=opportunity_rule.version,
                    configuration_json=opportunity_rule.model_dump(mode="json"),
                    active=opportunity_rule.enabled,
                    created_by="demo-data-generator",
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        OpportunityRule.opportunity_type,
                        OpportunityRule.version,
                    ]
                )
            )
        studio_rule_code = "SYNTHETIC_GROWTH_REVIEW"
        studio_rule_id = deterministic_uuid("rule-studio", studio_rule_code)
        studio_version_id = deterministic_uuid("rule-studio-version", studio_rule_code, 1)
        studio_definition = {
            "name": "Revue de croissance synthétique",
            "description": (
                "Règle de démonstration synthétique; seuil HYPOTHÈSE À VALIDER AVEC BOA."
            ),
            "scope": {"segment": ["SMALL", "MEDIUM"], "dataKind": "SYNTHETIC"},
            "logic": "AND",
            "conditions": [
                {
                    "metric": "INFLOW_GROWTH",
                    "operator": ">",
                    "value": 0.2,
                    "unit": "RATIO",
                    "period": "90D",
                }
            ],
            "recommendation": {
                "opportunityType": "GROWTH_FINANCING",
                "products": ["BOA_CREDIT_MLTD_DIRECT"],
                "horizon": "1-3_MONTHS",
            },
            "confidence": {"baseScore": 60, "weights": {"INFLOW_GROWTH": 25}},
            "lifecycle": {
                "validityDays": 90,
                "dismissedCooldownDays": 30,
                "convertedCooldownDays": 180,
                "deferredCooldownDays": 30,
                "expiredCooldownDays": 7,
            },
        }
        studio_checksum = hashlib.sha256(
            json.dumps(
                studio_definition,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode()
        ).hexdigest()
        session.execute(
            pg_insert(Rule)
            .values(
                id=studio_rule_id,
                rule_id=studio_rule_code,
                name=studio_definition["name"],
                description=studio_definition["description"],
                status="ACTIVE",
                current_version=1,
                active_version=1,
                created_by="demo-data-generator",
            )
            .on_conflict_do_nothing(index_elements=[Rule.rule_id])
        )
        session.execute(
            pg_insert(RuleVersion)
            .values(
                id=studio_version_id,
                rule_id=studio_rule_id,
                version=1,
                status="ACTIVE",
                name=studio_definition["name"],
                description=studio_definition["description"],
                scope_json=studio_definition["scope"],
                logic="AND",
                configuration_json=studio_definition,
                checksum=studio_checksum,
                created_by="demo-data-generator",
            )
            .on_conflict_do_nothing(index_elements=[RuleVersion.rule_id, RuleVersion.version])
        )
        root_condition_id = deterministic_uuid("rule-condition", studio_rule_code, 1, "root")
        session.execute(
            pg_insert(RuleCondition)
            .values(
                id=root_condition_id,
                rule_version_id=studio_version_id,
                parent_condition_id=None,
                path="root",
                position=0,
                node_type="GROUP",
                logic="AND",
                metric_code=None,
                operator=None,
                value_json=None,
                unit=None,
                period=None,
            )
            .on_conflict_do_nothing(
                index_elements=[RuleCondition.rule_version_id, RuleCondition.path]
            )
        )
        session.execute(
            pg_insert(RuleCondition)
            .values(
                id=deterministic_uuid("rule-condition", studio_rule_code, 1, "root.0"),
                rule_version_id=studio_version_id,
                parent_condition_id=root_condition_id,
                path="root.0",
                position=0,
                node_type="CONDITION",
                logic=None,
                metric_code="INFLOW_GROWTH",
                operator=">",
                value_json=0.2,
                unit="RATIO",
                period="90D",
            )
            .on_conflict_do_nothing(
                index_elements=[RuleCondition.rule_version_id, RuleCondition.path]
            )
        )
        session.execute(
            pg_insert(RuleAction)
            .values(
                id=deterministic_uuid("rule-action", studio_rule_code, 1, 0),
                rule_version_id=studio_version_id,
                position=0,
                opportunity_type_code="GROWTH_FINANCING",
                product_codes_json=["BOA_CREDIT_MLTD_DIRECT"],
                horizon_code="1-3_MONTHS",
            )
            .on_conflict_do_nothing(
                index_elements=[RuleAction.rule_version_id, RuleAction.position]
            )
        )
        session.execute(
            pg_insert(RuleConfidenceConfiguration)
            .values(
                id=deterministic_uuid("rule-confidence", studio_rule_code, 1),
                rule_version_id=studio_version_id,
                base_score=Decimal("0.60"),
                weights_json={"INFLOW_GROWTH": 25},
            )
            .on_conflict_do_nothing(index_elements=[RuleConfidenceConfiguration.rule_version_id])
        )
        session.flush()
        tx_buffer = []
        balance_buffer = []
        tx_count = 0
        for index in range(1, CUSTOMER_COUNT + 1):
            ref = f"SME-{index:05d}"
            account_ref = f"SYN-MA-{index:05d}-01"
            customer_id = deterministic_uuid("customer", ref)
            account_id = deterministic_uuid("account", account_ref)
            scenario = scenario_for(index)
            sector = SECTORS[(index - 1) % len(SECTORS)]
            customer = {
                "id": customer_id,
                "customer_ref": ref,
                "legal_name": customer_name(index, sector),
                "sector_code": sector,
                "segment_code": "SMALL" if index % 3 else "MEDIUM",
                "scenario_code": scenario,
                "incorporated_on": date(2000 + index % 20, index % 12 + 1, index % 27 + 1),
                "status": "ACTIVE",
                "rm_id": rms[relationship_manager_index(index, len(rms)) - 1]["id"],
                "created_by": "demo-data-generator",
            }
            session.execute(
                pg_insert(Customer)
                .values(**customer)
                .on_conflict_do_nothing(index_elements=[Customer.customer_ref])
            )
            manager = rms[relationship_manager_index(index, len(rms)) - 1]
            session.execute(
                pg_insert(PortfolioAssignment)
                .values(
                    id=deterministic_uuid("portfolio-assignment", customer_id, START_DATE),
                    customer_id=customer_id,
                    relationship_manager_id=manager["id"],
                    branch_code=manager["branch_code"],
                    valid_from=datetime.combine(START_DATE, time.min, tzinfo=timezone.utc),
                    valid_to=None,
                    actor="demo-data-generator",
                    reason="Initial synthetic portfolio assignment",
                )
                .on_conflict_do_nothing(index_elements=[PortfolioAssignment.id])
            )
            session.execute(
                pg_insert(Account)
                .values(
                    id=account_id,
                    account_ref=account_ref,
                    customer_id=customer_id,
                    account_type="CURRENT",
                    currency="MAD",
                    opened_on=START_DATE - timedelta(days=500),
                    status="ACTIVE",
                    created_by="demo-data-generator",
                )
                .on_conflict_do_nothing(index_elements=[Account.account_ref])
            )
            for code in demo_ownerships(ref, scenario):
                product = product_rows[code]
                session.execute(
                    pg_insert(CustomerProduct)
                    .values(
                        id=deterministic_uuid("customer-product", customer_id, product["id"]),
                        customer_id=customer_id,
                        product_id=product["id"],
                        status="ACTIVE",
                        opened_on=START_DATE - timedelta(days=200),
                        utilization_ratio=Decimal("0.55"),
                        created_by="demo-data-generator",
                    )
                    .on_conflict_do_nothing(index_elements=[CustomerProduct.id])
                )
            for row in generate_transaction_rows(index, customer_id, account_id):
                tx_buffer.append(row)
                tx_count += 1
                if len(tx_buffer) >= batch_size:
                    session.execute(
                        pg_insert(Transaction)
                        .values(tx_buffer)
                        .on_conflict_do_nothing(
                            index_elements=[
                                Transaction.source_system,
                                Transaction.transaction_ref,
                            ]
                        )
                    )
                    tx_buffer.clear()
            for row in generate_balance_rows(index, account_id):
                balance_buffer.append(row)
                if len(balance_buffer) >= batch_size:
                    session.execute(
                        pg_insert(AccountBalance)
                        .values(balance_buffer)
                        .on_conflict_do_nothing(
                            index_elements=[
                                AccountBalance.account_id,
                                AccountBalance.as_of_date,
                            ]
                        )
                    )
                    balance_buffer.clear()
        if tx_buffer:
            session.execute(
                pg_insert(Transaction)
                .values(tx_buffer)
                .on_conflict_do_nothing(
                    index_elements=[
                        Transaction.source_system,
                        Transaction.transaction_ref,
                    ]
                )
            )
        if balance_buffer:
            session.execute(
                pg_insert(AccountBalance)
                .values(balance_buffer)
                .on_conflict_do_nothing(
                    index_elements=[
                        AccountBalance.account_id,
                        AccountBalance.as_of_date,
                    ]
                )
            )
        session.execute(
            pg_insert(OutboxMessage)
            .values(
                id=deterministic_uuid("outbox", SEED),
                event_type="TransactionImported",
                aggregate_type="ImportBatch",
                aggregate_id=SEED,
                payload_json=manifest() | {"transactions": tx_count},
                correlation_id=str(deterministic_uuid("correlation", SEED)),
                attempt_count=0,
            )
            .on_conflict_do_nothing(index_elements=[OutboxMessage.id])
        )
        if tx_count < MIN_TRANSACTIONS:
            raise RuntimeError(f"generated only {tx_count} transactions")
    return manifest() | {"transactions": tx_count}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url")
    parser.add_argument("--manifest-only", action="store_true")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument(
        "--products-only",
        action="store_true",
        help="Recharge uniquement le catalogue produit et les détentions de démonstration.",
    )
    args = parser.parse_args()
    if args.manifest_only:
        print(manifest())
        return
    if not args.database_url:
        parser.error("--database-url or --manifest-only is required")
    if args.products_only:
        print(seed_products_only(args.database_url))
        return
    print(seed(args.database_url, args.batch_size))


if __name__ == "__main__":
    main()
