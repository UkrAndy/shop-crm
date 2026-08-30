"""Product catalog use cases.

Every query is scoped by `organization_id` in its `WHERE` clause rather than
filtered afterwards, so a scope mistake is a query that returns nothing, not one
that returns someone else's data.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.core.errors import AppError, OrganizationForbiddenError, VersionConflictError
from app.models.catalog import Product
from app.models.identity import Organization
from app.schemas.product import ProductCreate, ProductUpdate

# Bounds the damage a single request can do. Without a ceiling, `limit` turns
# one call into a full-table dump.
MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50


class BarcodeTakenError(AppError):
    """Another product in this organization already carries that barcode.

    409 rather than 422: the payload is well-formed, and it is the *current
    state* of the catalog that rejects it — exactly the distinction research
    §555 draws between the two codes.
    """

    status_code = 409
    code = "barcode_taken"
    message = "Another product in this organization already uses this barcode."


def _scoped(organization: Organization):  # noqa: ANN202 - SQLAlchemy Select generic
    return select(Product).where(Product.organization_id == organization.id)


def get_product(session: Session, organization: Organization, product_id: uuid.UUID) -> Product:
    """Load one product from the caller's organization.

    A product belonging to somebody else and a product that does not exist give
    the same answer, because the query never looks outside the scope and so the
    server never learns which case it is. Nothing can leak that it does not know.
    """
    product = session.scalar(_scoped(organization).where(Product.id == product_id))
    if product is None:
        raise OrganizationForbiddenError
    return product


def list_products(
    session: Session,
    organization: Organization,
    *,
    query: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> tuple[list[Product], int]:
    """Return one page and the total matching the same filter."""
    statement = _scoped(organization)

    if query:
        pattern = f"%{query.strip()}%"
        # Case-insensitive on both fields: a barcode is typed from a label and a
        # name from memory, and neither should need exact case.
        statement = statement.where(Product.name.ilike(pattern) | Product.barcode.ilike(pattern))

    total = session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    items = list(session.scalars(statement.order_by(Product.name).limit(limit).offset(offset)))
    return items, total or 0


def create_product(session: Session, organization: Organization, payload: ProductCreate) -> Product:
    product = Product(
        organization_id=organization.id,
        name=payload.name,
        unit=payload.unit,
        purchase_price=payload.purchase_price,
        barcode=payload.barcode,
    )
    session.add(product)
    _commit(session)
    return product


def update_product(
    session: Session,
    organization: Organization,
    product_id: uuid.UUID,
    payload: ProductUpdate,
) -> Product:
    """Apply a partial update, guarded by the version the client last saw.

    Two different races are covered, and both need to be:

    1. **A stale client.** It read version 3, someone saved version 4, and it is
       now sending 3. Checked here, *before* anything is mutated, so a rejected
       update leaves the row untouched.
    2. **A concurrent writer.** Nobody was ahead when we read, but somebody
       committed between our read and our flush. `version_id_col` catches that
       in the `UPDATE … WHERE version = ?` itself and raises `StaleDataError`.

    Checking only the first would leave a window; relying only on the second
    would mutate the object before discovering the client was stale.
    """
    product = get_product(session, organization, product_id)

    if product.version != payload.version:
        raise VersionConflictError

    fields = payload.model_dump(exclude={"version"}, exclude_unset=True)
    for field, value in fields.items():
        setattr(product, field, value)

    _commit(session)
    return product


def _commit(session: Session) -> None:
    """Commit, translating the two failures this module can provoke.

    Both roll the transaction back first: leaving a session in a failed state
    turns one bad request into every later one in the same connection failing.
    """
    try:
        session.commit()
    except StaleDataError as exc:
        session.rollback()
        raise VersionConflictError from exc
    except IntegrityError as exc:
        session.rollback()
        if "uq_products_organization_barcode" in str(exc.orig):
            raise BarcodeTakenError from exc
        # Anything else is a constraint we did not anticipate; letting it surface
        # as a 500 is honest, and silently mapping it to 409 would not be.
        raise
