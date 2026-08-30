"""goods receipts: documents and lines

Revision ID: d30b399f3635
Revises: 474bc809b5d4
Create Date: 2026-08-30 21:07:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d30b399f3635"
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
        # VARCHAR, not a PostgreSQL ENUM type: `ALTER TYPE ... ADD VALUE` cannot
        # run inside a transaction block, which would make every future status an
        # awkward migration. The CHECK below is the constraint.
        sa.Column(
            "status",
            sa.Enum("draft", "posted", name="receiptstatus", native_enum=False, length=16),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        # Line order is data. `now()` is the transaction timestamp, so every line
        # of one document shares it and `created_at` cannot order them.
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("purchase_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("position >= 0", name="ck_goods_receipt_lines_position_non_negative"),
        sa.CheckConstraint("purchase_price >= 0", name="ck_goods_receipt_lines_price_non_negative"),
        # Positive, not merely non-negative: a zero-quantity line means nothing
        # arrived, which is a line that should not exist.
        sa.CheckConstraint("quantity > 0", name="ck_goods_receipt_lines_quantity_positive"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["receipt_id"], ["goods_receipts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # DEFERRABLE: replacing a document's lines inserts the new set before
        # deleting the old one within a single flush, so the check must wait for
        # commit rather than firing mid-transaction.
        sa.UniqueConstraint(
            "receipt_id",
            "position",
            deferrable=True,
            initially="DEFERRED",
            name="uq_goods_receipt_lines_position",
        ),
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
