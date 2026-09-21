"""Add governed multibank flow visibility and domiciliation metadata.

Revision ID: 0020_multibank_visibility
Revises: 0019_ml_studio_catalog_merge
"""

from __future__ import annotations

import hashlib
import json
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020_multibank_visibility"
down_revision = "0019_ml_studio_catalog_merge"
branch_labels = None
depends_on = None

HYPOTHESIS = "HYPOTHÈSE À VALIDER AVEC BOA"
FLOW_RULE_ID = uuid.uuid5(uuid.NAMESPACE_URL, "boa-sme-oi:opp-rule:FLOW_DOMICILIATION:1")
CATEGORY_ID = uuid.uuid5(
    uuid.NAMESPACE_URL, "boa-sme-oi:transaction-category:INTER_BANK_SELF_TRANSFER:multibank-v1"
)
FEATURE_SET_ID = uuid.uuid5(
    uuid.NAMESPACE_URL, "boa-sme-oi:feature-set:sales-features-v3-multibank"
)

FLOW_RULE = {
    "enabled": False,
    "version": "1",
    "horizon": "1-3_MONTHS",
    "what": (
        "Part de flux estimée faible ou partielle chez BANK OF AFRICA : proposer la "
        "domiciliation des flux et des salaires."
    ),
    "when": "Contacter dans les 1 à 3 mois.",
    "all_conditions": [
        {
            "key": "flow_visibility_opportunity",
            "operator": "eq",
            "value": True,
            "label": "Visibilité des flux partielle ou faible",
        },
        {
            "key": "no_recent_domiciliation_action",
            "operator": "eq",
            "value": True,
            "label": "Aucune action de domiciliation depuis 180 jours",
        },
    ],
    "any_conditions": [
        {
            "key": "inflow_growth_rate",
            "operator": "gt",
            "value": 0,
            "label": "Croissance des encaissements chez BOA",
        },
        {
            "key": "fingerprint_growth_90d",
            "operator": "gt",
            "value": 0,
            "label": "Empreintes de multibancarisation en hausse sur 90 jours",
        },
        {
            "key": "declared_turnover_growth_rate",
            "operator": "gt",
            "value": 0,
            "label": "Chiffre d'affaires déclaré en hausse",
        },
    ],
    "recommended_product_codes": [
        "BOA_PACK_BUSINESS_PME",
        "BOA_BUSINESS_ONLINE",
        "BOA_VIREMENT_MASSE",
        "BOA_PRELEVEMENT_MASSE",
    ],
    "confidence_weights": {
        "signal_strength": 35,
        "persistence": 15,
        "baseline_separation": 10,
        "product_gap": 10,
        "recency": 10,
        "data_quality": 10,
        "corroboration": 10,
    },
    "priority_defaults": {
        "signal_strength": 0.85,
        "urgency": 0.7,
        "recency": 1.0,
        "relationship_context": 0.75,
        "product_gap": 0.8,
    },
    "minimum_data_coverage": 0.83,
    "visibility_sensitivity": "ROBUST",
    "visibility_policy": {
        "highShare": 0.7,
        "partialShare": 0.3,
        "fingerprints90d": 2,
        "partialPenaltyPoints": -10,
        "lowPenaltyPoints": -25,
        "unknownPenaltyPoints": -5,
        "domiciliationCooldownDays": 180,
        "status": HYPOTHESIS,
    },
    "lifecycle": {
        "validity_days": 90,
        "dismissed_cooldown_days": 180,
        "converted_cooldown_days": 180,
        "deferred_cooldown_days": 30,
        "expired_cooldown_days": 7,
    },
}

