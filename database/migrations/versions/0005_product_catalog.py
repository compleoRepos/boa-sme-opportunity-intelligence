"""Catalogue commercial BANK OF AFRICA : famille, description et source des produits."""

import sqlalchemy as sa
from alembic import op

revision = "0005_product_catalog"
down_revision = "0004_ml_and_portfolio"
branch_labels = None
depends_on = None

# 0001 crée les tables depuis les modèles (create_all) : sur base vide les colonnes
# existent déjà, d'où IF NOT EXISTS pour rester rejouable sur les bases existantes.
COLUMNS = (
    ("family", "VARCHAR(60)"),
    ("description", "TEXT"),
    ("source_url", "VARCHAR(300)"),
)


WIDENED = (
    ("opportunity", "opportunities", "engine_version"),
    ("opportunity", "opportunities", "rule_version"),
    ("opportunity", "decision_audit", "engine_version"),
    ("opportunity", "decision_audit", "rule_version"),
)


def upgrade():
    # Les identifiants Rule Studio (« RULE-XXXXXXXXXXXX:v1 ») et la version du moteur
    # avec re-classement ML dépassaient VARCHAR(30).
    for schema, table, column in WIDENED:
        op.execute(
            sa.text(f'ALTER TABLE "{schema}"."{table}" ALTER COLUMN "{column}" TYPE VARCHAR(80)')
        )
    for name, ddl in COLUMNS:
        op.execute(
            sa.text(f'ALTER TABLE "product"."products" ADD COLUMN IF NOT EXISTS "{name}" {ddl}')
        )


def downgrade():
    for name, _ddl in reversed(COLUMNS):
        op.execute(sa.text(f'ALTER TABLE "product"."products" DROP COLUMN IF EXISTS "{name}"'))
