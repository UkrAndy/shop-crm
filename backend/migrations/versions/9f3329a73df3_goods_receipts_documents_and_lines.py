"""goods receipts: documents and lines

Revision ID: 9f3329a73df3
Revises: 474bc809b5d4
Create Date: 2026-08-30 20:51:26.999589

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f3329a73df3"
down_revision: str | Sequence[str] | None = "474bc809b5d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "goods_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("counterparty_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # A CHECK rather than a native ENUM: both are enforced by the database,
        # but `ALTER TYPE ... ADD VALUE` cannot run inside a transaction block,
        # which would make every future status an awkward migration.
        sa.CheckConstraint("status IN ('draft', 'posted')", name="ck_goods_receipts_status"),
        sa.ForeignKeyConstraint(
            ["counterparty_id"], ["counterparties_stub.id"], ondelete="RESTRICT"
        ),
        # RESTRICT: a posted document must not vanish because its author was removed.
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_goods_receipts_organization_id"),
        "goods_receipts",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "goods_receipt_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("purchase_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("purchase_price >= 0", name="ck_goods_receipt_lines_price_non_negative"),
        # Positive, not merely non-negative: a zero-quantity line means nothing
        # arrived, which is a line that should not exist.
        sa.CheckConstraint("quantity > 0", name="ck_goods_receipt_lines_quantity_positive"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["receipt_id"], ["goods_receipts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_goods_receipt_lines_receipt_id"),
        "goods_receipt_lines",
        ["receipt_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_goods_receipt_lines_receipt_id"), table_name="goods_receipt_lines")
    op.drop_table("goods_receipt_lines")
    op.drop_index(op.f("ix_goods_receipts_organization_id"), table_name="goods_receipts")
    op.drop_table("goods_receipts")