FEATURE_REGISTRY = {
    "featureSetVersion": "sales-features-v3-multibank",
    "status": "REGISTERED_INACTIVE",
    "features": [
        {
            "name": "flow_visibility_share",
            "type": "nullable_float",
            "meaning": "Part estimée des encaissements annuels visibles chez BOA, bornée à 1.",
            "source": "analytics.flow_visibility_snapshots",
            "leakagePolicy": (
                "Utiliser uniquement un snapshot asOf antérieur ou égal à l'observation."
            ),
        },
        {
            "name": "flow_visibility_share_available",
            "type": "boolean",
            "meaning": "Indique si une part chiffrée est disponible.",
            "source": "analytics.flow_visibility_snapshots",
            "leakagePolicy": "Même coupe temporelle que flow_visibility_share.",
        },
        {
            "name": "banking_relationship_declared",
            "type": "categorical_encoded",
            "encoding": {"UNKNOWN": 0, "SECONDARY": 1, "PRIMARY": 2, "EXCLUSIVE": 3},
            "source": "customer.customers",
            "leakagePolicy": "Une déclaration CC postérieure à l'observation est exclue.",
        },
    ],
    "activation": (
        "Aucun modèle actif n'utilise cette version; aucun réentraînement dans le lot 13."
    ),
}


