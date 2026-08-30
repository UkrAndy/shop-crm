"""Goods receipt API contract.

Money crosses the wire as a string, for the reason set out in
`schemas/product.py`: JSON numbers are doubles, and a price that round-trips
through one can drift.
"""

import datetime as dt
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.goods_receipt import ReceiptStatus

Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]

# Whole units, strictly positive: a zero-quantity line means nothing arrived.
# Bounded above so a typo cannot request a quantity the `integer` column
# cannot hold, which would surface as a 500 instead of a validation error.
Quantity = Annotated[int, Field(gt=0, le=1_000_000_000)]


class GoodsReceiptLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    quantity: Quantity
    purchase_price: Money


class GoodsReceiptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counterparty_id: UUID
    # A draft may legitimately start empty and be filled in later. Posting is
    # what requires lines (Issue 20), not drafting.
    #
    # A literal `[]` is safe here: Pydantic deep-copies model defaults, unlike a
    # plain Python default argument.
    lines: list[GoodsReceiptLineInput] = []


class GoodsReceiptUpdate(BaseModel):
    """Partial update guarded by the version the client last saw.

    `lines` distinguishes **absent** from **empty**: omitting it leaves the
    document's lines alone, while sending `[]` clears them. Collapsing the two
    would let a supplier change silently wipe a delivery.
    """

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    counterparty_id: UUID | None = None
    lines: list[GoodsReceiptLineInput] | None = None


class GoodsReceiptLinePublic(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str
    quantity: int
    purchase_price: Decimal
    # Computed server-side, where the values are `Decimal`.
    line_total: Decimal


class GoodsReceiptSummary(BaseModel):
    """Everything the list page shows, so a table needs no call per row."""

    id: UUID
    status: ReceiptStatus
    version: int
    counterparty_id: UUID
    counterparty_name: str
    warehouse_id: UUID
    created_by: UUID
    created_by_email: str
    created_at: dt.datetime
    total: Decimal


class GoodsReceiptPublic(GoodsReceiptSummary):
    lines: list[GoodsReceiptLinePublic]


class GoodsReceiptPage(BaseModel):
    items: list[GoodsReceiptSummary]
    total: int
    limit: int
    offset: int


class CounterpartyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=255)]

    @field_validator("name", mode="before")
    @classmethod
    def strip_whitespace(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CounterpartyPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
