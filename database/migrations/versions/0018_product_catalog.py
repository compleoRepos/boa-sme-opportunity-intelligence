"""Add governed BANK OF AFRICA product catalogue metadata.

Revision ID: 0018_product_catalog
Revises: 0017_ml_shadow_governance
"""

from __future__ import annotations

import hashlib
import json

import sqlalchemy as sa
from alembic import op

revision = "0018_product_catalog"
down_revision = "0017_ml_shadow_governance"
branch_labels = None
depends_on = None

LEGACY_FAMILIES = {
    "INVESTMENT_FINANCING": "INVESTMENT_FINANCING",
    "WORKING_CAPITAL_FACILITY": "WORKING_CAPITAL_FACILITY",
    "OVERDRAFT": "OVERDRAFT",
    "TRADE_FINANCE": "TRADE_FINANCE",
    "CASH_MANAGEMENT": "CASH_MANAGEMENT",
    "TERM_DEPOSIT": "TERM_DEPOSIT",
    "LIQUIDITY_INVESTMENT": "LIQUIDITY_INVESTMENT",
}

DEMO_RULE_PRODUCTS = {
    "INVESTMENT_FINANCING": [
        "BOA_CREDIT_MLTD_DIRECT",
        "BOA_BAIL_ENTREPRISE",
        "BOA_ISTITMAR_MAROC_PME",
    ],
    "TRADE_FINANCE": [
        "BOA_CREDIT_DOCUMENTAIRE",
        "BOA_FINANCEMENT_IMPORTATIONS",
        "BOA_PREFINANCEMENT_EXPORT",
    ],
    "CASH_INVESTMENT": ["BOA_DEPOT_A_TERME", "BOA_BON_DE_CAISSE", "BOA_OPCVM"],
    "FINANCIAL_STRESS_SIGNAL": ["BOA_PACK_BUSINESS_PME", "BOA_CREDIT_CAMPAGNE"],
}

LEGACY_RULE_PRODUCTS = {
    "INVESTMENT_FINANCING": ["INVESTMENT_FINANCING", "WORKING_CAPITAL_FACILITY"],
    "TRADE_FINANCE": ["TRADE_FINANCE"],
    "CASH_INVESTMENT": ["CASH_MANAGEMENT", "TERM_DEPOSIT", "LIQUIDITY_INVESTMENT"],
    "FINANCIAL_STRESS_SIGNAL": ["CASH_MANAGEMENT", "WORKING_CAPITAL_FACILITY"],
}

DEMO_STUDIO_RULE_ID = "SYNTHETIC_GROWTH_REVIEW"
DEMO_STUDIO_PRODUCTS = ["BOA_CREDIT_MLTD_DIRECT"]
LEGACY_STUDIO_PRODUCTS = ["INVESTMENT_FINANCING"]