def upgrade() -> None:
    op.add_column("customers", sa.Column("banking_relationship", sa.String(20)), schema="customer")
    op.add_column(
        "customers",
        sa.Column("banking_relationship_declared_at", sa.DateTime(timezone=True)),
        schema="customer",
    )
    op.add_column(
        "customers",
        sa.Column("banking_relationship_declared_by", sa.String(120)),
        schema="customer",
    )
    op.add_column(
        "customers", sa.Column("banking_relationship_reason", sa.Text()), schema="customer"
    )
    op.add_column(
        "customers", sa.Column("banking_relationship_source", sa.String(30)), schema="customer"
    )
    op.add_column("customers", sa.Column("declared_turnover", sa.Numeric(19, 4)), schema="customer")
    op.add_column("customers", sa.Column("declared_turnover_as_of", sa.Date()), schema="customer")
    op.add_column(
        "customers", sa.Column("declared_turnover_entered_by", sa.String(120)), schema="customer"
    )
    op.add_column(
        "customers", sa.Column("declared_turnover_source", sa.String(30)), schema="customer"
    )
    op.create_check_constraint(
        "ck_customers_banking_relationship",
        "customers",
        "banking_relationship IS NULL OR banking_relationship IN "
        "('EXCLUSIVE','PRIMARY','SECONDARY','UNKNOWN')",
        schema="customer",
    )
    op.create_check_constraint(
        "ck_customers_declared_turnover_positive",
        "customers",
        "declared_turnover IS NULL OR declared_turnover > 0",
        schema="customer",
    )
    op.create_table(
        "banking_relationship_declarations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer.customers.id"),
            nullable=False,
        ),
        sa.Column("banking_relationship", sa.String(20), nullable=False),
        sa.Column("declared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("declared_by", sa.String(120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("declared_turnover", sa.Numeric(19, 4)),
        sa.Column("declared_turnover_as_of", sa.Date()),
        sa.Column("declared_turnover_source", sa.String(30)),
        sa.CheckConstraint(
            "banking_relationship IN ('EXCLUSIVE','PRIMARY','SECONDARY','UNKNOWN')",
            name="ck_banking_declaration_relationship",
        ),
        sa.CheckConstraint(
            "declared_turnover IS NULL OR declared_turnover > 0",
            name="ck_banking_declaration_turnover_positive",
        ),
        schema="customer",
    )
    op.create_index(
        "ix_banking_declarations_customer_time",
        "banking_relationship_declarations",
        ["customer_id", "declared_at"],
        schema="customer",
    )

    op.add_column(
        "transactions", sa.Column("counterparty_name", sa.String(180)), schema="transaction"
    )
    op.add_column(
        "transactions", sa.Column("remittance_information", sa.String(500)), schema="transaction"
    )
    op.add_column(
        "transactions",
        sa.Column("externally_domiciled", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="transaction",
    )
    op.add_column(
        "opportunity_actions",
        sa.Column("opportunity_type", sa.String(80)),
        schema="action",
    )

    op.create_table(
        "flow_visibility_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_ref", sa.String(40), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("estimated_share", sa.Numeric(8, 6)),
        sa.Column("method", sa.String(40), nullable=False),
        sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fingerprint_count_90d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fingerprint_previous_90d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("categorization_coverage", sa.Numeric(8, 6), nullable=False, server_default="0"),
        sa.Column("calculation_version", sa.String(40), nullable=False),
        sa.Column("input_watermark", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.UniqueConstraint(
            "customer_id", "as_of_date", "calculation_version", name="uq_flow_visibility_snapshot"
        ),
        sa.CheckConstraint(
            "level IN ('HIGH','PARTIAL','LOW','UNKNOWN')", name="ck_flow_visibility_level"
        ),
        sa.CheckConstraint(
            "estimated_share IS NULL OR estimated_share BETWEEN 0 AND 1",
            name="ck_flow_visibility_share",
        ),
        schema="analytics",
    )
    op.create_index(
        "ix_flow_visibility_customer_asof",
        "flow_visibility_snapshots",
        ["customer_id", "as_of_date"],
        schema="analytics",
    )
    op.create_table(
        "flow_visibility_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("policy_id", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("configuration_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.UniqueConstraint("policy_id", "version", name="uq_flow_visibility_policy_version"),
        schema="analytics",
    )
    op.create_index(
        "uq_flow_visibility_policy_active",
        "flow_visibility_policies",
        ["policy_id"],
        unique=True,
        postgresql_where=sa.text("active = true"),
        schema="analytics",
    )
    op.execute(
        sa.text(
            """
            INSERT INTO analytics.flow_visibility_policies
              (id, policy_id, version, active, configuration_json, justification, created_by)
            VALUES
              (:id, 'multibank-flow-visibility', 1, true, CAST(:configuration AS jsonb),
               :justification, 'migration-0020')
            """
        ).bindparams(
            id=uuid.uuid5(uuid.NAMESPACE_URL, "boa-sme-oi:flow-visibility-policy:1"),
            configuration=json.dumps(FLOW_RULE["visibility_policy"], sort_keys=True),
            justification=HYPOTHESIS,
        )
    )

    op.add_column(
        "opportunities",
        sa.Column(
            "recommendation_nature", sa.String(30), nullable=False, server_default="NEED_DISCOVERY"
        ),
        schema="opportunity",
    )
    op.create_check_constraint(
        "ck_opportunity_recommendation_nature",
        "opportunities",
        "recommendation_nature IN ('NEED_DISCOVERY','WIN_BACK')",
        schema="opportunity",
    )

    op.create_table(
        "feature_set_registry",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("feature_set_version", sa.String(40), nullable=False, unique=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("definition_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(120), nullable=False),
        schema="feature_store",
    )

    category_payload = (
        "SYNTHETIC_POC|INTER_BANK_SELF_TRANSFER|multibank-v1|Transfert interbancaire vers soi-même"
    )
    op.execute(
        sa.text(
            """
            INSERT INTO config.transaction_categories
              (id, category_code, version, label, active, provenance, checksum, reason, created_by)
            VALUES
              (:id, 'INTER_BANK_SELF_TRANSFER', 'multibank-v1',
               'Transfert interbancaire vers soi-même', true, 'SYNTHETIC_POC', :checksum,
               :reason, 'migration-0020')
            ON CONFLICT (category_code, version) DO NOTHING
            """
        ).bindparams(
            id=CATEGORY_ID,
            checksum=hashlib.sha256(category_payload.encode()).hexdigest(),
            reason=f"Règle paramétrable du POC multibancaire; {HYPOTHESIS}.",
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO opportunity.opportunity_rules
              (id, opportunity_type, version, configuration_json, active,
               created_at, updated_at, created_by)
            VALUES (:id, 'FLOW_DOMICILIATION', '1', CAST(:configuration AS jsonb),
                    false, now(), now(), 'migration-0020')
            ON CONFLICT (opportunity_type, version) DO NOTHING
            """
        ).bindparams(id=FLOW_RULE_ID, configuration=json.dumps(FLOW_RULE, ensure_ascii=False))
    )
    feature_json = json.dumps(FEATURE_REGISTRY, sort_keys=True, ensure_ascii=False)
    op.execute(
        sa.text(
            """
            INSERT INTO feature_store.feature_set_registry
              (id, feature_set_version, status, definition_json, checksum, created_by)
            VALUES (:id, 'sales-features-v3-multibank', 'REGISTERED_INACTIVE',
                    CAST(:definition AS jsonb), :checksum, 'migration-0020')
            ON CONFLICT (feature_set_version) DO NOTHING
            """
        ).bindparams(
            id=FEATURE_SET_ID,
            definition=feature_json,
            checksum=hashlib.sha256(feature_json.encode()).hexdigest(),
        )
    )

    op.execute(
        sa.text(
            "GRANT USAGE ON SCHEMA analytics TO customer_service, product_service, "
            "opportunity_service, portfolio_service, feature_store_service, "
            "rule_management_service"
        )
    )
    op.execute(sa.text("GRANT SELECT ON analytics.flow_visibility_snapshots TO customer_service"))
    op.execute(
        sa.text(
            "GRANT SELECT, INSERT, UPDATE ON analytics.flow_visibility_snapshots "
            "TO analytics_service"
        )
    )
    op.execute(sa.text("GRANT SELECT ON analytics.flow_visibility_policies TO analytics_service"))
    op.execute(
        sa.text(
            "GRANT SELECT, INSERT, UPDATE ON analytics.flow_visibility_policies "
            "TO opportunity_service"
        )
    )
    op.execute(
        sa.text(
            "GRANT SELECT, UPDATE ON analytics.flow_visibility_policies TO rule_management_service"
        )
    )
    op.execute(
        sa.text(
            "GRANT SELECT ON analytics.flow_visibility_snapshots TO product_service, "
            "opportunity_service, portfolio_service, feature_store_service, "
            "rule_management_service"
        )
    )
    op.execute(
        sa.text("GRANT USAGE ON SCHEMA customer TO analytics_service, feature_store_service")
    )
    op.execute(
        sa.text("GRANT SELECT ON customer.customers TO analytics_service, feature_store_service")
    )
    op.execute(
        sa.text(
            "GRANT SELECT, INSERT ON customer.banking_relationship_declarations TO customer_service"
        )
    )
    op.execute(
        sa.text("GRANT USAGE ON SCHEMA action TO opportunity_service, rule_management_service")
    )
    op.execute(
        sa.text(
            "GRANT SELECT ON action.opportunity_actions TO "
            "opportunity_service, rule_management_service"
        )
    )
    op.execute(
        sa.text("GRANT USAGE ON SCHEMA feature_store TO feature_store_service, ml_engine_service")
    )
    op.execute(
        sa.text(
            "GRANT SELECT ON feature_store.feature_set_registry TO "
            "feature_store_service, ml_engine_service"
        )
    )


def downgrade() -> None:
    protected_rows = (
        op.get_bind()
        .execute(
            sa.text(
                """
            SELECT
              (SELECT count(*) FROM customer.banking_relationship_declarations
                 WHERE source <> 'SYNTHETIC_POC')
            + (SELECT count(*) FROM customer.customers
                 WHERE banking_relationship IS NOT NULL
                    OR banking_relationship_declared_at IS NOT NULL
                    OR banking_relationship_declared_by IS NOT NULL
                    OR banking_relationship_reason IS NOT NULL
                    OR banking_relationship_source IS NOT NULL
                    OR declared_turnover IS NOT NULL
                    OR declared_turnover_as_of IS NOT NULL
                    OR declared_turnover_entered_by IS NOT NULL
                    OR declared_turnover_source IS NOT NULL)
            + (SELECT count(*) FROM transaction.transactions
                 WHERE counterparty_name IS NOT NULL
                    OR remittance_information IS NOT NULL
                    OR externally_domiciled IS NOT NULL)
            + (SELECT count(*) FROM opportunity.opportunities
                 WHERE recommendation_nature IS NOT NULL)
            + (SELECT count(*) FROM action.opportunity_actions
                 WHERE opportunity_type IS NOT NULL
                   AND actor_subject_id <> 'demo-data-generator')
            + (SELECT count(*) FROM analytics.flow_visibility_snapshots snapshot
                 JOIN customer.customers customer ON customer.id = snapshot.customer_id
                WHERE customer.created_by <> 'demo-data-generator')
            + (SELECT count(*) FROM analytics.flow_visibility_policies
                WHERE created_by <> 'migration-0020')
            + (SELECT count(*) FROM feature_store.feature_set_registry
                WHERE created_by <> 'migration-0020')
            """
            )
        )
        .scalar_one()
    )
    if protected_rows:
        raise RuntimeError(
            "0020 downgrade refused: governed multibank data must be exported or removed first."
        )
    op.execute(
        sa.text(
            "REVOKE SELECT ON feature_store.feature_set_registry FROM "
            "feature_store_service, ml_engine_service"
        )
    )
    op.execute(
        sa.text(
            "REVOKE USAGE ON SCHEMA feature_store FROM feature_store_service, ml_engine_service"
        )
    )
    op.execute(
        sa.text(
            "REVOKE SELECT ON action.opportunity_actions FROM "
            "opportunity_service, rule_management_service"
        )
    )
    op.execute(
        sa.text("REVOKE USAGE ON SCHEMA action FROM opportunity_service, rule_management_service")
    )
    op.execute(
        sa.text("REVOKE SELECT ON customer.customers FROM analytics_service, feature_store_service")
    )
    op.execute(
        sa.text(
            "REVOKE SELECT, INSERT ON customer.banking_relationship_declarations "
            "FROM customer_service"
        )
    )
    op.execute(
        sa.text("REVOKE USAGE ON SCHEMA customer FROM analytics_service, feature_store_service")
    )
    op.execute(
        sa.text(
            "REVOKE SELECT ON analytics.flow_visibility_snapshots FROM customer_service, "
            "product_service, opportunity_service, portfolio_service, feature_store_service, "
            "rule_management_service"
        )
    )
    op.execute(
        sa.text(
            "REVOKE SELECT, INSERT, UPDATE ON analytics.flow_visibility_snapshots "
            "FROM analytics_service"
        )
    )
    op.execute(
        sa.text("REVOKE SELECT ON analytics.flow_visibility_policies FROM analytics_service")
    )
    op.execute(
        sa.text(
            "REVOKE SELECT, INSERT, UPDATE ON analytics.flow_visibility_policies "
            "FROM opportunity_service"
        )
    )
    op.execute(
        sa.text(
            "REVOKE SELECT, UPDATE ON analytics.flow_visibility_policies "
            "FROM rule_management_service"
        )
    )
    op.execute(
        sa.text(
            "REVOKE USAGE ON SCHEMA analytics FROM customer_service, product_service, "
            "opportunity_service, portfolio_service, feature_store_service, "
            "rule_management_service"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM opportunity.opportunity_rules WHERE id=:id AND created_by='migration-0020'"
        ).bindparams(id=FLOW_RULE_ID)
    )
    op.execute(
        sa.text(
            "DELETE FROM config.transaction_categories WHERE id=:id AND created_by='migration-0020'"
        ).bindparams(id=CATEGORY_ID)
    )
    op.drop_table("feature_set_registry", schema="feature_store")
    op.drop_column("opportunity_actions", "opportunity_type", schema="action")
    op.drop_constraint(
        "ck_opportunity_recommendation_nature", "opportunities", schema="opportunity", type_="check"
    )
    op.drop_column("opportunities", "recommendation_nature", schema="opportunity")
    op.drop_index(
        "uq_flow_visibility_policy_active",
        table_name="flow_visibility_policies",
        schema="analytics",
    )
    op.drop_table("flow_visibility_policies", schema="analytics")
    op.drop_index(
        "ix_flow_visibility_customer_asof",
        table_name="flow_visibility_snapshots",
        schema="analytics",
    )
    op.drop_table("flow_visibility_snapshots", schema="analytics")
    op.drop_index(
        "ix_banking_declarations_customer_time",
        table_name="banking_relationship_declarations",
        schema="customer",
    )
    op.drop_table("banking_relationship_declarations", schema="customer")
    op.drop_column("transactions", "externally_domiciled", schema="transaction")
    op.drop_column("transactions", "remittance_information", schema="transaction")
    op.drop_column("transactions", "counterparty_name", schema="transaction")
    op.drop_constraint(
        "ck_customers_declared_turnover_positive", "customers", schema="customer", type_="check"
    )
    op.drop_constraint(
        "ck_customers_banking_relationship", "customers", schema="customer", type_="check"
    )
    for column in (
        "declared_turnover_source",
        "declared_turnover_entered_by",
        "declared_turnover_as_of",
        "declared_turnover",
        "banking_relationship_source",
        "banking_relationship_reason",
        "banking_relationship_declared_by",
        "banking_relationship_declared_at",
        "banking_relationship",
    ):
        op.drop_column("customers", column, schema="customer")


__all__ = ["downgrade", "upgrade"]
