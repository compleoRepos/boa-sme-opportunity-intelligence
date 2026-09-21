"""Merge governed ML Studio and public product catalogue branches.

Revision ID: 0019_ml_studio_catalog_merge
Revises: 0018_ml_studio, 0018_product_catalog
"""

from __future__ import annotations

revision = "0019_ml_studio_catalog_merge"
down_revision = ("0018_ml_studio", "0018_product_catalog")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Join both additive migration branches without additional DDL."""


def downgrade() -> None:
    """Split back to both additive migration branches without additional DDL."""
