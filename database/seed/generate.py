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
    CustomerBankingDeclaration,
    CustomerProduct,
    MLDatasetManifest,
    MLTrainingExample,
    Opportunity,
    OpportunityRule,
    OutboxMessage,
    PortfolioAssignment,
    Product,
    RelationshipManager,
    Rule,
    RuleAction,
    RuleAuditLog,
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

from database.seed.financial_intelligence import seed_financial_intelligence
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
    "MULTIBANK_PRIMARY",
    "MULTIBANK_SECONDARY",
)
MULTIBANK_TARGET_SHARE = {
    "MULTIBANK_PRIMARY": Decimal("0.60"),
    "MULTIBANK_SECONDARY": Decimal("0.25"),
}
DEMO_ML_MANIFEST_VERSION = "demo-synthetic-labels-2026-v1"
DEMO_ML_EXAMPLE_COUNT = 240
DEMO_ML_FEATURES = (
    "cash_inflow_growth_90d",
    "supplier_payment_growth_90d",
    "international_activity_ratio_90d",
    "balance_strength_90d",
    "activity_density_90d",
    "analytics_coverage_90d",
    "customer_tenure_ratio",
    "segment_medium",
    "confirmed_signal_ratio",
    "published_rule_match_strength",
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


def demo_training_example(index: int) -> dict:
    """Create one deterministic and explicitly synthetic commercial propensity example."""
    scenario = scenario_for(index)
    rng = rng_for("ml-training", index)
    growth = scenario == "GROWTH_COMPANY"
    international = scenario == "INTERNATIONAL_GROWTH"
    surplus = scenario == "CASH_SURPLUS"
    false_positive = scenario.startswith("FALSE_POSITIVE")
    positive_rates = {
        "GROWTH_COMPANY": 0.80,
        "INTERNATIONAL_GROWTH": 0.70,
        "CASH_SURPLUS": 0.50,
        "STABLE_COMPANY": 0.20,
        "FINANCIAL_STRESS": 0.10,
        "NORMAL_CUSTOMER": 0.15,
        "FALSE_POSITIVE_SEASONAL": 0.0,
        "FALSE_POSITIVE_ONE_OFF": 0.0,
        "MULTIBANK_PRIMARY": 0.45,
        "MULTIBANK_SECONDARY": 0.35,
    }
    # Draw independently for every chronological example so TRAIN and TEST both
    # retain positives; false-positive scenarios are deterministically negative.
    label = False if false_positive else rng.random() < positive_rates[scenario]
    observation = date(2026, 1, 1) + timedelta(days=index - 1)
    feature_values = {
        "cash_inflow_growth_90d": round((0.55 if growth else 0.10) + rng.uniform(-0.12, 0.12), 6),
        "supplier_payment_growth_90d": round(
            (0.38 if growth else 0.08) + rng.uniform(-0.1, 0.1), 6
        ),
        "international_activity_ratio_90d": round(
            (0.72 if international else 0.08) + rng.uniform(-0.06, 0.06), 6
        ),
        "balance_strength_90d": round((0.70 if surplus else 0.45) + rng.uniform(-0.12, 0.12), 6),
        "activity_density_90d": round((0.75 if growth else 0.48) + rng.uniform(-0.1, 0.1), 6),
        "analytics_coverage_90d": round(0.92 + rng.uniform(-0.05, 0.05), 6),
        "customer_tenure_ratio": round(0.35 + (index % 15) / 20, 6),
        "segment_medium": float(index % 3 == 0),
        "confirmed_signal_ratio": round((0.78 if label else 0.25) + rng.uniform(-0.1, 0.1), 6),
        "published_rule_match_strength": round(
            (0.80 if label else (0.72 if false_positive else 0.30)) + rng.uniform(-0.08, 0.08),
            6,
        ),
    }
    return {
        "id": deterministic_uuid("ml-training-example", DEMO_ML_MANIFEST_VERSION, index),
        "manifest_id": deterministic_uuid("ml-dataset-manifest", DEMO_ML_MANIFEST_VERSION),
        "entity_ref": f"SME-{index:05d}",
        "split": "TRAIN" if index <= 192 else "TEST",
        "observation_as_of": observation,
        "label_available_from": observation + timedelta(days=90),
        "feature_values_json": {key: feature_values[key] for key in DEMO_ML_FEATURES},
        "label": label,
        "source_kind": "DEMO_SYNTHETIC_LABELS",
    }


def monthly_multiplier(scenario: str, month_index: int, sector: str) -> float:
    recent = month_index >= 9
    base = 1.0
    if scenario in {"GROWTH_COMPANY", "MULTIBANK_PRIMARY", "MULTIBANK_SECONDARY"} and recent:
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
            self_transfer = (
                scenario in MULTIBANK_TARGET_SHARE
                and current.weekday() == 1
                and current.day <= 14
                and item_no == daily_count - 1
            )
            if self_transfer:
                is_credit = (current.month + customer_index) % 2 == 0
                direction = "CREDIT" if is_credit else "DEBIT"
                category = "INTER_BANK_SELF_TRANSFER"
                international = False
                amount = Decimal("15000.00")
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
                "transaction_type": "TRANSFER" if international or self_transfer else "PAYMENT",
                "category": category,
                "is_international": international,
                "country_code": "FR" if international else "MA",
                "status": "BOOKED",
                "source_system": "MOCK_PAYMENTS",
                "counterparty_name": (
                    customer_name(customer_index, sector) if self_transfer else None
                ),
                "remittance_information": (
                    "Transfert entre comptes propres dans une autre banque"
                    if self_transfer
                    else None
                ),
                "externally_domiciled": self_transfer,
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
        elif scenario == "MULTIBANK_SECONDARY":
            balance = max(Decimal("25000"), balance + Decimal(str(rng.randint(-3500, 2800))))
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
        "multibank": {
            "targetShares": {key: float(value) for key, value in MULTIBANK_TARGET_SHARE.items()},
            "declaredTurnoverPopulation": "one customer out of two in each multibank scenario",
            "relationshipDeclarationPopulation": (
                "one customer out of three in each multibank scenario"
            ),
            "status": "HYPOTHÈSE À VALIDER AVEC BOA",
        },
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
        # This governed replica intentionally starts as a draft. The isolated
        # validator exercises validation, persisted simulation, analyst
        # submission, independent approval, publication and the full audit trail.
        studio_rule_code = "FLOW_DOMICILIATION_001"
        studio_rule_id = deterministic_uuid("rule-studio", studio_rule_code)
        studio_version_id = deterministic_uuid("rule-studio-version", studio_rule_code, 1)
        studio_definition = {
            "name": "Domiciliation des flux multibancarisés",
            "description": (
                "Réplique gouvernée de FLOW_DOMICILIATION_001 sur données synthétiques; "
                "seuils HYPOTHÈSE À VALIDER AVEC BOA."
            ),
            "scope": {"segment": ["SMALL", "MEDIUM"], "dataKind": "SYNTHETIC"},
            "logic": "AND",
            "conditions": [
                {
                    "metric": "FLOW_VISIBILITY_OPPORTUNITY",
                    "operator": "=",
                    "value": True,
                    "unit": "BOOLEAN",
                    "period": "90D",
                },
                {
                    "metric": "NO_RECENT_DOMICILIATION_ACTION",
                    "operator": "=",
                    "value": True,
                    "unit": "BOOLEAN",
                    "period": "180D",
                },
                {
                    "type": "GROUP",
                    "logic": "OR",
                    "conditions": [
                        {
                            "metric": "INFLOW_GROWTH",
                            "operator": ">",
                            "value": 0,
                            "unit": "RATIO",
                            "period": "90D",
                        },
                        {
                            "metric": "FINGERPRINT_GROWTH_90D",
                            "operator": ">",
                            "value": 0,
                            "unit": "COUNT",
                            "period": "90D",
                        },
                        {
                            "metric": "DECLARED_TURNOVER_GROWTH",
                            "operator": ">",
                            "value": 0,
                            "unit": "RATIO",
                            "period": "365D",
                        },
                    ],
                },
            ],
            "recommendation": {
                "opportunityType": "FLOW_DOMICILIATION",
                "products": [
                    "BOA_PACK_BUSINESS_PME",
                    "BOA_BUSINESS_ONLINE",
                    "BOA_VIREMENT_MASSE",
                    "BOA_PRELEVEMENT_MASSE",
                ],
                "horizon": "1-3_MONTHS",
                "what": (
                    "Part de flux estimée faible ou partielle chez BANK OF AFRICA : "
                    "proposer la domiciliation des flux et des salaires."
                ),
                "whenText": "Contacter dans les 1 à 3 mois.",
            },
            "confidence": {
                "baseScore": 60,
                "weights": {
                    "FLOW_VISIBILITY_OPPORTUNITY": 15,
                    "INFLOW_GROWTH": 10,
                    "FINGERPRINT_GROWTH_90D": 10,
                    "DECLARED_TURNOVER_GROWTH": 10,
                },
            },
            "lifecycle": {
                "validityDays": 90,
                "dismissedCooldownDays": 180,
                "convertedCooldownDays": 180,
                "deferredCooldownDays": 180,
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
                status="DRAFT",
                current_version=1,
                active_version=None,
                created_by="business.analyst.demo",
            )
            .on_conflict_do_nothing(index_elements=[Rule.rule_id])
        )
        session.execute(
            pg_insert(RuleVersion)
            .values(
                id=studio_version_id,
                rule_id=studio_rule_id,
                version=1,
                status="DRAFT",
                name=studio_definition["name"],
                description=studio_definition["description"],
                scope_json=studio_definition["scope"],
                logic="AND",
                configuration_json=studio_definition,
                checksum=studio_checksum,
                created_by="business.analyst.demo",
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
        condition_rows = [
            ("root.0", 0, "FLOW_VISIBILITY_OPPORTUNITY", "90D"),
            ("root.1", 1, "NO_RECENT_DOMICILIATION_ACTION", "180D"),
        ]
        for path, position, metric, period in condition_rows:
            session.execute(
                pg_insert(RuleCondition)
                .values(
                    id=deterministic_uuid("rule-condition", studio_rule_code, 1, path),
                    rule_version_id=studio_version_id,
                    parent_condition_id=root_condition_id,
                    path=path,
                    position=position,
                    node_type="CONDITION",
                    logic=None,
                    metric_code=metric,
                    operator="=",
                    value_json=True,
                    unit="BOOLEAN",
                    period=period,
                )
                .on_conflict_do_nothing(
                    index_elements=[RuleCondition.rule_version_id, RuleCondition.path]
                )
            )
        dynamics_group_id = deterministic_uuid("rule-condition", studio_rule_code, 1, "root.2")
        session.execute(
            pg_insert(RuleCondition)
            .values(
                id=dynamics_group_id,
                rule_version_id=studio_version_id,
                parent_condition_id=root_condition_id,
                path="root.2",
                position=2,
                node_type="GROUP",
                logic="OR",
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
        dynamic_rows = [
            ("root.2.0", 0, "INFLOW_GROWTH", "RATIO", "90D"),
            ("root.2.1", 1, "FINGERPRINT_GROWTH_90D", "COUNT", "90D"),
            ("root.2.2", 2, "DECLARED_TURNOVER_GROWTH", "RATIO", "365D"),
        ]
        for path, position, metric, unit, period in dynamic_rows:
            session.execute(
                pg_insert(RuleCondition)
                .values(
                    id=deterministic_uuid("rule-condition", studio_rule_code, 1, path),
                    rule_version_id=studio_version_id,
                    parent_condition_id=dynamics_group_id,
                    path=path,
                    position=position,
                    node_type="CONDITION",
                    logic=None,
                    metric_code=metric,
                    operator=">",
                    value_json=0,
                    unit=unit,
                    period=period,
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
                opportunity_type_code="FLOW_DOMICILIATION",
                product_codes_json=[
                    "BOA_PACK_BUSINESS_PME",
                    "BOA_BUSINESS_ONLINE",
                    "BOA_VIREMENT_MASSE",
                    "BOA_PRELEVEMENT_MASSE",
                ],
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
                weights_json={
                    "FLOW_VISIBILITY_OPPORTUNITY": 15,
                    "INFLOW_GROWTH": 10,
                    "FINGERPRINT_GROWTH_90D": 10,
                    "DECLARED_TURNOVER_GROWTH": 10,
                },
            )
            .on_conflict_do_nothing(index_elements=[RuleConfidenceConfiguration.rule_version_id])
        )
        session.execute(
            pg_insert(RuleAuditLog)
            .values(
                id=deterministic_uuid("rule-audit", studio_rule_code, 1, "CREATED"),
                rule_id=studio_rule_id,
                rule_version=1,
                action="CREATED",
                user_id="business.analyst.demo",
                timestamp=datetime.combine(START_DATE, time(hour=8), tzinfo=timezone.utc),
                old_value_json=None,
                new_value_json={**studio_definition, "status": "DRAFT"},
                reason="Brouillon synthétique seedé pour le circuit gouverné",
            )
            .on_conflict_do_nothing(index_elements=[RuleAuditLog.id])
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
            transaction_rows = list(generate_transaction_rows(index, customer_id, account_id))
            multibank_share = MULTIBANK_TARGET_SHARE.get(scenario)
            boa_inflows = sum(
                (
                    row["amount"]
                    for row in transaction_rows
                    if row["direction"] == "CREDIT"
                    and row["category"] != "INTER_BANK_SELF_TRANSFER"
                ),
                Decimal(0),
            )
            has_si_relationship = multibank_share is not None and index % 3 == 0
            has_declared_turnover = multibank_share is not None and index % 2 == 0
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
                "banking_relationship": (
                    "PRIMARY"
                    if has_si_relationship and scenario == "MULTIBANK_PRIMARY"
                    else "SECONDARY"
                    if has_si_relationship
                    else None
                ),
                "banking_relationship_declared_at": (
                    datetime.combine(END_DATE, time.min, tzinfo=timezone.utc)
                    if has_si_relationship
                    else None
                ),
                "banking_relationship_declared_by": (
                    "demo-data-generator" if has_si_relationship else None
                ),
                "banking_relationship_reason": (
                    "Scénario synthétique multibancaire; HYPOTHÈSE À VALIDER AVEC BOA"
                    if has_si_relationship
                    else None
                ),
                "banking_relationship_source": (
                    "INFORMATION_SYSTEM" if has_si_relationship else None
                ),
                "declared_turnover": (
                    (boa_inflows / multibank_share).quantize(Decimal("0.0001"))
                    if has_declared_turnover and multibank_share is not None
                    else None
                ),
                "declared_turnover_as_of": END_DATE if has_declared_turnover else None,
                "declared_turnover_entered_by": (
                    "demo-data-generator" if has_declared_turnover else None
                ),
                "declared_turnover_source": (
                    "INFORMATION_SYSTEM" if has_declared_turnover else None
                ),
                "created_by": "demo-data-generator",
            }
            session.execute(
                pg_insert(Customer)
                .values(**customer)
                .on_conflict_do_nothing(index_elements=[Customer.customer_ref])
            )
            if has_si_relationship or has_declared_turnover:
                declared_at = datetime.combine(END_DATE, time.min, tzinfo=timezone.utc)
                session.execute(
                    pg_insert(CustomerBankingDeclaration)
                    .values(
                        id=deterministic_uuid(
                            "banking-relationship-declaration", customer_id, declared_at
                        ),
                        customer_id=customer_id,
                        banking_relationship=customer["banking_relationship"] or "UNKNOWN",
                        declared_at=declared_at,
                        declared_by="demo-data-generator",
                        reason=("Scénario synthétique multibancaire; HYPOTHÈSE À VALIDER AVEC BOA"),
                        source="SYNTHETIC_POC",
                        declared_turnover=customer["declared_turnover"],
                        declared_turnover_as_of=customer["declared_turnover_as_of"],
                        declared_turnover_source=(
                            "SYNTHETIC_POC" if has_declared_turnover else None
                        ),
                    )
                    .on_conflict_do_nothing(index_elements=[CustomerBankingDeclaration.id])
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
            for row in transaction_rows:
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
        seed_financial_intelligence(session)
        demo_examples = [
            demo_training_example(index) for index in range(1, DEMO_ML_EXAMPLE_COUNT + 1)
        ]
        demo_manifest_id = deterministic_uuid("ml-dataset-manifest", DEMO_ML_MANIFEST_VERSION)
        demo_manifest_payload = {
            "manifestVersion": DEMO_ML_MANIFEST_VERSION,
            "sourceKind": "DEMO_SYNTHETIC_LABELS",
            "purpose": "DEMONSTRATION_ONLY",
            "targetOutcome": "ANY_COMMERCIAL_OPPORTUNITY",
            "labelDefinitionVersion": "demo-commercial-conversion-90d-v1",
            "horizonDays": 90,
            "population": {
                "segment": "PME",
                "featureSetVersion": "sales-features-v2",
                "dataClassification": "SYNTHETIC_DEMO_ONLY",
            },
            "trainingCutoff": "2026-07-11",
            "rowCount": DEMO_ML_EXAMPLE_COUNT,
        }
        demo_manifest_hash = hashlib.sha256(
            json.dumps(demo_manifest_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        session.execute(
            pg_insert(MLDatasetManifest)
            .values(
                id=demo_manifest_id,
                manifest_version=DEMO_ML_MANIFEST_VERSION,
                source_kind="DEMO_SYNTHETIC_LABELS",
                purpose="DEMONSTRATION_ONLY",
                target_outcome="ANY_COMMERCIAL_OPPORTUNITY",
                label_definition_version="demo-commercial-conversion-90d-v1",
                horizon_days=90,
                population_json=demo_manifest_payload["population"],
                exclusions_json=[
                    "FALSE_POSITIVE_SYNTHETIC_LABEL_ALWAYS_NEGATIVE",
                    "NEVER_PROMOTABLE",
                ],
                training_cutoff=date(2026, 7, 11),
                feature_snapshot_ids_json=[],
                label_snapshot_ids_json=[str(item["id"]) for item in demo_examples],
                row_count=DEMO_ML_EXAMPLE_COUNT,
                manifest_hash=demo_manifest_hash,
                status="TRAINING_READY",
                blockers_json=["DEMO_SYNTHETIC_LABELS_NON_PROMOTABLE"],
                created_by="demo-data-generator",
            )
            .on_conflict_do_nothing(index_elements=[MLDatasetManifest.manifest_version])
        )
        session.execute(
            pg_insert(MLTrainingExample)
            .values(demo_examples)
            .on_conflict_do_nothing(index_elements=[MLTrainingExample.id])
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
