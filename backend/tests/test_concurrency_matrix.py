"""Issue 26 — the concurrency and error matrix.

The cases already covered elsewhere are not repeated here:

| Case | Where |
|---|---|
| concurrent posts of the same receipt, same key | `test_posting_concurrency.py` |
| concurrent posts of the same receipt, different keys | `test_posting_concurrency.py` |
| concurrent product updates | `test_products_concurrency.py` |
| malformed payloads → 422 | `test_products.py`, `test_goods_receipts_api.py`, `test_posting.py` |
| cross-organization → 403 | every scoped suite |

What remains, and lives here:

- concurrent posts of **different** receipts for the same product → both succeed
  and the balance aggregates;
- concurrent draft edits with mismatched versions → exactly one 409;
- a stale read, then a post, then a re-query → the balance is right anyway.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

from app.core.db import SessionLocal
from app.core.errors import AppError, VersionConflictError
from app.models.goods_receipt import GoodsReceipt
from app.models.identity import Organization, User
from app.schemas.goods_receipt import GoodsReceiptLineInput, GoodsReceiptUpdate
from app.services import goods_receipt, posting, stock
from tests.support.concurrency import run_in_parallel
from tests.support.scenes import Scene, add_draft, committed_draft, purge_organization


@pytest.fixture
def scene(migrated_database: None) -> Iterator[Scene]:
    built = committed_draft(quantity=10)
    try:
        yield built
    finally:
        purge_organization(built.organization_id)


def _post(scene: Scene, receipt_id: uuid.UUID) -> str:
    with SessionLocal() as session:
        organization = session.get(Organization, scene.organization_id)
        user = session.get(User, scene.user_id)
        assert organization is not None and user is not None
        try:
            posting.post_receipt(session, organization, user, receipt_id, 1)
            session.commit()
            return "posted"
        except AppError as exc:
            session.rollback()
            return exc.code


def _balance(scene: Scene) -> int:
    with SessionLocal() as session:
        organization = session.get(Organization, scene.organization_id)
        assert organization is not None
        rows, _ = stock.list_balances(session, organization, product_id=scene.product_id)
        return rows[0].quantity_balance


# --------------------------------------------------------------------------- #
# Two sellers, one product
# --------------------------------------------------------------------------- #


def test_concurrent_posts_of_different_receipts_both_succeed_and_aggregate(
    scene: Scene,
) -> None:
    """Different documents are not in contention, and the totals add up.

    The row lock must serialise posts of the *same* receipt without serialising
    unrelated ones — otherwise correctness would have been bought with
    throughput nobody agreed to lose. Two deliveries of 10 and 25 make 35, not
    one of them.
    """
    second = add_draft(scene, quantity=25)

    outcome = run_in_parallel(lambda: _post(scene, scene.receipt_id), lambda: _post(scene, second))

    assert outcome.values == ["posted", "posted"]
    assert _balance(scene) == 35


def test_a_third_delivery_keeps_adding(scene: Scene) -> None:
    # Sequential, but it pins the same claim the balance query rests on: the
    # number is a sum of movements, so it can only grow by what arrived.
    third = add_draft(scene, quantity=5)

    assert _post(scene, scene.receipt_id) == "posted"
    assert _post(scene, third) == "posted"

    assert _balance(scene) == 15


# --------------------------------------------------------------------------- #
# Two editors, one draft
# --------------------------------------------------------------------------- #


def test_concurrent_draft_edits_with_the_same_expected_version_leave_one_winner(
    scene: Scene,
) -> None:
    """Both editors loaded version 1; only one may save it.

    This is the products case repeated on a document, because the goods receipt
    carries its own `version` and the rule has to hold there too — a lost update
    on a delivery is stock that was never counted.
    """

    def edit(quantity: int) -> str:
        with SessionLocal() as session:
            organization = session.get(Organization, scene.organization_id)
            assert organization is not None
            try:
                goods_receipt.update_receipt(
                    session,
                    organization,
                    scene.receipt_id,
                    GoodsReceiptUpdate(
                        version=1,
                        lines=[
                            GoodsReceiptLineInput(
                                product_id=scene.product_id,
                                quantity=quantity,
                                purchase_price="100.00",  # type: ignore[arg-type]
                            )
                        ],
                    ),
                )
                session.commit()
                return "saved"
            except VersionConflictError:
                session.rollback()
                return "version_conflict"

    outcome = run_in_parallel(lambda: edit(3), lambda: edit(7))

    assert sorted(outcome.values) == ["saved", "version_conflict"]

    with SessionLocal() as session:
        receipt = session.get(GoodsReceipt, scene.receipt_id)
        assert receipt is not None
        assert receipt.version == 2
        assert [item.quantity for item in receipt.lines] in ([3], [7])


# --------------------------------------------------------------------------- #
# Stale read
# --------------------------------------------------------------------------- #


def test_a_stale_balance_read_does_not_survive_a_post(scene: Scene) -> None:
    """Read projections may lag; the command side is authoritative (research §435).

    The balance read before posting is not wrong — it was true when taken. What
    matters is that re-querying after the command reflects it, because nothing
    is cached: the number is computed from the movements each time it is asked
    for.
    """
    before = _balance(scene)
    assert before == 0

    assert _post(scene, scene.receipt_id) == "posted"

    assert _balance(scene) == 10


def test_a_failed_post_leaves_the_balance_untouched(scene: Scene) -> None:
    # The other half: a refused command must not move the number either.
    assert _post(scene, scene.receipt_id) == "posted"
    assert _balance(scene) == 10

    # Second attempt on the same, now-posted document.
    assert _post(scene, scene.receipt_id) == "receipt_not_draft"

    assert _balance(scene) == 10
