"""Stock balance: aggregated from movements, stored nowhere."""

import uuid

from fastapi import APIRouter, Query

from app.api.deps import CurrentOrganization, SessionDep
from app.core.errors import documented
from app.schemas.stock import StockBalancePage, StockBalanceRow
from app.services import stock

router = APIRouter(prefix="/stock-balance", tags=["stock"])


@router.get("", response_model=StockBalancePage, responses=documented(401, 403))
def read_stock_balance(
    organization: CurrentOrganization,
    db: SessionDep,
    # Plain defaults: FastAPI treats them as optional query parameters just as
    # `Query(default=None)` would, without the bare call in a default.
    product_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    limit: int = Query(default=stock.DEFAULT_PAGE_SIZE, ge=1, le=stock.MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> StockBalancePage:
    """Balances for the active organization.

    With `product_id`, exactly one row — **zero** if nothing has ever moved,
    because an empty shelf is a valid answer and a missing product is a
    different question (403, since the lookup is scoped).
    """
    rows, total = stock.list_balances(
        db,
        organization,
        product_id=product_id,
        warehouse_id=warehouse_id,
        limit=limit,
        offset=offset,
    )
    return StockBalancePage(
        items=[StockBalanceRow(**row._asdict()) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
