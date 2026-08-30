"""Issue 14 — warehouse and counterparty reference stubs.

These exist to make a goods receipt valid, not as modules in their own right.
The PRD scopes one warehouse per organization and a name-only supplier; the
tests below pin both of those boundaries so the stubs cannot quietly grow.

Acceptance criteria under test:
- every organization resolves to exactly one warehouse;
- a receipt can reference a supplier by id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.models.counterparty import CounterpartyStub
from app.models.inventory import Warehouse
from app.services import inventory

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from app.models.identity import Organization


# --------------------------------------------------------------------------- #
# Default warehouse
# --------------------------------------------------------------------------- #


def test_a_new_organization_resolves_to_a_warehouse(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    org = organization_factory("ФОП Склад")

    warehouse = inventory.default_warehouse(db_session, org)

    assert warehouse.organization_id == org.id
    assert warehouse.name


def test_resolving_twice_returns_the_same_warehouse(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    # Get-or-create, not create: a receipt posted twice must not silently
    # produce a second warehouse to hold the stock.
    org = organization_factory("ФОП Двічі")

    first = inventory.default_warehouse(db_session, org)
    second = inventory.default_warehouse(db_session, org)

    assert first.id == second.id
    assert (
        db_session.scalar(select(Warehouse).where(Warehouse.organization_id == org.id)) is not None
    )


def test_exactly_one_warehouse_per_organization(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    """Enforced by the database, not by the service being careful.

    The PRD puts multiple warehouses and transfers out of scope. Encoding that
    as a constraint means the day it changes is a deliberate migration rather
    than a surprise.
    """
    org = organization_factory("ФОП Один склад")
    inventory.default_warehouse(db_session, org)

    db_session.add(Warehouse(organization_id=org.id, name="Другий склад"))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_warehouses_are_scoped_per_organization(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    first = organization_factory("ФОП A")
    second = organization_factory("ФОП B")

    warehouse_a = inventory.default_warehouse(db_session, first)
    warehouse_b = inventory.default_warehouse(db_session, second)

    assert warehouse_a.id != warehouse_b.id


def test_deleting_an_organization_removes_its_warehouse(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    org = organization_factory("ФОП Зникла")
    inventory.default_warehouse(db_session, org)

    db_session.delete(org)
    db_session.flush()

    assert db_session.scalar(select(Warehouse).where(Warehouse.organization_id == org.id)) is None


# --------------------------------------------------------------------------- #
# Counterparty stub
# --------------------------------------------------------------------------- #


def test_a_supplier_can_be_referenced_by_id(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    org = organization_factory("ФОП Постачальник")

    supplier = CounterpartyStub(organization_id=org.id, name="ТОВ Кава Плюс")
    db_session.add(supplier)
    db_session.flush()

    assert db_session.get(CounterpartyStub, supplier.id) is supplier


def test_supplier_names_are_unique_within_an_organization(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    # The entity is a name and nothing else, so two rows with the same name are
    # indistinguishable — and a user picking between them is picking at random.
    org = organization_factory("ФОП Дублікат")
    db_session.add(CounterpartyStub(organization_id=org.id, name="ТОВ Кава Плюс"))
    db_session.flush()

    db_session.add(CounterpartyStub(organization_id=org.id, name="ТОВ Кава Плюс"))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_the_same_supplier_name_may_exist_in_another_organization(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    first = organization_factory("ФОП Перша")
    second = organization_factory("ФОП Друга")

    db_session.add(CounterpartyStub(organization_id=first.id, name="ТОВ Спільний"))
    db_session.add(CounterpartyStub(organization_id=second.id, name="ТОВ Спільний"))

    db_session.flush()


def test_a_blank_supplier_name_is_rejected(
    db_session: Session, organization_factory: Callable[[str], Organization]
) -> None:
    org = organization_factory("ФОП Порожній")
    db_session.add(CounterpartyStub(organization_id=org.id, name="   "))

    with pytest.raises(IntegrityError):
        db_session.flush()


# --------------------------------------------------------------------------- #
# Boundaries the PRD draws
# --------------------------------------------------------------------------- #


def test_the_counterparty_stub_stays_a_stub() -> None:
    """Contracts, statistics and balances are explicitly out of scope.

    Asserted rather than trusted: a name-only reference entity is precisely the
    kind of table that accretes columns nobody planned.
    """
    columns = set(inspect(CounterpartyStub).columns.keys())

    assert columns == {"id", "organization_id", "name", "created_at"}


def test_the_warehouse_holds_no_stock() -> None:
    # Balance is aggregated from movements. A quantity on the warehouse row
    # would be the same shortcut `products` is already guarded against.
    columns = set(inspect(Warehouse).columns.keys())

    assert "quantity" not in columns
    assert columns == {"id", "organization_id", "name", "created_at"}
