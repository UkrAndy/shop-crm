"""Product catalog.

Design note: `Product` is the first aggregate carrying a `version` token, and
goods receipts (Issue 15) repeat the pattern, so the mechanism is chosen here
for all of them.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.conventions import MONEY, TIMESTAMPTZ, UUID_PK


class Product(Base):
    """A catalog item, scoped to one organization.

    **There is deliberately no `quantity` column.** Stock balance is aggregated
    from immutable movements (PRD §In Scope); a mutable counter here is the
    shortcut this architecture exists to forbid, and `test_catalog.py` asserts
    its absence so it cannot reappear under deadline.
    """

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("purchase_price >= 0", name="ck_products_price_non_negative"),
        # Rejects "" and "   " alike. A product with a blank name is unusable in
        # a picker, and trimming in the service layer only fixes the paths that
        # remember to call it.
        CheckConstraint("btrim(name) <> ''", name="ck_products_name_not_blank"),
        # Partial, so any number of products may carry no barcode while the ones
        # that do stay unique *within their organization*: two independent ФОПs
        # selling the same manufactured product both hold its EAN legitimately.
        Index(
            "uq_products_organization_barcode",
            "organization_id",
            "barcode",
            unique=True,
            postgresql_where=text("barcode IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )

    name: Mapped[str] = mapped_column(String(255))
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str] = mapped_column(String(32))
    purchase_price: Mapped[Decimal] = mapped_column(MONEY)

    # Optimistic concurrency. `version_id_col` below makes SQLAlchemy emit
    # `UPDATE ... WHERE id = ? AND version = ?` and raise `StaleDataError` when
    # that matches no row, so a lost update is impossible rather than unlikely.
    # SQLAlchemy owns the counter; the server default only covers a hypothetical
    # insert that bypasses the ORM.
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())

    __mapper_args__ = {"version_id_col": version}
