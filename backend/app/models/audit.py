"""Business audit.

Research §778: audit is durable domain data, not technical logging. It records
who did what to which entity, when, and what changed — and it outlives the thing
it describes.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.conventions import TIMESTAMPTZ, UUID_PK


class AuditLog(Base):
    """One recorded business action.

    **Append-only**, like `stock_movements`: a trigger refuses `UPDATE` and
    `DELETE`. An audit trail that can be edited is not evidence of anything.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint("btrim(action) <> ''", name="ck_audit_log_action_not_blank"),
        CheckConstraint("btrim(entity_type) <> ''", name="ck_audit_log_entity_type_not_blank"),
        # The two questions asked of an audit trail: "what happened to this
        # document?" and "what happened here recently?"
        Index("ix_audit_log_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_audit_log_recent", "organization_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    # RESTRICT: an action whose actor has been erased is unattributable, which
    # defeats the purpose of recording it.
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))

    # Deliberately **not** a foreign key. History must outlive its subject, and a
    # movement, a receipt and a product all end up referenced from this column.
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID_PK)

    # Nullable on both sides: a creation has no "before", and some actions have
    # neither. Requiring both would push callers into writing `{}` and losing the
    # distinction between "nothing" and "empty".
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMPTZ, server_default=func.now())
