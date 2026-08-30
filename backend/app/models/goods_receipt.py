"""Goods receipt — the document that brings stock in.

Header plus lines, editable only while `draft`. Posting (Issue 20) turns it into
a batch and a stock movement in one transaction, after which it is immutable.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.conventions import MONEY, TIMESTAMPTZ, UUID_PK


class ReceiptStatus(enum.StrEnum):
    DRAFT = "draft"
    POSTED = "posted"


# A `VARCHAR` plus a `CHECK`, not a PostgreSQL native `ENUM`. Both are enforced
# by the database, which is what the requirement asks for; the difference is
# what happens when the set changes. `ALTER TYPE ... ADD VALUE` cannot run inside
# a transaction block against a pre-existing type, so a native enum turns every
# future status into an awkward migration. The CHECK is a one-line rewrite.
_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in ReceiptStatus)


class GoodsReceipt(Base):
    """Supplier delivery document.

    `version` uses the same `version_id_col` mechanism as `Product`: the guard
    lives in `UPDATE ... WHERE version = ?` rather than in remembering to check.
    """

    __tablename__ = "goods_receipts"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="ck_goods_receipts_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT")
    )
    counterparty_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("counterparties_stub.id", ondelete="RESTRICT")
    )

    status: Mapped[ReceiptStatus] = mapped_column(
        String(16), default=ReceiptStatus.DRAFT, server_default=ReceiptStatus.DRAFT.value
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    # Audit needs an actor. RESTRICT rather than CASCADE: a posted document must
    # not disappear because somebody removed the user who entered it.
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())

    lines: Mapped[list[GoodsReceiptLine]] = relationship(
        back_populates="receipt",
        # `delete-orphan`: editing a draft replaces its lines, and a line that
        # lingered after being removed would be counted at posting time and
        # quietly inflate the stock.
        cascade="all, delete-orphan",
        order_by="GoodsReceiptLine.created_at",
    )

    __mapper_args__ = {"version_id_col": version}


class GoodsReceiptLine(Base):
    """One product arriving, at one price.

    **No stored total.** `quantity × purchase_price` is a second source of truth
    that can only agree with its inputs or be wrong, and the arithmetic is cheap.
    """

    __tablename__ = "goods_receipt_lines"
    __table_args__ = (
        # Positive, not merely non-negative: a zero-quantity line means nothing
        # arrived, which is a line that should not exist.
        CheckConstraint("quantity > 0", name="ck_goods_receipt_lines_quantity_positive"),
        CheckConstraint("purchase_price >= 0", name="ck_goods_receipt_lines_price_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, default=uuid.uuid4)
    receipt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("goods_receipts.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))

    # Whole units (PRD: «кількість — ціле»).
    quantity: Mapped[int] = mapped_column(Integer)
    purchase_price: Mapped[Decimal] = mapped_column(MONEY)

    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())

    receipt: Mapped[GoodsReceipt] = relationship(back_populates="lines")
