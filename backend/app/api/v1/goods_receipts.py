"""Goods receipt endpoints: drafting, editing and posting.

Draft edits refuse to touch a posted document; posting turns a draft into stock
in one transaction.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.api.deps import CurrentOrganization, CurrentUser, SessionDep
from app.core.errors import VersionConflictError, documented
from app.core.idempotency import require_idempotency_key, run_idempotent
from app.models.goods_receipt import GoodsReceipt
from app.models.identity import Organization, User
from app.schemas.goods_receipt import (
    CounterpartyCreate,
    CounterpartyPublic,
    GoodsReceiptCreate,
    GoodsReceiptLinePublic,
    GoodsReceiptPage,
    GoodsReceiptPostRequest,
    GoodsReceiptPublic,
    GoodsReceiptSummary,
    GoodsReceiptUpdate,
)
from app.services import goods_receipt as service
from app.services import posting

router = APIRouter(prefix="/goods-receipts", tags=["goods-receipts"])
counterparties_router = APIRouter(prefix="/counterparties", tags=["counterparties"])

_SCOPED = documented(401, 403)


def _summary(session: Session, receipt: GoodsReceipt) -> GoodsReceiptSummary:
    # Names rather than bare ids: the list and detail views both show them, and
    # resolving here costs one join instead of a call per row in the browser.
    counterparty = receipt.counterparty_id
    from app.models.counterparty import CounterpartyStub
    from app.models.identity import User

    supplier = session.get(CounterpartyStub, counterparty)
    author = session.get(User, receipt.created_by)
    assert supplier is not None and author is not None  # foreign keys guarantee both

    return GoodsReceiptSummary(
        id=receipt.id,
        status=receipt.status,
        version=receipt.version,
        counterparty_id=receipt.counterparty_id,
        counterparty_name=supplier.name,
        warehouse_id=receipt.warehouse_id,
        created_by=receipt.created_by,
        created_by_email=author.email,
        created_at=receipt.created_at,
        total=service.receipt_total(receipt),
    )


def _detail(session: Session, receipt: GoodsReceipt) -> GoodsReceiptPublic:
    from app.models.catalog import Product

    lines: list[GoodsReceiptLinePublic] = []
    for item in receipt.lines:
        product = session.get(Product, item.product_id)
        assert product is not None
        lines.append(
            GoodsReceiptLinePublic(
                id=item.id,
                product_id=item.product_id,
                product_name=product.name,
                quantity=item.quantity,
                purchase_price=item.purchase_price,
                line_total=service.line_total(item),
            )
        )

    return GoodsReceiptPublic(**_summary(session, receipt).model_dump(), lines=lines)


@router.post(
    "",
    response_model=GoodsReceiptPublic,
    status_code=status.HTTP_201_CREATED,
    responses=documented(401, 403, 422),
)
def create_receipt(
    payload: GoodsReceiptCreate,
    organization: CurrentOrganization,
    user: CurrentUser,
    db: SessionDep,
) -> GoodsReceiptPublic:
    receipt = service.create_receipt(db, organization, user, payload)
    return _detail(db, receipt)


@router.get("", response_model=GoodsReceiptPage, responses=_SCOPED)
def list_receipts(
    organization: CurrentOrganization,
    db: SessionDep,
    limit: int = Query(default=service.DEFAULT_PAGE_SIZE, ge=1, le=service.MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> GoodsReceiptPage:
    items, total = service.list_receipts(db, organization, limit=limit, offset=offset)
    return GoodsReceiptPage(
        items=[_summary(db, item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{receipt_id}", response_model=GoodsReceiptPublic, responses=_SCOPED)
def read_receipt(
    receipt_id: uuid.UUID, organization: CurrentOrganization, db: SessionDep
) -> GoodsReceiptPublic:
    return _detail(db, service.get_receipt(db, organization, receipt_id))


@router.patch(
    "/{receipt_id}",
    response_model=GoodsReceiptPublic,
    responses=documented(401, 403, 409, 422),
)
def update_receipt(
    receipt_id: uuid.UUID,
    payload: GoodsReceiptUpdate,
    organization: CurrentOrganization,
    db: SessionDep,
) -> GoodsReceiptPublic:
    """Edit a draft. A posted document answers 409 under any payload."""
    receipt = service.update_receipt(db, organization, receipt_id, payload)
    return _detail(db, receipt)


@router.post(
    "/{receipt_id}/post",
    response_model=GoodsReceiptPublic,
    responses=documented(401, 403, 409, 422),
)
def post_receipt(
    receipt_id: uuid.UUID,
    payload: GoodsReceiptPostRequest,
    organization: CurrentOrganization,
    user: CurrentUser,
    db: SessionDep,
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> JSONResponse:
    """Turn a draft into stock: batch, movement, audit and status, all or nothing.

    The command runs inside `run_idempotent`, which shares this request's
    transaction. That is what makes a replay safe *and* a failure harmless: the
    reservation and the work commit together or roll back together.

    Returns a `JSONResponse` rather than a model, because a replay hands back the
    body recorded at the time — the stored response is the answer, not whatever
    the document looks like now.
    """
    try:
        outcome = run_idempotent(
            db,
            organization=organization,
            endpoint="POST /api/v1/goods-receipts/{id}/post",
            key=idempotency_key,
            payload=posting.posting_payload(receipt_id, payload.version),
            execute=lambda: _execute_post(db, organization, user, receipt_id, payload.version),
        )
        db.commit()
    except StaleDataError as exc:
        # Defence in depth. `SELECT ... FOR UPDATE` should mean a concurrent
        # poster reads `posted` and gets a clean 409 long before this fires — but
        # if it ever does, the caller deserves 409 rather than a 500 for what is
        # simply a race it lost.
        db.rollback()
        raise VersionConflictError from exc

    return JSONResponse(status_code=outcome.status_code, content=outcome.body)


def _execute_post(
    db: Session,
    organization: Organization,
    user: User,
    receipt_id: uuid.UUID,
    version: int,
) -> tuple[int, dict[str, Any]]:
    receipt = posting.post_receipt(db, organization, user, receipt_id, version)
    # `mode="json"` so the stored body is exactly what the client receives, on
    # the first call and on every replay.
    return 200, _detail(db, receipt).model_dump(mode="json")


@counterparties_router.get("", response_model=list[CounterpartyPublic], responses=_SCOPED)
def list_counterparties(
    organization: CurrentOrganization, db: SessionDep
) -> list[CounterpartyPublic]:
    return [
        CounterpartyPublic.model_validate(item)
        for item in service.list_counterparties(db, organization)
    ]


@counterparties_router.post(
    "",
    response_model=CounterpartyPublic,
    status_code=status.HTTP_201_CREATED,
    responses=documented(401, 403, 409, 422),
)
def create_counterparty(
    payload: CounterpartyCreate, organization: CurrentOrganization, db: SessionDep
) -> CounterpartyPublic:
    """Minimal supplier creation — a name and nothing else (PRD §In Scope)."""
    return CounterpartyPublic.model_validate(
        service.create_counterparty(db, organization, payload.name)
    )
