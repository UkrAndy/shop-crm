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
    Enum,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.conventions import MONEY, TIMESTAMPTZ, UUID_PK


class ReceiptStatus(enum.StrEnum):
    DRAFT = "draft"
    POSTED = "posted"


# `native_enum=False` renders `VARCHAR(16)` rather than a PostgreSQL `ENUM`
# type: `ALTER TYPE ... ADD VALUE` cannot run inside a transaction block against
# a pre-existing type, so a native enum would turn every future status into an
# awkward migration.
#
# The type's job here is **conversion** — a plain `String` column typed
# `Mapped[ReceiptStatus]` hands back a bare `str` after a round trip through the
# database, so `status is ReceiptStatus.DRAFT` is quietly False and the
# annotation is a lie. `values_callable` is load-bearing too: without it
# SQLAlchemy stores the member *names* (`DRAFT`) instead of the values.
#
# `create_constraint=False` on purpose. SQLAlchemy would add the CHECK through a
# DDL event that never appears in `Table.constraints`, and Alembic's
# check-constraint comparison then reports it as an orphan on every run. The
# constraint is declared explicitly below instead, where autogenerate can see it.
def _status_values(enum_cls: type[ReceiptStatus]) -> list[str]:
    return [member.value for member in enum_cls]


_STATUS = Enum(
    ReceiptStatus,
    native_enum=False,
    create_constraint=False,
    length=16,
    values_callable=_status_values,
)

_STATUS_VALUES = ", ".join(f"'{member.value}'" for member in ReceiptStatus)


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
        _STATUS, default=ReceiptStatus.DRAFT, server_default=ReceiptStatus.DRAFT.value
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
        order_by="GoodsReceiptLine.position",
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
        CheckConstraint("position >= 0", name="ck_goods_receipt_lines_position_non_negative"),
        # DEFERRABLE because replacing a document's lines inserts the new set
        # before deleting the old one within a single flush; checking at commit
        # lets that pass while still refusing two lines to claim one slot.
        UniqueConstraint(
            "receipt_id",
            "position",
            name="uq_goods_receipt_lines_position",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, default=uuid.uuid4)
    receipt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("goods_receipts.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))

    # Line order is *data*, not an accident of insertion time. `now()` is the
    # transaction timestamp in PostgreSQL, so every line of one document shares
    # it — ordering by `created_at` would return them in arbitrary order.
    position: Mapped[int] = mapped_column(Integer)

    # Whole units (PRD: «кількість — ціле»).
    quantity: Mapped[int] = mapped_column(Integer)
    purchase_price: Mapped[Decimal] = mapped_column(MONEY)

    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())

    receipt: Mapped[GoodsReceipt] = relationship(back_populates="lines")
