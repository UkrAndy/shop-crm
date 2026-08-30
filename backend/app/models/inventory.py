"""Warehouses, inventory batches and stock movements.

Stock balance is **aggregated from movements** and stored nowhere. That is the
PRD's central architectural claim, and everything here exists to make it true:
movements are append-only, indexed for the aggregation, and no row in this module
or in `catalog` carries a running quantity.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.conventions import MONEY, TIMESTAMPTZ, UUID_PK


class Warehouse(Base):
    """Where stock sits.

    A reference stub, not a module. The PRD scopes **one warehouse per
    organization** and puts transfers out of scope; the unique constraint below
    encodes that, so the day it changes is a deliberate migration rather than a
    surprise discovered in production.

    **Holds no quantity of its own.**
    """

    __tablename__ = "warehouses"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_warehouses_organization"),
        CheckConstraint("btrim(name) <> ''", name="ck_warehouses_name_not_blank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())


class MovementType(enum.StrEnum):
    RECEIPT = "receipt"
    SALE = "sale"
    ADJUSTMENT = "adjustment"


def _movement_type_values(enum_cls: type[MovementType]) -> list[str]:
    return [member.value for member in enum_cls]


# Same shape as the receipt status: VARCHAR rather than a native ENUM, because
# `ALTER TYPE ... ADD VALUE` cannot run inside a transaction block; the type's
# job here is converting to and from the Python enum, and the CHECK on the table
# is the constraint autogenerate can see.
_MOVEMENT_TYPE = Enum(
    MovementType,
    native_enum=False,
    create_constraint=False,
    length=16,
    values_callable=_movement_type_values,
)

_MOVEMENT_TYPE_VALUES = ", ".join(f"'{member.value}'" for member in MovementType)


class InventoryBatch(Base):
    """A quantity of one product that arrived at one price.

    The batch keeps the price it arrived at rather than reading today's catalog
    price: FIFO cost, in a later phase, depends on exactly that.
    """

    __tablename__ = "inventory_batches"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_inventory_batches_quantity_positive"),
        CheckConstraint("purchase_price >= 0", name="ck_inventory_batches_price_non_negative"),
        # More left than ever arrived, or less than none, is not a state to
        # detect later — it is one the database should refuse to hold.
        CheckConstraint(
            "remaining_quantity >= 0 AND remaining_quantity <= quantity",
            name="ck_inventory_batches_remaining_within_quantity",
        ),
        Index("ix_inventory_batches_scope", "organization_id", "warehouse_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT")
    )
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    receipt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("goods_receipts.id", ondelete="RESTRICT")
    )

    purchase_price: Mapped[Decimal] = mapped_column(MONEY)
    quantity: Mapped[int] = mapped_column(Integer)
    remaining_quantity: Mapped[int] = mapped_column(Integer)

    received_at: Mapped[dt.datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())


class StockMovement(Base):
    """One immutable fact: this much of this product moved, here, because of that.

    **Append-only.** A database trigger refuses `UPDATE` and `DELETE` — see the
    migration — because "immutable by application policy" holds only for code
    that has read the policy, and a migration or a fix-up script has not.

    The sign of `quantity_delta` is the mechanism: balance is `SUM(quantity_delta)`
    over the scope, so an inbound movement is positive and an outbound one
    negative. Sales are out of scope for this slice, but the column is not.
    """

    __tablename__ = "stock_movements"
    __table_args__ = (
        # Nothing moved, so there is nothing to record; a zero row only pollutes
        # the aggregation it contributes nothing to.
        CheckConstraint("quantity_delta <> 0", name="ck_stock_movements_delta_non_zero"),
        CheckConstraint(
            f"movement_type IN ({_MOVEMENT_TYPE_VALUES})", name="ck_stock_movements_type"
        ),
        # The balance query filters on exactly these three, in this order.
        # Without the index it is a sequential scan over every movement the
        # tenant has ever made.
        Index("ix_stock_movements_scope", "organization_id", "warehouse_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT")
    )
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_batches.id", ondelete="RESTRICT")
    )

    quantity_delta: Mapped[int] = mapped_column(Integer)
    movement_type: Mapped[MovementType] = mapped_column(_MOVEMENT_TYPE)

    # The document that caused it. A plain column rather than a foreign key: a
    # movement may later be caused by a sale, a transfer or an adjustment, and
    # history must not depend on which table that document lives in.
    document_id: Mapped[uuid.UUID] = mapped_column(UUID_PK)

    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
