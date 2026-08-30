"""Issue 15 — the goods receipt document and its lines.

Acceptance criteria under test:
- status is constrained at the database level, not free text;
- deleting a draft removes its lines, leaving no reachable orphans;
- a non-positive quantity is rejected by the database, not only by Pydantic.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, NamedTuple

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.models.catalog import Product
from app.models.counterparty import CounterpartyStub
from app.models.goods_receipt import GoodsReceipt, GoodsReceiptLine, ReceiptStatus
from app.services import inventory

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from app.models.identity import Organization, User


class Scene(NamedTuple):
    organization: Organization
    user: User
    receipt: GoodsReceipt
    product: Product


@pytest.fixture
def scene(
    db_session: Session,
    user_factory: Callable[..., User],
    organization_factory: Callable[[str], Organization],
) -> Scene:
    """A draft receipt with everything it needs to be valid, and one product."""
    organization = organization_factory("ФОП Надходження")
    user = user_factory("receipts@example.com", organization)
    warehouse = inventory.default_warehouse(db_session, organization)

    supplier = CounterpartyStub(organization_id=organization.id, name="ТОВ Постачальник")
    product = Product(
        organization_id=organization.id,
        name="Кава мелена",
        unit="шт",
        purchase_price=Decimal("100.00"),
    )
    db_session.add_all([supplier, product])
    db_session.flush()

    receipt = GoodsReceipt(
        organization_id=organization.id,
        warehouse_id=warehouse.id,
        counterparty_id=supplier.id,
        created_by=user.id,
    )
    db_session.add(receipt)
    db_session.flush()

    return Scene(organization=organization, user=user, receipt=receipt, product=product)


def line(scene: Scene, **overrides: object) -> GoodsReceiptLine:
    values: dict[str, object] = {
        "receipt_id": scene.receipt.id,
        "product_id": scene.product.id,
        "quantity": 10,
        "purchase_price": Decimal("100.00"),
    }
    values.update(overrides)
    return GoodsReceiptLine(**values)


# --------------------------------------------------------------------------- #
# Status
# --------------------------------------------------------------------------- #


def test_a_new_receipt_is_a_draft(scene: Scene) -> None:
    assert scene.receipt.status is ReceiptStatus.DRAFT


def test_the_database_rejects_an_unknown_status(db_session: Session, scene: Scene) -> None:
    """Constrained at the database level, not merely by the Python enum.

    Raw SQL on purpose: the point is that the constraint holds against writers
    that never load the ORM — a migration, a fix-up script, a future service.
    """
    with pytest.raises((IntegrityError, DBAPIError)):
        db_session.execute(
            text("UPDATE goods_receipts SET status = 'approved' WHERE id = :id"),
            {"id": scene.receipt.id},
        )
        db_session.flush()


@pytest.mark.parametrize("status", list(ReceiptStatus))
def test_every_declared_status_is_accepted(
    db_session: Session, scene: Scene, status: ReceiptStatus
) -> None:
    # The mirror image of the test above: the constraint must not be narrower
    # than the enum, or a legitimate transition would fail in production.
    scene.receipt.status = status

    db_session.flush()


# --------------------------------------------------------------------------- #
# Lines
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("quantity", [0, -1, -100])
def test_a_non_positive_quantity_is_rejected_by_the_database(
    db_session: Session, scene: Scene, quantity: int
) -> None:
    db_session.add(line(scene, quantity=quantity))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_a_negative_line_price_is_rejected(db_session: Session, scene: Scene) -> None:
    db_session.add(line(scene, purchase_price=Decimal("-0.01")))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_line_price_keeps_kopiyka_precision(db_session: Session, scene: Scene) -> None:
    item = line(scene, purchase_price=Decimal("12.34"))
    db_session.add(item)
    db_session.flush()
    db_session.expire(item)

    assert item.purchase_price == Decimal("12.34")
    assert isinstance(item.purchase_price, Decimal)


def test_the_same_product_may_appear_on_two_lines(db_session: Session, scene: Scene) -> None:
    # Price is per line, so the same product arriving at two different prices in
    # one delivery is a real case, not a mistake to prevent.
    db_session.add(line(scene, purchase_price=Decimal("100.00")))
    db_session.add(line(scene, purchase_price=Decimal("110.00")))

    db_session.flush()


def test_deleting_the_receipt_removes_its_lines(db_session: Session, scene: Scene) -> None:
    db_session.add(line(scene))
    db_session.add(line(scene, quantity=5))
    db_session.flush()

    db_session.delete(scene.receipt)
    db_session.flush()

    remaining = db_session.scalar(
        select(func.count())
        .select_from(GoodsReceiptLine)
        .where(GoodsReceiptLine.receipt_id == scene.receipt.id)
    )
    assert remaining == 0


def test_removing_a_line_from_the_collection_deletes_it(db_session: Session, scene: Scene) -> None:
    """`delete-orphan`, so a line detached from its document does not survive.

    Editing a draft replaces its lines; a line that lingers after being removed
    would be counted at posting time and quietly inflate the stock.
    """
    item = line(scene)
    scene.receipt.lines.append(item)
    db_session.flush()

    scene.receipt.lines.remove(item)
    db_session.flush()

    assert db_session.get(GoodsReceiptLine, item.id) is None


def test_a_line_cannot_reference_a_missing_receipt(db_session: Session, scene: Scene) -> None:
    import uuid

    db_session.add(line(scene, receipt_id=uuid.uuid4()))

    with pytest.raises(IntegrityError):
        db_session.flush()


# --------------------------------------------------------------------------- #
# Version token — the same pattern as Product
# --------------------------------------------------------------------------- #


def test_version_starts_at_one_and_increments(db_session: Session, scene: Scene) -> None:
    assert scene.receipt.version == 1

    scene.receipt.status = ReceiptStatus.POSTED
    db_session.flush()

    assert scene.receipt.version == 2


def test_a_stale_version_loses(db_session: Session, scene: Scene) -> None:
    db_session.execute(
        text("UPDATE goods_receipts SET version = version + 1 WHERE id = :id"),
        {"id": scene.receipt.id},
    )

    scene.receipt.status = ReceiptStatus.POSTED

    with pytest.raises(StaleDataError):
        db_session.flush()


# --------------------------------------------------------------------------- #
# Shape
# --------------------------------------------------------------------------- #


def test_the_receipt_records_who_created_it(scene: Scene) -> None:
    # Audit needs an actor, and a document whose author is unknown cannot be
    # explained after the fact.
    assert scene.receipt.created_by == scene.user.id


def test_lines_carry_no_computed_total() -> None:
    """A stored line total is a second source of truth for `quantity × price`.

    It can only ever agree with them or be wrong, and the arithmetic is cheap.
    """
    columns = set(inspect(GoodsReceiptLine).columns.keys())

    assert "total" not in columns
    assert "amount" not in columns
