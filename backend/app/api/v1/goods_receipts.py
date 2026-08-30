"""Goods receipt draft endpoints.

Posting lives in Issue 20; everything here refuses to touch a document that has
already been posted.
"""

import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentOrganization, CurrentUser, SessionDep
from app.core.errors import documented
from app.models.goods_receipt import GoodsReceipt
from app.schemas.goods_receipt import (
    CounterpartyCreate,
    CounterpartyPublic,
    GoodsReceiptCreate,
    GoodsReceiptLinePublic,
    GoodsReceiptPage,
    GoodsReceiptPublic,
    GoodsReceiptSummary,
    GoodsReceiptUpdate,
)
from app.services import goods_receipt as service

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
