"""Issue 22 — posting under contention.

The sequential cases live in `test_posting.py`. These are the ones that need
genuinely parallel transactions, so they commit for real on independent
connections and clean up after themselves.

Acceptance criterion: **each test fails when its guard is removed.** Verified
deliberately — see the Issue 22 notes in the backlog.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any, NamedTuple

import pytest
from sqlalchemy import delete, func, select, text

from app.core.db import SessionLocal
from app.core.errors import AppError
from app.core.idempotency import run_idempotent
from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.catalog import Product
from app.models.counterparty import CounterpartyStub
from app.models.goods_receipt import GoodsReceipt, GoodsReceiptLine, ReceiptStatus
from app.models.idempotency import IdempotencyRecord
from app.models.identity import Membership, Organization, User
from app.models.inventory import InventoryBatch, StockMovement, Warehouse
from app.services import inventory, posting

BARRIER_TIMEOUT_SECONDS = 10
ENDPOINT = "POST /api/v1/goods-receipts/{id}/post"
APPEND_ONLY_TABLES = ("stock_movements", "audit_log")


class Scene(NamedTuple):
    organization_id: uuid.UUID
    user_id: uuid.UUID
    receipt_id: uuid.UUID


@pytest.fixture
def committed_receipt(migrated_database: None) -> Iterator[Scene]:
    """A real, committed draft with one line, on a throwaway organization.

    Committed rather than rolled back: threads on separate connections cannot
    see each other's uncommitted work, so a transactional fixture would make the
    race untestable.
    """
    with SessionLocal() as session:
        organization = Organization(name=f"ФОП Гонка {uuid.uuid4()}")
        session.add(organization)
        session.flush()

        user = User(email=f"poster-{uuid.uuid4()}@example.com", password_hash=hash_password("x"))
        session.add(user)
        session.flush()
        session.add(Membership(user_id=user.id, organization_id=organization.id))

        warehouse = inventory.default_warehouse(session, organization)
        supplier = CounterpartyStub(organization_id=organization.id, name="ТОВ Гонка")
        product = Product(
            organization_id=organization.id,
            name="Кава",
            unit="шт",
            purchase_price=Decimal("100.00"),
        )
        session.add_all([supplier, product])
        session.flush()

        receipt = GoodsReceipt(
            organization_id=organization.id,
            warehouse_id=warehouse.id,
            counterparty_id=supplier.id,
            created_by=user.id,
            lines=[
                GoodsReceiptLine(
                    product_id=product.id,
                    position=0,
                    quantity=10,
                    purchase_price=Decimal("100.00"),
                )
            ],
        )
        session.add(receipt)
        session.commit()
        scene = Scene(organization_id=organization.id, user_id=user.id, receipt_id=receipt.id)

    try:
        yield scene
    finally:
        _purge(scene.organization_id)


def _purge(organization_id: uuid.UUID) -> None:
    """Remove everything this test wrote, child rows first.

    Two things make this less trivial than a cascade:

    - Movements and audit rows are **append-only**: the trigger refuses `DELETE`,
      which is the point of it. Disabling it for the duration is a deliberate,
      table-owner operation confined to the test suite; production has no code
      path that reaches it.
    - Deleting the organization alone is not enough. `ON DELETE RESTRICT` fires
      even when the referencing row is itself being removed by the same cascade,
      so a receipt still pointing at its warehouse blocks the warehouse's
      removal. The order below is the dependency order, made explicit.
    """
    with SessionLocal() as session:
        for table in APPEND_ONLY_TABLES:
            session.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER {table}_append_only"))
        session.commit()

    try:
        with SessionLocal() as session:
            receipts = select(GoodsReceipt.id).where(
                GoodsReceipt.organization_id == organization_id
            )
            actors = set(
                session.scalars(
                    select(GoodsReceipt.created_by).where(
                        GoodsReceipt.organization_id == organization_id
                    )
                )
            )

            session.execute(
                delete(StockMovement).where(StockMovement.organization_id == organization_id)
            )
            session.execute(delete(AuditLog).where(AuditLog.organization_id == organization_id))
            session.execute(
                delete(InventoryBatch).where(InventoryBatch.organization_id == organization_id)
            )
            session.execute(
                delete(IdempotencyRecord).where(
                    IdempotencyRecord.organization_id == organization_id
                )
            )
            session.execute(
                delete(GoodsReceiptLine).where(GoodsReceiptLine.receipt_id.in_(receipts))
            )
            session.execute(
                delete(GoodsReceipt).where(GoodsReceipt.organization_id == organization_id)
            )
            session.execute(delete(Product).where(Product.organization_id == organization_id))
            session.execute(
                delete(CounterpartyStub).where(CounterpartyStub.organization_id == organization_id)
            )
            session.execute(delete(Warehouse).where(Warehouse.organization_id == organization_id))
            session.execute(delete(Organization).where(Organization.id == organization_id))
            # Users outlive the organization only because nothing references
            # them any more once the documents are gone.
            for actor in actors:
                session.execute(delete(User).where(User.id == actor))
            session.commit()
    finally:
        with SessionLocal() as session:
            for table in APPEND_ONLY_TABLES:
                session.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER {table}_append_only"))
            session.commit()


def _run_in_parallel(*targets: Any) -> None:
    threads = [threading.Thread(target=target) for target in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    for thread in threads:
        assert not thread.is_alive(), "a worker did not finish — likely a deadlock"


def _counts(organization_id: uuid.UUID) -> tuple[int, int, int]:
    with SessionLocal() as session:
        batches = session.scalar(
            select(func.count())
            .select_from(InventoryBatch)
            .where(InventoryBatch.organization_id == organization_id)
        )
        movements = session.scalar(
            select(func.count())
            .select_from(StockMovement)
            .where(StockMovement.organization_id == organization_id)
        )
        audits = session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.organization_id == organization_id)
        )
    return batches or 0, movements or 0, audits or 0


def _post(scene: Scene, key: str, version: int = 1) -> tuple[str, dict[str, Any] | None]:
    """One full posting request, in its own transaction — what the endpoint does."""
    with SessionLocal() as session:
        organization = session.get(Organization, scene.organization_id)
        user = session.get(User, scene.user_id)
        assert organization is not None and user is not None

        def execute() -> tuple[int, dict[str, Any]]:
            receipt = posting.post_receipt(session, organization, user, scene.receipt_id, version)
            return 200, {"id": str(receipt.id), "status": receipt.status.value}

        try:
            outcome = run_idempotent(
                session,
                organization=organization,
                endpoint=ENDPOINT,
                key=key,
                payload=posting.posting_payload(scene.receipt_id, version),
                execute=execute,
            )
            session.commit()
            return ("replayed" if outcome.replayed else "posted", outcome.body)
        except AppError as exc:
            session.rollback()
            return (exc.code, None)


# --------------------------------------------------------------------------- #
# Concurrent posts
# --------------------------------------------------------------------------- #


def test_two_concurrent_posts_with_different_keys_leave_one_movement(
    committed_receipt: Scene,
) -> None:
    """Exactly one wins, and the stock says so.

    The barrier is what makes this a race: neither thread starts posting until
    both are ready. Without the row lock both would read `draft`, both would
    write a batch and a movement, and one delivery would become two.
    """
    barrier = threading.Barrier(2, timeout=BARRIER_TIMEOUT_SECONDS)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt(key: str) -> None:
        barrier.wait()
        result, _ = _post(committed_receipt, key)
        with lock:
            outcomes.append(result)

    _run_in_parallel(lambda: attempt("key-a"), lambda: attempt("key-b"))

    assert sorted(outcomes) == ["posted", "receipt_not_draft"]
    assert _counts(committed_receipt.organization_id) == (1, 1, 1)


def test_two_concurrent_posts_with_the_same_key_execute_once(
    committed_receipt: Scene,
) -> None:
    """The idempotency path under real contention.

    One transaction inserts the reservation; the other waits on the unique index
    and, once the winner commits, replays its stored response. Both callers get
    an answer, and one delivery becomes one movement.
    """
    barrier = threading.Barrier(2, timeout=BARRIER_TIMEOUT_SECONDS)
    outcomes: list[str] = []
    bodies: list[dict[str, Any] | None] = []
    lock = threading.Lock()

    def attempt() -> None:
        barrier.wait()
        result, body = _post(committed_receipt, "shared-key")
        with lock:
            outcomes.append(result)
            bodies.append(body)

    _run_in_parallel(attempt, attempt)

    assert sorted(outcomes) == ["posted", "replayed"]
    # The replay hands back the winner's body, not a second computation of it.
    assert bodies[0] == bodies[1]
    assert _counts(committed_receipt.organization_id) == (1, 1, 1)


def test_a_different_key_on_a_posted_document_is_refused(committed_receipt: Scene) -> None:
    """The counterpart to the race above, run sequentially.

    A fresh key is not a replay, so idempotency has nothing to say; what refuses
    is the document's own state.
    """
    assert _post(committed_receipt, "first")[0] == "posted"

    result, _ = _post(committed_receipt, "second", version=2)

    assert result == "receipt_not_draft"
    assert _counts(committed_receipt.organization_id) == (1, 1, 1)


def test_the_document_ends_posted_exactly_once(committed_receipt: Scene) -> None:
    barrier = threading.Barrier(2, timeout=BARRIER_TIMEOUT_SECONDS)

    def attempt(key: str) -> None:
        barrier.wait()
        _post(committed_receipt, key)

    _run_in_parallel(lambda: attempt("x"), lambda: attempt("y"))

    with SessionLocal() as session:
        receipt = session.get(GoodsReceipt, committed_receipt.receipt_id)
        assert receipt is not None
        assert receipt.status is ReceiptStatus.POSTED
        # One increment, not two: the loser wrote nothing.
        assert receipt.version == 2
