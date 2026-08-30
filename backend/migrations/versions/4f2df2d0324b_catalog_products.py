"""catalog: products

Revision ID: 4f2df2d0324b
Revises: 1a8834c7fd44
Create Date: 2026-08-30 19:58:35.682032

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f2df2d0324b"
down_revision: str | Sequence[str] | None = "1a8834c7fd44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("barcode", sa.String(length=64), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("purchase_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_products_name_not_blank"),
        sa.CheckConstraint("purchase_price >= 0", name="ck_products_price_non_negative"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_products_organization_id"), "products", ["organization_id"], unique=False
    )
    # Partial: any number of products may have no barcode, while the ones that
    # do stay unique within their organization.
    op.create_index(
        "uq_products_organization_barcode",
        "products",
        ["organization_id", "barcode"],
        unique=True,
        postgresql_where=sa.text("barcode IS NOT NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_products_organization_barcode",
        table_name="products",
        postgresql_where=sa.text("barcode IS NOT NULL"),
    )
    op.drop_index(op.f("ix_products_organization_id"), table_name="products")
    op.drop_table("products")
