"""Product catalog endpoints."""

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentOrganization, SessionDep
from app.core.errors import documented
from app.schemas.product import ProductCreate, ProductPage, ProductPublic, ProductUpdate
from app.services import catalog

router = APIRouter(prefix="/products", tags=["products"])

_SCOPED = documented(401, 403)


@router.post(
    "",
    response_model=ProductPublic,
    status_code=status.HTTP_201_CREATED,
    responses=documented(401, 403, 409, 422),
)
def create_product(
    payload: ProductCreate, organization: CurrentOrganization, db: SessionDep
) -> ProductPublic:
    product = catalog.create_product(db, organization, payload)
    return ProductPublic.model_validate(product)


@router.get("", response_model=ProductPage, responses=_SCOPED)
def list_products(
    organization: CurrentOrganization,
    db: SessionDep,
    q: str | None = Query(default=None, max_length=64, description="Matches name or barcode"),
    limit: int = Query(default=catalog.DEFAULT_PAGE_SIZE, ge=1, le=catalog.MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> ProductPage:
    items, total = catalog.list_products(db, organization, query=q, limit=limit, offset=offset)
    return ProductPage(
        items=[ProductPublic.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{product_id}", response_model=ProductPublic, responses=_SCOPED)
def read_product(
    product_id: uuid.UUID, organization: CurrentOrganization, db: SessionDep
) -> ProductPublic:
    return ProductPublic.model_validate(catalog.get_product(db, organization, product_id))


@router.patch(
    "/{product_id}",
    response_model=ProductPublic,
    responses=documented(401, 403, 409, 422),
)
def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    organization: CurrentOrganization,
    db: SessionDep,
) -> ProductPublic:
    """Partial update. `version` is required and a mismatch is 409, never a silent overwrite."""
    product = catalog.update_product(db, organization, product_id, payload)
    return ProductPublic.model_validate(product)
