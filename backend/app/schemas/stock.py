"""Stock balance API contract."""

import datetime as dt
from uuid import UUID

from pydantic import BaseModel


class StockBalanceRow(BaseModel):
    product_id: UUID
    product_name: str
    warehouse_id: UUID | None
    # A whole number: quantities are integers throughout (PRD).
    quantity_balance: int
    # `None` when nothing has ever moved — a valid state, not an error.
    last_movement_at: dt.datetime | None


class StockBalancePage(BaseModel):
    items: list[StockBalanceRow]
    total: int
    limit: int
    offset: int
