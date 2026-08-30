"""Idempotency records.

One row per (organization, endpoint, key). The unique constraint is not a
nicety — it is the mechanism: two concurrent requests carrying the same key both
attempt the insert, PostgreSQL makes the second wait on the index, and whichever
loses reads the winner's stored response instead of executing.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.conventions import TIMESTAMPTZ, UUID_PK


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        # Scoped per organization because client-supplied keys are not globally
        # unique, and per endpoint because the same key reaching two different
        # commands is two different pieces of work.
        UniqueConstraint("organization_id", "endpoint", "key", name="uq_idempotency_records_scope"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )

    key: Mapped[str] = mapped_column(String(255))
    endpoint: Mapped[str] = mapped_column(String(255))

    # SHA-256 over a canonical rendering of the request. The same key with a
    # different payload is a client bug, not a replay, and this is how the two
    # are told apart.
    request_fingerprint: Mapped[str] = mapped_column(String(64))

    response_status: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB)

    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
