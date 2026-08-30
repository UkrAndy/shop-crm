"""Goods receipt draft use cases.

Editing is only ever possible while the document is `draft`. Everything that can
reject a request is checked **before** anything is mutated, so a rejected
`PATCH` provably leaves the document exactly as it was — a half-applied delivery
would post as real stock.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm.exc import StaleDataError

from app.core.errors import AppError, OrganizationForbiddenError, VersionConflictError
from app.models.catalog import Product
from app.models.counterparty import CounterpartyStub
from app.models.goods_receipt import GoodsReceipt, GoodsReceiptLine, ReceiptStatus
from app.models.identity import Organization, User
from app.schemas.goods_receipt import (
    GoodsReceiptCreate,
    GoodsReceiptLineInput,
    GoodsReceiptUpdate,
)
from app.services import inventory

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50


class ReceiptNotDraftError(AppError):
    """The document has been posted, so it is immutable.

    409, not 403: the caller has every right to it, and the payload is fine —
    it is the document's current state that refuses. Research §555 draws exactly
    this line between 409 and 422.
    """

    status_code = 409
    code = "receipt_not_draft"
    message = "This document has been posted and can no longer be edited."


class UnknownProductError(AppError):
    """A line names a product that is not in the caller's organization.

    422 with its own code rather than a bare validation error, so the client can
    point at the offending picker. A foreign product and a nonexistent one give
    the same answer because the lookup is scoped and never learns which it was.
    """

    status_code = 422
    code = "unknown_product"
    message = "One of the lines references a product that does not exist here."


class UnknownCounterpartyError(AppError):
    status_code = 422
    code = "unknown_counterparty"
    message = "That supplier does not exist in this organization."


class CounterpartyNameTakenError(AppError):
    status_code = 409
    code = "counterparty_name_taken"
    message = "A supplier with this name already exists in this organization."


def _scoped(organization: Organization):  # noqa: ANN202 - SQLAlchemy Select generic
    return (
        select(GoodsReceipt)
        .where(GoodsReceipt.organization_id == organization.id)
        .options(selectinload(GoodsReceipt.lines))
    )


def get_receipt(
    session: Session, organization: Organization, receipt_id: uuid.UUID
) -> GoodsReceipt:
    receipt = session.scalar(_scoped(organization).where(GoodsReceipt.id == receipt_id))
    if receipt is None:
        raise OrganizationForbiddenError
    return receipt


def list_receipts(
    session: Session,
    organization: Organization,
    *,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> tuple[list[GoodsReceipt], int]:
    """Newest first: a receipt list is a work queue, and the newest is the one
    somebody is about to act on."""
    statement = _scoped(organization)
    total = session.scalar(
        select(func.count()).select_from(
            select(GoodsReceipt.id)
            .where(GoodsReceipt.organization_id == organization.id)
            .subquery()
        )
    )
    items = list(
        session.scalars(
            statement.order_by(GoodsReceipt.created_at.desc(), GoodsReceipt.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return items, total or 0


def _resolve_counterparty(
    session: Session, organization: Organization, counterparty_id: uuid.UUID
) -> CounterpartyStub:
    counterparty = session.scalar(
        select(CounterpartyStub).where(
            CounterpartyStub.organization_id == organization.id,
            CounterpartyStub.id == counterparty_id,
        )
    )
    if counterparty is None:
        raise UnknownCounterpartyError
    return counterparty


def _resolve_products(
    session: Session, organization: Organization, lines: list[GoodsReceiptLineInput]
) -> None:
    """Verify every line's product belongs to the caller's organization.

    One query for the whole payload rather than one per line, and it runs before
    any mutation so a bad line in the middle cannot leave the document partly
    rewritten. This is the cross-tenant guard the schema does not express — see
    the Issue 15 note on the composite-foreign-key alternative.
    """
    if not lines:
        return

    wanted = {item.product_id for item in lines}
    found = set(
        session.scalars(
            select(Product.id).where(
                Product.organization_id == organization.id, Product.id.in_(wanted)
            )
        )
    )
    if wanted - found:
        raise UnknownProductError


def create_receipt(
    session: Session, organization: Organization, actor: User, payload: GoodsReceiptCreate
) -> GoodsReceipt:
    counterparty = _resolve_counterparty(session, organization, payload.counterparty_id)
    _resolve_products(session, organization, payload.lines)

    # Resolved server-side: an organization has exactly one warehouse, so letting
    # the client name it would only create a way to get it wrong.
    warehouse = inventory.default_warehouse(session, organization)

    receipt = GoodsReceipt(
        organization_id=organization.id,
        warehouse_id=warehouse.id,
        counterparty_id=counterparty.id,
        created_by=actor.id,
        lines=_new_lines(payload.lines),
    )
    session.add(receipt)
    _commit(session)
    return receipt


def update_receipt(
    session: Session,
    organization: Organization,
    receipt_id: uuid.UUID,
    payload: GoodsReceiptUpdate,
) -> GoodsReceipt:
    """Edit a draft.

    The order of the checks is the point. Status, then version, then every
    referenced entity — all before a single attribute is touched. A rejection
    therefore cannot have half-applied anything, which is what makes the
    "previous lines intact" guarantee true rather than merely likely.
    """
    receipt = get_receipt(session, organization, receipt_id)

    if receipt.status is not ReceiptStatus.DRAFT:
        raise ReceiptNotDraftError

    if receipt.version != payload.version:
        raise VersionConflictError

    counterparty = (
        _resolve_counterparty(session, organization, payload.counterparty_id)
        if payload.counterparty_id is not None
        else None
    )
    if payload.lines is not None:
        _resolve_products(session, organization, payload.lines)

    # Validation is complete; from here nothing can fail on our account.
    if counterparty is not None:
        receipt.counterparty_id = counterparty.id

    if payload.lines is not None:
        # Wholesale replacement. `delete-orphan` removes what is dropped, so no
        # line can survive its document's edit and be counted at posting time.
        receipt.lines = _new_lines(payload.lines)

        # `version_id_col` only increments when the *parent row* is updated, and
        # replacing a collection does not touch it. Without this, two users could
        # rewrite the same draft's lines concurrently and both would be told they
        # won — a lost update on the document's actual contents, which is exactly
        # what the version token exists to prevent. Flagging the row dirty forces
        # the UPDATE that carries the version check.
        flag_modified(receipt, "status")

    _commit(session)
    return receipt


def _new_line(item: GoodsReceiptLineInput, position: int) -> GoodsReceiptLine:
    return GoodsReceiptLine(
        product_id=item.product_id,
        position=position,
        quantity=item.quantity,
        purchase_price=item.purchase_price,
    )


def _new_lines(items: list[GoodsReceiptLineInput]) -> list[GoodsReceiptLine]:
    """Number the lines in the order the client sent them.

    The payload order is the user's order — it is what they typed, and the
    document must read back the same way.
    """
    return [_new_line(item, position) for position, item in enumerate(items)]


def line_total(item: GoodsReceiptLine) -> Decimal:
    return item.purchase_price * item.quantity


def receipt_total(receipt: GoodsReceipt) -> Decimal:
    """Summed on the server, where the values are `Decimal`.

    JavaScript has no decimal type; a total computed in the browser is a total
    that can be off by a kopiyka, and this one is shown next to money.
    """
    return sum((line_total(item) for item in receipt.lines), start=Decimal("0.00"))


# --------------------------------------------------------------------------- #
# Counterparties — the minimum the receipt UI needs to be usable
# --------------------------------------------------------------------------- #


def list_counterparties(session: Session, organization: Organization) -> list[CounterpartyStub]:
    return list(
        session.scalars(
            select(CounterpartyStub)
            .where(CounterpartyStub.organization_id == organization.id)
            .order_by(CounterpartyStub.name)
        )
    )


def create_counterparty(
    session: Session, organization: Organization, name: str
) -> CounterpartyStub:
    counterparty = CounterpartyStub(organization_id=organization.id, name=name)
    session.add(counterparty)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if "uq_counterparties_organization_name" in str(exc.orig):
            raise CounterpartyNameTakenError from exc
        raise
    return counterparty


def _commit(session: Session) -> None:
    try:
        session.commit()
    except StaleDataError as exc:
        session.rollback()
        raise VersionConflictError from exc
