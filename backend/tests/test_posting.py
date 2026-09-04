"""Issue 20 — posting a goods receipt.

Acceptance criteria under test:
- posting twice creates exactly one batch and one movement;
- posting an already-posted document → 409;
- posting a document with no lines → 422;
- an injected failure after batch creation leaves zero batches and zero movements.

Issue 22 adds the concurrency and replay matrix on top of this file.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import func, select

from app.models.audit import AuditLog
from app.models.goods_receipt import GoodsReceipt, ReceiptStatus
from app.models.inventory import InventoryBatch, MovementType, StockMovement

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from tests.conftest import LoggedIn

RECEIPTS = "/api/v1/goods-receipts"
PRODUCTS = "/api/v1/products"
COUNTERPARTIES = "/api/v1/counterparties"


def make_product(client: TestClient, name: str, price: str = "100.00") -> dict[str, Any]:
    response = client.post(PRODUCTS, json={"name": name, "unit": "шт", "purchase_price": price})
    assert response.status_code == 201, response.text
    return response.json()


def some_supplier(client: TestClient) -> dict[str, Any]:
    existing = client.get(COUNTERPARTIES).json()
    if existing:
        return existing[0]
    response = client.post(COUNTERPARTIES, json={"name": "ТОВ Постачальник"})
    assert response.status_code == 201, response.text
    return response.json()


def make_draft(client: TestClient, lines: list[dict[str, Any]]) -> dict[str, Any]:
    response = client.post(
        RECEIPTS, json={"counterparty_id": some_supplier(client)["id"], "lines": lines}
    )
    assert response.status_code == 201, response.text
    return response.json()


def line(product_id: str, quantity: int = 10, price: str = "100.00") -> dict[str, Any]:
    return {"product_id": product_id, "quantity": quantity, "purchase_price": price}


def post(
    client: TestClient, receipt: dict[str, Any], *, key: str = "key-1", version: int | None = None
):  # noqa: ANN201 - httpx Response
    return client.post(
        f"{RECEIPTS}/{receipt['id']}/post",
        json={"version": version if version is not None else receipt["version"]},
        headers={"Idempotency-Key": key},
    )


def count(session: Session, model: type[Any], organization_id: uuid.UUID) -> int:
    """Scoped, deliberately.

    A global count assumes the whole database belongs to this test. It does not:
    `test_posting_concurrency.py` commits rows on its own organizations, and a
    test that depends on the rest of the database being empty is testing the
    suite rather than the code.
    """
    return (
        session.scalar(
            select(func.count()).select_from(model).where(model.organization_id == organization_id)
        )
        or 0
    )


# --------------------------------------------------------------------------- #
# The happy path
# --------------------------------------------------------------------------- #


def test_posting_flips_the_status_and_bumps_the_version(logged_in: LoggedIn) -> None:
    product = make_product(logged_in.client, "Кава")
    receipt = make_draft(logged_in.client, [line(product["id"], 10)])

    response = post(logged_in.client, receipt)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "posted"
    assert response.json()["version"] == receipt["version"] + 1


def test_posting_creates_one_batch_and_one_movement_per_line(
    logged_in: LoggedIn, db_session: Session
) -> None:
    """One batch per line, not one per document.

    The plan says "copy price, sum qty", which only works for a single-product
    delivery. A batch is a quantity of **one** product at **one** price — summing
    across lines would merge different goods into one batch and lose the price
    each arrived at, which is exactly what FIFO cost later depends on.
    """
    coffee = make_product(logged_in.client, "Кава")
    tea = make_product(logged_in.client, "Чай")
    receipt = make_draft(
        logged_in.client,
        [line(coffee["id"], 10, "100.00"), line(tea["id"], 5, "50.00")],
    )

    post(logged_in.client, receipt)

    org = logged_in.organization.id
    batches = db_session.scalars(
        select(InventoryBatch).where(InventoryBatch.organization_id == org)
    ).all()
    movements = db_session.scalars(
        select(StockMovement).where(StockMovement.organization_id == org)
    ).all()

    assert len(batches) == 2
    assert len(movements) == 2
    assert {(b.quantity, str(b.purchase_price)) for b in batches} == {
        (10, "100.00"),
        (5, "50.00"),
    }


def test_a_new_batch_is_entirely_unconsumed(logged_in: LoggedIn, db_session: Session) -> None:
    product = make_product(logged_in.client, "Кава")
    receipt = make_draft(logged_in.client, [line(product["id"], 7)])

    post(logged_in.client, receipt)

    org = logged_in.organization.id
    batch = db_session.scalars(
        select(InventoryBatch).where(InventoryBatch.organization_id == org)
    ).one()
    assert batch.quantity == 7
    assert batch.remaining_quantity == 7
    assert batch.receipt_id == uuid.UUID(receipt["id"])


def test_the_movement_points_back_at_its_batch_and_document(
    logged_in: LoggedIn, db_session: Session
) -> None:
    product = make_product(logged_in.client, "Кава")
    receipt = make_draft(logged_in.client, [line(product["id"], 4)])

    post(logged_in.client, receipt)

    org = logged_in.organization.id
    batch = db_session.scalars(
        select(InventoryBatch).where(InventoryBatch.organization_id == org)
    ).one()
    movement = db_session.scalars(
        select(StockMovement).where(StockMovement.organization_id == org)
    ).one()

    assert movement.quantity_delta == 4
    assert movement.movement_type is MovementType.RECEIPT
    assert movement.batch_id == batch.id
    assert movement.document_id == uuid.UUID(receipt["id"])
    assert movement.warehouse_id == batch.warehouse_id


def test_posting_writes_an_audit_record(logged_in: LoggedIn, db_session: Session) -> None:
    product = make_product(logged_in.client, "Кава")
    receipt = make_draft(logged_in.client, [line(product["id"])])

    post(logged_in.client, receipt)

    entry = db_session.scalars(
        select(AuditLog).where(
            AuditLog.action == "posted_receipt",
            AuditLog.organization_id == logged_in.organization.id,
        )
    ).one()
    assert entry.entity_type == "goods_receipt"
    assert entry.entity_id == uuid.UUID(receipt["id"])
    assert entry.actor_id == logged_in.user.id
    assert entry.old_value == {"status": "draft", "version": receipt["version"]}
    assert entry.new_value == {"status": "posted", "version": receipt["version"] + 1}


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #


def test_posting_an_empty_document_is_422(logged_in: LoggedIn, db_session: Session) -> None:
    receipt = make_draft(logged_in.client, [])

    response = post(logged_in.client, receipt)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "empty_document"
    org = logged_in.organization.id
    assert count(db_session, InventoryBatch, org) == 0
    assert count(db_session, StockMovement, org) == 0


def test_posting_twice_is_409(logged_in: LoggedIn) -> None:
    product = make_product(logged_in.client, "Кава")
    receipt = make_draft(logged_in.client, [line(product["id"])])
    post(logged_in.client, receipt, key="first")

    # A *different* key, so this is a genuine second attempt rather than a replay.
    response = post(logged_in.client, receipt, key="second", version=receipt["version"] + 1)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "receipt_not_draft"


def test_posting_twice_still_leaves_one_batch_and_one_movement(
    logged_in: LoggedIn, db_session: Session
) -> None:
    """The acceptance criterion, stated in stock rather than in status codes."""
    product = make_product(logged_in.client, "Кава")
    receipt = make_draft(logged_in.client, [line(product["id"])])

    post(logged_in.client, receipt, key="first")
    post(logged_in.client, receipt, key="second", version=receipt["version"] + 1)

    org = logged_in.organization.id
    assert count(db_session, InventoryBatch, org) == 1
    assert count(db_session, StockMovement, org) == 1


def test_a_stale_version_is_409(logged_in: LoggedIn, db_session: Session) -> None:
    product = make_product(logged_in.client, "Кава")
    receipt = make_draft(logged_in.client, [line(product["id"])])
    logged_in.client.patch(
        f"{RECEIPTS}/{receipt['id']}", json={"version": 1, "lines": [line(product["id"], 3)]}
    )

    response = post(logged_in.client, receipt, version=1)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "version_conflict"
    org = logged_in.organization.id
    assert count(db_session, StockMovement, org) == 0


def test_the_idempotency_key_is_required(logged_in: LoggedIn) -> None:
    product = make_product(logged_in.client, "Кава")
    receipt = make_draft(logged_in.client, [line(product["id"])])

    response = logged_in.client.post(
        f"{RECEIPTS}/{receipt['id']}/post", json={"version": receipt["version"]}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "idempotency_key_required"


def test_posting_a_foreign_receipt_is_403(logged_in: LoggedIn) -> None:
    response = logged_in.client.post(
        f"{RECEIPTS}/{uuid.uuid4()}/post",
        json={"version": 1},
        headers={"Idempotency-Key": "whatever"},
    )

    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# Replay
# --------------------------------------------------------------------------- #


def test_a_replay_returns_the_same_body_and_creates_nothing_more(
    logged_in: LoggedIn, db_session: Session
) -> None:
    product = make_product(logged_in.client, "Кава")
    receipt = make_draft(logged_in.client, [line(product["id"])])

    first = post(logged_in.client, receipt, key="same-key")
    second = post(logged_in.client, receipt, key="same-key")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    org = logged_in.organization.id
    assert count(db_session, InventoryBatch, org) == 1
    assert count(db_session, StockMovement, org) == 1


def test_the_same_key_with_a_different_version_is_409(logged_in: LoggedIn) -> None:
    product = make_product(logged_in.client, "Кава")
    receipt = make_draft(logged_in.client, [line(product["id"])])
    post(logged_in.client, receipt, key="reused")

    response = post(logged_in.client, receipt, key="reused", version=99)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_conflict"


# --------------------------------------------------------------------------- #
# Atomicity
# --------------------------------------------------------------------------- #


def test_an_injected_failure_leaves_no_batches_and_no_movements(
    logged_in: LoggedIn, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The criterion that matters most: all of it, or none of it.

    The failure is injected *after* the batches exist in the session, so the
    rollback has something real to undo. A partial post — stock recorded with no
    movement to explain it, or a movement pointing at a batch that was never
    committed — is the corruption this whole transaction exists to prevent.
    """
    from app.services import posting

    product = make_product(logged_in.client, "Кава")
    receipt = make_draft(logged_in.client, [line(product["id"])])

    def explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected failure after batch creation")

    monkeypatch.setattr(posting, "_record_movement", explode)

    with pytest.raises(RuntimeError):
        post(logged_in.client, receipt)

    db_session.rollback()

    org = logged_in.organization.id
    assert count(db_session, InventoryBatch, org) == 0
    assert count(db_session, StockMovement, org) == 0
    assert count(db_session, AuditLog, org) == 0


def test_a_failed_post_leaves_the_document_a_draft(
    logged_in: LoggedIn, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import posting

    product = make_product(logged_in.client, "Кава")
    receipt = make_draft(logged_in.client, [line(product["id"])])
    receipt_id = uuid.UUID(receipt["id"])

    def explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected failure")

    monkeypatch.setattr(posting, "_record_movement", explode)

    with pytest.raises(RuntimeError):
        post(logged_in.client, receipt)

    db_session.rollback()

    row = db_session.get(GoodsReceipt, receipt_id)
    assert row is not None
    assert row.status is ReceiptStatus.DRAFT
    assert row.version == receipt["version"]
