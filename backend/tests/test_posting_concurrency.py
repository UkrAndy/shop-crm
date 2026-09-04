"""Issue 22 — posting under contention.

The sequential cases live in `test_posting.py`. These need genuinely parallel
transactions, so they use the committed scenes and the barrier helper from
`tests/support/`.

Acceptance criterion: **each test fails when its guard is removed.** Verified
deliberately — see the Issue 22 notes in the backlog.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.core.errors import AppError
from app.core.idempotency import run_idempotent
from app.models.audit import AuditLog
from app.models.goods_receipt import GoodsReceipt, ReceiptStatus
from app.models.identity import Organization, User
from app.models.inventory import InventoryBatch, StockMovement
from app.services import posting
from tests.support.concurrency import run_in_parallel
from tests.support.scenes import Scene, committed_draft, purge_organization

ENDPOINT = "POST /api/v1/goods-receipts/{id}/post"


@pytest.fixture
def scene(migrated_database: None) -> Iterator[Scene]:
    built = committed_draft()
    try:
        yield built
    finally:
        purge_organization(built.organization_id)


def counts(organization_id: uuid.UUID) -> tuple[int, int, int]:
    """Batches, movements and audit rows — scoped, deliberately.

    A global count would depend on what the rest of the suite happened to commit.
    """
    with SessionLocal() as session:
        return (
            session.scalar(
                select(func.count())
                .select_from(InventoryBatch)
                .where(InventoryBatch.organization_id == organization_id)
            )
            or 0,
            session.scalar(
                select(func.count())
                .select_from(StockMovement)
                .where(StockMovement.organization_id == organization_id)
            )
            or 0,
            session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.organization_id == organization_id)
            )
            or 0,
        )


def post(
    scene: Scene, key: str, version: int = 1, receipt_id: uuid.UUID | None = None
) -> tuple[str, dict[str, Any] | None]:
    """One full posting request, in its own transaction — what the endpoint does."""
    target = receipt_id or scene.receipt_id

    with SessionLocal() as session:
        organization = session.get(Organization, scene.organization_id)
        user = session.get(User, scene.user_id)
        assert organization is not None and user is not None

        def execute() -> tuple[int, dict[str, Any]]:
            receipt = posting.post_receipt(session, organization, user, target, version)
            return 200, {"id": str(receipt.id), "status": receipt.status.value}

        try:
            outcome = run_idempotent(
                session,
                organization=organization,
                endpoint=ENDPOINT,
                key=key,
                payload=posting.posting_payload(target, version),
                execute=execute,
            )
            session.commit()
            return ("replayed" if outcome.replayed else "posted", outcome.body)
        except AppError as exc:
            session.rollback()
            return (exc.code, None)


def test_two_concurrent_posts_with_different_keys_leave_one_movement(scene: Scene) -> None:
    """Exactly one wins, and the stock says so.

    Without the row lock both would read `draft`, both would write a batch and a
    movement, and one delivery would become two.
    """
    outcome = run_in_parallel(lambda: post(scene, "key-a")[0], lambda: post(scene, "key-b")[0])

    assert sorted(outcome.values) == ["posted", "receipt_not_draft"]
    assert counts(scene.organization_id) == (1, 1, 1)


def test_two_concurrent_posts_with_the_same_key_execute_once(scene: Scene) -> None:
    """The idempotency path under real contention.

    One transaction inserts the reservation; the other waits on the unique index
    and, once the winner commits, replays its stored response. Both callers get
    an answer, and one delivery becomes one movement.
    """
    outcome = run_in_parallel(lambda: post(scene, "shared-key"), lambda: post(scene, "shared-key"))

    labels = sorted(value[0] for value in outcome.values)
    bodies = [value[1] for value in outcome.values]

    assert labels == ["posted", "replayed"]
    # The replay hands back the winner's body, not a second computation of it.
    assert bodies[0] == bodies[1]
    assert counts(scene.organization_id) == (1, 1, 1)


def test_a_different_key_on_a_posted_document_is_refused(scene: Scene) -> None:
    """A fresh key is not a replay, so idempotency has nothing to say.

    What refuses is the document's own state.
    """
    assert post(scene, "first")[0] == "posted"

    assert post(scene, "second", version=2)[0] == "receipt_not_draft"
    assert counts(scene.organization_id) == (1, 1, 1)


def test_the_document_ends_posted_exactly_once(scene: Scene) -> None:
    run_in_parallel(lambda: post(scene, "x"), lambda: post(scene, "y"))

    with SessionLocal() as session:
        receipt = session.get(GoodsReceipt, scene.receipt_id)
        assert receipt is not None
        assert receipt.status is ReceiptStatus.POSTED
        # One increment, not two: the loser wrote nothing.
        assert receipt.version == 2
