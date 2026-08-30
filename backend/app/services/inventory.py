"""Warehouse resolution.

One warehouse per organization (PRD §In Scope), created on first use rather than
required up front — an organization that predates this code, or one inserted by
hand, still resolves instead of failing.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.identity import Organization
from app.models.inventory import Warehouse

DEFAULT_WAREHOUSE_NAME = "Основний склад"


def default_warehouse(session: Session, organization: Organization) -> Warehouse:
    """Return the organization's warehouse, creating it if it does not exist yet.

    Get-or-create rather than create: posting a second receipt must not produce
    a second warehouse to hold the stock.

    The insert runs inside a **savepoint**. Two concurrent first-uses would both
    see nothing and both insert; the unique constraint rejects one of them, and
    a savepoint confines that failure so the caller's transaction survives and
    can simply re-read the row the winner created. Flushing directly would poison
    the outer transaction instead, turning a benign race into a failed request.
    """
    existing = session.scalar(select(Warehouse).where(Warehouse.organization_id == organization.id))
    if existing is not None:
        return existing

    warehouse = Warehouse(organization_id=organization.id, name=DEFAULT_WAREHOUSE_NAME)
    try:
        with session.begin_nested():
            session.add(warehouse)
    except IntegrityError:
        # Somebody else created it between our read and our insert.
        won = session.scalar(select(Warehouse).where(Warehouse.organization_id == organization.id))
        assert won is not None, "the unique constraint fired, so a row must exist"
        return won

    return warehouse
