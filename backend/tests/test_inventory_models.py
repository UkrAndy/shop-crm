"""Issue 18 — batch, movement and audit models.

Acceptance criteria under test:
- movements carry `quantity_delta`, `movement_type`, `batch_id`, `document_id`;
- no product row holds a mutable `quantity` column;
- an index supports `(organization_id, warehouse_id, product_id)` aggregation.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, NamedTuple

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models.audit import AuditLog
from app.models.catalog import Product
from app.models.counterparty import CounterpartyStub
from app.models.goods_receipt import GoodsReceipt
from app.models.inventory import InventoryBatch, MovementType, StockMovement, Warehouse
from app.services import inventory

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from app.models.identity import Organization, User


class Scene(NamedTuple):
    organization: Organization
    user: User
    warehouse: Warehouse
    product: Product
    receipt: GoodsReceipt


@pytest.fixture
def scene(
    db_session: Session,
    user_factory: Callable[..., User],
    organization_factory: Callable[[str], Organization],
) -> Scene:
    organization = organization_factory("ФОП Рухи")
    user = user_factory("movements@example.com", organization)
    warehouse = inventory.default_warehouse(db_session, organization)

    supplier = CounterpartyStub(organization_id=organization.id, name="ТОВ Рухи")
    product = Product(
        organization_id=organization.id,
        name="Кава",
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

    return Scene(
        organization=organization,
        user=user,
        warehouse=warehouse,
        product=product,
        receipt=receipt,
    )


def make_batch(scene: Scene, **overrides: object) -> InventoryBatch:
    values: dict[str, object] = {
        "organization_id": scene.organization.id,
        "warehouse_id": scene.warehouse.id,
        "product_id": scene.product.id,
        "receipt_id": scene.receipt.id,
        "purchase_price": Decimal("100.00"),
        "quantity": 10,
        "remaining_quantity": 10,
    }
    values.update(overrides)
    return InventoryBatch(**values)


def make_movement(scene: Scene, batch: InventoryBatch, **overrides: object) -> StockMovement:
    values: dict[str, object] = {
        "organization_id": scene.organization.id,
        "warehouse_id": scene.warehouse.id,
        "product_id": scene.product.id,
        "batch_id": batch.id,
        "quantity_delta": 10,
        "movement_type": MovementType.RECEIPT,
        "document_id": scene.receipt.id,
    }
    values.update(overrides)
    return StockMovement(**values)


# --------------------------------------------------------------------------- #
# Batches
# --------------------------------------------------------------------------- #


def test_a_batch_records_the_price_it_arrived_at(db_session: Session, scene: Scene) -> None:
    # FIFO cost (a later phase) depends on each batch keeping its own price
    # rather than reading today's catalog price.
    batch = make_batch(scene, purchase_price=Decimal("87.65"))
    db_session.add(batch)
    db_session.flush()
    db_session.expire(batch)

    assert batch.purchase_price == Decimal("87.65")
    assert isinstance(batch.purchase_price, Decimal)


@pytest.mark.parametrize("quantity", [0, -1])
def test_a_batch_must_have_a_positive_quantity(
    db_session: Session, scene: Scene, quantity: int
) -> None:
    db_session.add(make_batch(scene, quantity=quantity, remaining_quantity=0))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_remaining_quantity_may_not_exceed_the_batch(db_session: Session, scene: Scene) -> None:
    # More left than ever arrived is not a state to detect later; it is one the
    # database should refuse to hold.
    db_session.add(make_batch(scene, quantity=10, remaining_quantity=11))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_remaining_quantity_may_not_go_negative(db_session: Session, scene: Scene) -> None:
    db_session.add(make_batch(scene, quantity=10, remaining_quantity=-1))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_a_fully_consumed_batch_is_valid(db_session: Session, scene: Scene) -> None:
    db_session.add(make_batch(scene, quantity=10, remaining_quantity=0))

    db_session.flush()


# --------------------------------------------------------------------------- #
# Movements
# --------------------------------------------------------------------------- #


def test_a_movement_carries_everything_a_balance_needs(db_session: Session, scene: Scene) -> None:
    batch = make_batch(scene)
    db_session.add(batch)
    db_session.flush()

    movement = make_movement(scene, batch)
    db_session.add(movement)
    db_session.flush()
    db_session.expire(movement)

    assert movement.quantity_delta == 10
    assert movement.movement_type is MovementType.RECEIPT
    assert movement.batch_id == batch.id
    assert movement.document_id == scene.receipt.id


def test_a_zero_movement_is_rejected(db_session: Session, scene: Scene) -> None:
    # Nothing moved, so there is nothing to record. A zero row only pollutes the
    # aggregation it would contribute nothing to.
    batch = make_batch(scene)
    db_session.add(batch)
    db_session.flush()

    db_session.add(make_movement(scene, batch, quantity_delta=0))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_a_negative_movement_is_allowed(db_session: Session, scene: Scene) -> None:
    # Sales are out of scope for this slice, but the *sign* is the mechanism by
    # which balance is aggregated. Forbidding it now would mean rebuilding the
    # column later.
    batch = make_batch(scene)
    db_session.add(batch)
    db_session.flush()

    db_session.add(make_movement(scene, batch, quantity_delta=-3, document_id=scene.receipt.id))

    db_session.flush()


def test_the_database_rejects_an_unknown_movement_type(db_session: Session, scene: Scene) -> None:
    batch = make_batch(scene)
    db_session.add(batch)
    db_session.flush()
    movement = make_movement(scene, batch)
    db_session.add(movement)
    db_session.flush()

    with pytest.raises((IntegrityError, DBAPIError)):
        db_session.execute(
            text("UPDATE stock_movements SET movement_type = 'teleport' WHERE id = :id"),
            {"id": movement.id},
        )


def test_a_movement_cannot_be_modified(db_session: Session, scene: Scene) -> None:
    """Append-only, enforced by the database rather than by convention.

    Research §386 asks for immutability "by application policy and database
    constraints where practical". A trigger is practical: it holds against a
    migration, a fix-up script and a future service alike, none of which will
    have read our policy.
    """
    batch = make_batch(scene)
    db_session.add(batch)
    db_session.flush()
    movement = make_movement(scene, batch)
    db_session.add(movement)
    db_session.flush()

    with pytest.raises(DBAPIError):
        db_session.execute(
            text("UPDATE stock_movements SET quantity_delta = 999 WHERE id = :id"),
            {"id": movement.id},
        )


def test_no_application_code_deletes_or_updates_a_movement() -> None:
    """The other half of append-only: there is no code path that tries.

    The trigger stops the database from accepting it; this stops a developer
    from writing something that would fail at runtime in production.
    """
    from pathlib import Path

    app_root = Path(__file__).resolve().parent.parent / "app"
    sources = "\n".join(path.read_text(encoding="utf-8") for path in app_root.rglob("*.py"))

    assert "delete(StockMovement)" not in sources
    assert "session.delete(movement" not in sources


def test_movements_are_indexed_for_balance_aggregation(db_session: Session) -> None:
    """The acceptance criterion, checked against the real schema.

    Stock balance is `SUM(quantity_delta)` filtered by organization, warehouse
    and product. Without this index that becomes a sequential scan over every
    movement the tenant has ever made.
    """
    indexes = inspect(db_session.get_bind()).get_indexes("stock_movements")
    columns = [tuple(index["column_names"]) for index in indexes]

    assert ("organization_id", "warehouse_id", "product_id") in columns


def test_no_product_row_holds_a_quantity() -> None:
    # The PRD's central claim, asserted again now that a real alternative
    # exists: balance comes from movements, so a counter on the product would be
    # a second source of truth that can drift.
    assert "quantity" not in set(inspect(Product).columns.keys())


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #


def test_an_audit_row_records_actor_action_and_entity(db_session: Session, scene: Scene) -> None:
    entry = AuditLog(
        organization_id=scene.organization.id,
        actor_id=scene.user.id,
        action="posted_receipt",
        entity_type="goods_receipt",
        entity_id=scene.receipt.id,
        old_value={"status": "draft"},
        new_value={"status": "posted"},
    )
    db_session.add(entry)
    db_session.flush()
    db_session.expire(entry)

    assert entry.actor_id == scene.user.id
    assert entry.old_value == {"status": "draft"}
    assert entry.new_value == {"status": "posted"}
    assert entry.created_at.tzinfo is not None


def test_audit_values_may_be_absent(db_session: Session, scene: Scene) -> None:
    # A creation has no "before", and a read has neither. Requiring both would
    # push callers into writing `{}` and losing the distinction.
    db_session.add(
        AuditLog(
            organization_id=scene.organization.id,
            actor_id=scene.user.id,
            action="created_receipt",
            entity_type="goods_receipt",
            entity_id=scene.receipt.id,
        )
    )

    db_session.flush()


def test_an_audit_row_cannot_be_modified(db_session: Session, scene: Scene) -> None:
    entry = AuditLog(
        organization_id=scene.organization.id,
        actor_id=scene.user.id,
        action="posted_receipt",
        entity_type="goods_receipt",
        entity_id=scene.receipt.id,
    )
    db_session.add(entry)
    db_session.flush()

    with pytest.raises(DBAPIError):
        db_session.execute(
            text("UPDATE audit_log SET action = 'nothing happened' WHERE id = :id"),
            {"id": entry.id},
        )


def test_audit_survives_the_entity_it_describes(db_session: Session, scene: Scene) -> None:
    """`entity_id` is a plain column, not a foreign key.

    An audit trail that disappears with the thing it recorded is not an audit
    trail. The reference is deliberately loose so history outlives its subject.
    """
    entry = AuditLog(
        organization_id=scene.organization.id,
        actor_id=scene.user.id,
        action="deleted_something",
        entity_type="goods_receipt",
        entity_id=uuid.uuid4(),
    )
    db_session.add(entry)

    db_session.flush()
