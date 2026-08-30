"""Counterparties — a deliberate stub.

The PRD scopes a **name-only** supplier entity and puts the full module —
contracts, several contracts per counterparty, statistics — out of scope. A
name-only reference table is exactly the kind that accretes columns nobody
planned, so `test_reference_stubs.py` asserts the column set rather than
trusting it.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.conventions import TIMESTAMPTZ, UUID_PK


class CounterpartyStub(Base):
    """A supplier, identified by a name and nothing else."""

    __tablename__ = "counterparties_stub"
    __table_args__ = (
        # Two rows with the same name are indistinguishable, and a user picking
        # between them in a dropdown is picking at random.
        UniqueConstraint("organization_id", "name", name="uq_counterparties_organization_name"),
        CheckConstraint("btrim(name) <> ''", name="ck_counterparties_name_not_blank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
