"""Warehouses.

A reference stub, not a module. The PRD scopes **one warehouse per
organization** and puts transfers between warehouses out of scope; the unique
constraint below encodes that, so the day it changes is a deliberate migration
rather than a surprise discovered in production.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.conventions import TIMESTAMPTZ, UUID_PK


class Warehouse(Base):
    """Where stock sits.

    **Holds no quantity of its own.** Balance is aggregated from movements, the
    same rule `products` is already guarded against breaking.
    """

    __tablename__ = "warehouses"
    __table_args__ = (
        # One per organization, at the database level. See the module docstring.
        UniqueConstraint("organization_id", name="uq_warehouses_organization"),
        CheckConstraint("btrim(name) <> ''", name="ck_warehouses_name_not_blank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