def _checksum(definition: dict[str, object]) -> str:
    canonical = json.dumps(definition, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _update_demo_studio_products(source: list[str], target: list[str]) -> None:
    bind = op.get_bind()
    row = (
        bind.execute(
            sa.text(
                """
            SELECT rv.id, rv.configuration_json
              FROM rule.rule_versions rv
              JOIN rule.rules r ON r.id = rv.rule_id
             WHERE r.rule_id = :rule_id
               AND r.created_by = 'demo-data-generator'
               AND rv.version = 1
               AND rv.created_by = 'demo-data-generator'
            """
            ).bindparams(rule_id=DEMO_STUDIO_RULE_ID)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return
    configuration = dict(row["configuration_json"])
    recommendation = dict(configuration.get("recommendation") or {})
    if recommendation.get("products") != source:
        return
    recommendation["products"] = target
    configuration["recommendation"] = recommendation
    bind.execute(
        sa.text(
            """
            UPDATE rule.rule_versions
               SET configuration_json = CAST(:configuration AS jsonb), checksum = :checksum
             WHERE id = :version_id
            """
        ).bindparams(
            configuration=json.dumps(configuration),
            checksum=_checksum(configuration),
            version_id=row["id"],
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE rule.rule_actions
               SET product_codes_json = CAST(:products AS jsonb)
             WHERE rule_version_id = :version_id
            """
        ).bindparams(products=json.dumps(target), version_id=row["id"])
    )


def _update_demo_rule_products(products_by_type: dict[str, list[str]]) -> None:
    for opportunity_type, product_codes in products_by_type.items():
        op.execute(
            sa.text(
                """
                UPDATE opportunity.opportunity_rules
                   SET configuration_json = jsonb_set(
                         configuration_json::jsonb,
                         '{recommended_product_codes}',
                         CAST(:products AS jsonb),
                         true
                       )::json
                 WHERE opportunity_type = :opportunity_type
                   AND version = '1'
                   AND created_by = 'demo-data-generator'
                """
            ).bindparams(
                opportunity_type=opportunity_type,
                products=json.dumps(product_codes),
            )
        )


def upgrade() -> None:
    op.execute(
        sa.text('ALTER TABLE "product"."products" ADD COLUMN IF NOT EXISTS "family" VARCHAR(80)')
    )
    op.execute(
        sa.text('ALTER TABLE "product"."products" ADD COLUMN IF NOT EXISTS "description" TEXT')
    )
    op.execute(
        sa.text(
            'ALTER TABLE "product"."products" ADD COLUMN IF NOT EXISTS "source_url" VARCHAR(500)'
        )
    )
    for code, family in LEGACY_FAMILIES.items():
        op.execute(
            sa.text(
                'UPDATE "product"."products" SET family=:family '
                "WHERE product_code=:code AND family IS NULL"
            ).bindparams(code=code, family=family)
        )
    op.execute(
        sa.text('UPDATE "product"."products" SET family=\'UNCLASSIFIED\' WHERE family IS NULL')
    )
    op.execute(
        sa.text('UPDATE "product"."products" SET description=\'\' WHERE description IS NULL')
    )
    op.alter_column(
        "products",
        "family",
        schema="product",
        existing_type=sa.String(length=80),
        nullable=False,
        server_default="UNCLASSIFIED",
    )
    op.alter_column(
        "products",
        "description",
        schema="product",
        existing_type=sa.Text(),
        nullable=False,
        server_default="",
    )
    op.alter_column(
        "opportunities",
        "rule_version",
        schema="opportunity",
        existing_type=sa.String(length=30),
        type_=sa.String(length=80),
        existing_nullable=False,
    )
    op.alter_column(
        "decision_audit",
        "rule_version",
        schema="opportunity",
        existing_type=sa.String(length=30),
        type_=sa.String(length=80),
        existing_nullable=False,
    )
    _update_demo_rule_products(DEMO_RULE_PRODUCTS)
    _update_demo_studio_products(LEGACY_STUDIO_PRODUCTS, DEMO_STUDIO_PRODUCTS)


def downgrade() -> None:
    _update_demo_studio_products(DEMO_STUDIO_PRODUCTS, LEGACY_STUDIO_PRODUCTS)
    _update_demo_rule_products(LEGACY_RULE_PRODUCTS)
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM opportunity.opportunities WHERE length(rule_version) > 30
                UNION ALL
                SELECT 1 FROM opportunity.decision_audit WHERE length(rule_version) > 30
              ) THEN
                RAISE EXCEPTION '0018 downgrade blocked: rule_version exceeds 30 characters';
              END IF;
            END $$;
            """
        )
    )
    op.alter_column(
        "decision_audit",
        "rule_version",
        schema="opportunity",
        existing_type=sa.String(length=80),
        type_=sa.String(length=30),
        existing_nullable=False,
    )
    op.alter_column(
        "opportunities",
        "rule_version",
        schema="opportunity",
        existing_type=sa.String(length=80),
        type_=sa.String(length=30),
        existing_nullable=False,
    )
    op.drop_column("products", "source_url", schema="product")
    op.drop_column("products", "description", schema="product")
    op.drop_column("products", "family", schema="product")
