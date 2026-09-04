"""Posting a goods receipt.

The single most correctness-sensitive operation in the slice. Everything below
happens in **one** transaction — the caller's — and nothing in this module
commits. Either the document becomes posted with its batches, movements and
audit record, or none of it happened.

Order matters and is deliberate:

1. lock the receipt row, so a concurrent poster waits rather than racing;
2. verify state and version *before* anything is written;
3. write batches, then movements, then the status change, then the audit record.

Steps 1 and 2 mean a rejected post has not touched a row. Step 3's ordering
matters only for readability — they all live or die together.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, OrganizationForbiddenError, VersionConflictError
from app.models.audit import AuditLog
from app.models.goods_receipt import GoodsReceipt, GoodsReceiptLine, ReceiptStatus
from app.models.identity import Organization, User
from app.models.inventory import InventoryBatch, MovementType, StockMovement
from app.services.goods_receipt import ReceiptNotDraftError

AUDIT_ACTION = "posted_receipt"
AUDIT_ENTITY = "goods_receipt"


class EmptyDocumentError(AppError):
    """A delivery of nothing is not a delivery.

    422 rather than 409: the document's state is fine, its *content* is not —
    which is the line research §555 draws between the two.
    """

    status_code = 422
    code = "empty_document"
    message = "A document with no lines cannot be posted."


def lock_receipt(
    session: Session, organization: Organization, receipt_id: uuid.UUID
) -> GoodsReceipt:
    """Load the receipt with `SELECT ... FOR UPDATE`.

    The row lock is what makes two simultaneous posts sequential: the second
    waits here, and by the time it proceeds the first has already flipped the
    status, so it reads `posted` and refuses. Without the lock both would read
    `draft` and both would post.

    `version_id_col` would still catch it at flush time, but only after the
    second transaction had done all its work — the lock is cheaper and the error
    is clearer.
    """
    receipt = session.scalar(
        select(GoodsReceipt)
        .where(
            GoodsReceipt.organization_id == organization.id,
            GoodsReceipt.id == receipt_id,
        )
        .with_for_update()
    )
    if receipt is None:
        raise OrganizationForbiddenError

    # Loaded separately: `SELECT ... FOR UPDATE` cannot be combined with an outer
    # join, so the lines come after the lock rather than with it.
    session.refresh(receipt, ["lines"])
    return receipt


def post_receipt(
    session: Session,
    organization: Organization,
    actor: User,
    receipt_id: uuid.UUID,
    expected_version: int,
) -> GoodsReceipt:
    """Turn a draft into stock. Does not commit — the caller owns the transaction."""
    receipt = lock_receipt(session, organization, receipt_id)

    # Every refusal happens before the first write.
    if receipt.status is not ReceiptStatus.DRAFT:
        raise ReceiptNotDraftError
    if receipt.version != expected_version:
        raise VersionConflictError
    if not receipt.lines:
        raise EmptyDocumentError

    previous_version = receipt.version

    for item in receipt.lines:
        batch = _create_batch(session, receipt, item)
        _record_movement(session, receipt, item, batch)

    receipt.status = ReceiptStatus.POSTED

    # `version_id_col` increments on flush; the audit record has to state the
    # version the document will carry once this transaction commits.
    session.add(
        AuditLog(
            organization_id=organization.id,
            actor_id=actor.id,
            action=AUDIT_ACTION,
            entity_type=AUDIT_ENTITY,
            entity_id=receipt.id,
            old_value={"status": ReceiptStatus.DRAFT.value, "version": previous_version},
            new_value={"status": ReceiptStatus.POSTED.value, "version": previous_version + 1},
        )
    )

    session.flush()
    return receipt


def _create_batch(
    session: Session, receipt: GoodsReceipt, item: GoodsReceiptLine
) -> InventoryBatch:
    """One batch per line.

    The plan says "copy price, sum qty", which holds only for a single-product
    delivery. A batch is a quantity of **one** product at **one** price; summing
    across lines would merge different goods and lose the price each arrived at,
    which is precisely what FIFO cost later depends on.

    Two lines naming the same product at the same price still become two
    batches. They arrived as two entries on the document, and keeping them
    separate preserves the trace back to it.
    """
    batch = InventoryBatch(
        organization_id=receipt.organization_id,
        warehouse_id=receipt.warehouse_id,
        product_id=item.product_id,
        receipt_id=receipt.id,
        purchase_price=item.purchase_price,
        quantity=item.quantity,
        # Nothing has been consumed from a batch that has just arrived.
        remaining_quantity=item.quantity,
    )
    session.add(batch)
    # The movement needs the batch's id, and the id is assigned on flush.
    session.flush()
    return batch


def _record_movement(
    session: Session, receipt: GoodsReceipt, item: GoodsReceiptLine, batch: InventoryBatch
) -> StockMovement:
    """The immutable fact that makes the stock balance true.

    Positive delta: goods came in. Balance is `SUM(quantity_delta)` over the
    scope, so this row *is* the stock — there is no counter to update.
    """
    movement = StockMovement(
        organization_id=receipt.organization_id,
        warehouse_id=receipt.warehouse_id,
        product_id=item.product_id,
        batch_id=batch.id,
        quantity_delta=item.quantity,
        movement_type=MovementType.RECEIPT,
        document_id=receipt.id,
    )
    session.add(movement)
    return movement


def posting_payload(receipt_id: uuid.UUID, expected_version: int) -> dict[str, Any]:
    """What the idempotency fingerprint is taken over.

    The document and the version the client believed it was posting. Reusing a
    key for a different document, or for a different version of the same one, is
    a different request and must not replay this one's answer.
    """
    return {"receipt_id": str(receipt_id), "version": expected_version}
