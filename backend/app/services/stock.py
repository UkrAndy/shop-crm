"""Stock balance.

`SUM(quantity_delta)` over `stock_movements`, computed on demand. There is no
stored quantity anywhere in this path, and that is the point: a counter can drift
from the movements that were supposed to maintain it, and then two numbers
disagree with no way to say which is right. One source of truth, aggregated.

`ix_stock_movements_scope` covers `(organization_id, warehouse_id, product_id)`,
which is exactly what the `WHERE` clause below filters on.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import NamedTuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import OrganizationForbiddenError
from app.models.catalog import Product
from app.models.identity import Organization
from app.models.inventory import StockMovement

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50


class BalanceRow(NamedTuple):
    product_id: uuid.UUID
    product_name: str
    warehouse_id: uuid.UUID | None
    quantity_balance: int
    last_movement_at: dt.datetime | None


def _require_product(
    session: Session, organization: Organization, product_id: uuid.UUID
) -> Product:
    """A product outside the caller's organization is indistinguishable from one
    that does not exist, because the lookup is scoped and never learns which."""
    product = session.scalar(
        select(Product).where(Product.organization_id == organization.id, Product.id == product_id)
    )
    if product is None:
        raise OrganizationForbiddenError
    return product


def balance_for_product(
    session: Session,
    organization: Organization,
    product: Product,
    warehouse_id: uuid.UUID | None = None,
) -> BalanceRow:
    """The balance of one product, **zero** when nothing has ever moved.

    Not 404: "nothing has arrived yet" is a valid and informative state, quite
    unlike "this product does not exist". Collapsing the two would make an empty
    shelf indistinguishable from a typo.
    """
    statement = select(
        func.coalesce(func.sum(StockMovement.quantity_delta), 0),
        func.max(StockMovement.created_at),
    ).where(
        StockMovement.organization_id == organization.id,
        StockMovement.product_id == product.id,
    )
    if warehouse_id is not None:
        statement = statement.where(StockMovement.warehouse_id == warehouse_id)

    total, last_at = session.execute(statement).one()

    return BalanceRow(
        product_id=product.id,
        product_name=product.name,
        warehouse_id=warehouse_id,
        quantity_balance=int(total),
        last_movement_at=last_at,
    )


def list_balances(
    session: Session,
    organization: Organization,
    *,
    product_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> tuple[list[BalanceRow], int]:
    """Balances for the caller's organization.

    With a `product_id`, exactly one row — including a zero one. Without,
    only products that have actually moved: a catalog-wide list of zeros is
    noise, and the unfiltered view answers "what is in the warehouse".
    """
    if product_id is not None:
        product = _require_product(session, organization, product_id)
        return [balance_for_product(session, organization, product, warehouse_id)], 1

    grouped = (
        select(
            StockMovement.product_id,
            StockMovement.warehouse_id,
            func.sum(StockMovement.quantity_delta).label("quantity_balance"),
            func.max(StockMovement.created_at).label("last_movement_at"),
        )
        .where(StockMovement.organization_id == organization.id)
        .group_by(StockMovement.product_id, StockMovement.warehouse_id)
    )
    if warehouse_id is not None:
        grouped = grouped.where(StockMovement.warehouse_id == warehouse_id)

    summary = grouped.subquery()
    # Joined rather than looked up per row: the page renders a table, and a query
    # per line is how a list page becomes slow without anyone noticing.
    statement = (
        select(
            summary.c.product_id,
            Product.name,
            summary.c.warehouse_id,
            summary.c.quantity_balance,
            summary.c.last_movement_at,
        )
        .join(Product, Product.id == summary.c.product_id)
        .order_by(Product.name)
    )

    total = session.scalar(select(func.count()).select_from(summary)) or 0
    rows = session.execute(statement.limit(limit).offset(offset)).all()

    return [
        BalanceRow(
            product_id=row[0],
            product_name=row[1],
            warehouse_id=row[2],
            quantity_balance=int(row[3]),
            last_movement_at=row[4],
        )
        for row in rows
    ], total
