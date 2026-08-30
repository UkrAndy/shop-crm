"""inventory: batches, movements and audit

Revision ID: 5951163f2067
Revises: d30b399f3635
Create Date: 2026-08-30 21:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5951163f2067"
down_revision: str | Sequence[str] | None = "d30b399f3635"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Append-only, enforced by the database rather than by convention.
#
# Research §386 asks for immutability "by application policy and database
# constraints where practical". A trigger is practical, and it is the only form
# that holds against writers who never read the policy: a migration, a fix-up
# script in a psql session, a future service.
#
# `UPDATE` and `DELETE` are refused. `DELETE` here means a direct one — the
# `organizations` foreign key is `ON DELETE CASCADE` for other tables, but
# movements and audit rows deliberately are **not** reachable that way, so
# removing a tenant with posted history is a conscious operation rather than a
# side effect of one row disappearing.
_APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION refuse_modification() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'relation % is append-only; % is not permitted', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""

_APPEND_ONLY_TABLES = ("stock_movements", "audit_log")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        # Not a foreign key on purpose: history must outlive its subject.
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("btrim(action) <> ''", name="ck_audit_log_action_not_blank"),
        sa.CheckConstraint("btrim(entity_type) <> ''", name="ck_audit_log_entity_type_not_blank"),
        # RESTRICT: an action whose actor has been erased is unattributable.
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_log_entity",
        "audit_log",
        ["organization_id", "entity_type", "entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_log_recent", "audit_log", ["organization_id", "created_at"], unique=False
    )

    op.create_table(
        "inventory_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), nullable=False),
        # The batch keeps the price it arrived at: FIFO cost depends on it.
        sa.Column("purchase_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("remaining_quantity", sa.Integer(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("purchase_price >= 0", name="ck_inventory_batches_price_non_negative"),
        sa.CheckConstraint("quantity > 0", name="ck_inventory_batches_quantity_positive"),
        # More left than ever arrived, or less than none, is a state the database
        # should refuse to hold rather than one to detect later.
        sa.CheckConstraint(
            "remaining_quantity >= 0 AND remaining_quantity <= quantity",
            name="ck_inventory_batches_remaining_within_quantity",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["receipt_id"], ["goods_receipts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inventory_batches_scope",
        "inventory_batches",
        ["organization_id", "warehouse_id", "product_id"],
        unique=False,
    )

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        # Signed: balance is SUM(quantity_delta) over the scope.
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column(
            "movement_type",
            sa.Enum(
                "receipt",
                "sale",
                "adjustment",
                name="movementtype",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        # Not a foreign key: the causing document may later be a sale, a
        # transfer or an adjustment, and history must not depend on which table
        # it lives in.
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "movement_type IN ('receipt', 'sale', 'adjustment')", name="ck_stock_movements_type"
        ),
        sa.CheckConstraint("quantity_delta <> 0", name="ck_stock_movements_delta_non_zero"),
        sa.ForeignKeyConstraint(["batch_id"], ["inventory_batches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_stock_movements_scope",
        "stock_movements",
        ["organization_id", "warehouse_id", "product_id"],
        unique=False,
    )

    op.execute(_APPEND_ONLY_FUNCTION)
    for table in _APPEND_ONLY_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER {table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION refuse_modification();
            """
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table in _APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table};")
    op.execute("DROP FUNCTION IF EXISTS refuse_modification();")

    op.drop_index("ix_stock_movements_scope", table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_index("ix_inventory_batches_scope", table_name="inventory_batches")
    op.drop_table("inventory_batches")
    op.drop_index("ix_audit_log_recent", table_name="audit_log")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_table("audit_log")
