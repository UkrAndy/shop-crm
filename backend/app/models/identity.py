"""Identity, sessions and organization scope.

Design: `docs/design-docs/design-auth.md`.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

# Primary keys are UUIDs rather than sequential integers. In a multi-tenant
# system an integer id in a URL leaks row counts and invites enumeration across
# organizations; scope checks stop access but not inference. uuid4 has poor
# index locality — uuid7 is the upgrade path once the Python floor reaches 3.14,
# and it is a drop-in change because nothing depends on the value's shape.
_UUID_PK = Uuid(as_uuid=True)

# RFC 5321 caps an address at 320 octets.
_EMAIL_MAX_LENGTH = 320


class User(Base):
    """An authenticated person.

    `password_hash` must never appear in an API response; no Pydantic schema
    exposes it, and `tests/test_identity.py` asserts that.
    """

    __tablename__ = "users"
    __table_args__ = (
        # The application lowercases before writing; the database refuses
        # anything else, so a future code path cannot create "Bob@x.com"
        # alongside "bob@x.com".
        CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
    )

    id: Mapped[uuid.UUID] = mapped_column(_UUID_PK, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(_EMAIL_MAX_LENGTH), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Organization(Base):
    """A legal entity (ФОП) that owns documents, stock and catalog data.

    Every scoped query filters on `organization_id`; this is the root of that scope.
    """

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(_UUID_PK, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class Membership(Base):
    """Grants a user access to an organization.

    A separate entity rather than a column on `users`: the PRD scope is
    single-company/multi-FOP, so one person legitimately belongs to several
    organizations. No role column — the PRD puts RBAC out of scope, and an
    unused column invites code to depend on a shape nobody designed.
    """

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_memberships_user_org"),
    )

    id: Mapped[uuid.UUID] = mapped_column(_UUID_PK, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(back_populates="memberships")


class UserSession(Base):
    """A logged-in session.

    Named `UserSession` rather than `Session` so it cannot be confused with
    `sqlalchemy.orm.Session` at a call site; the table keeps the plain name.

    The token is stored as a SHA-256 digest. Argon2 would be wrong here: the
    token is 256 bits of entropy, so there is nothing to brute-force, and this
    hash is computed on **every** authenticated request.
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(_UUID_PK, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Server-side, so a client cannot assert its own scope by editing a request
    # body. Nulled rather than cascaded away if the organization disappears.
    active_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Absolute expiry. Never extended — only `last_used_at` slides.
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))

    # Session/device audit data (research §621). Recorded, not yet surfaced.
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    user: Mapped[User] = relationship()
