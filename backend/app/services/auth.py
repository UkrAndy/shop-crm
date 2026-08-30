"""Login, session lifecycle and organization scope resolution.

Design: `docs/design-docs/design-auth.md`.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import (
    InvalidCredentialsError,
    OrganizationForbiddenError,
    UnauthenticatedError,
)
from app.core.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    password_needs_rehash,
    verify_dummy_password,
    verify_password,
)
from app.models.identity import Membership, Organization, User, UserSession


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def authenticate(session: Session, email: str, password: str) -> User:
    """Return the user, or raise `InvalidCredentialsError`.

    The same exception covers an unknown email, a wrong password and a
    deactivated account, and the unknown-email branch still pays for one hash
    verification so the three are indistinguishable by response time too.
    """
    user = session.scalar(select(User).where(User.email == email.strip().lower()))

    if user is None:
        verify_dummy_password(password)
        raise InvalidCredentialsError

    if not verify_password(user.password_hash, password):
        raise InvalidCredentialsError

    if not user.is_active:
        raise InvalidCredentialsError

    # Migrate the stored hash as argon2-cffi's defaults rise over time.
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    return user


def start_session(
    session: Session,
    user: User,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, UserSession]:
    """Create a session row and return `(raw token, row)`.

    The raw token is returned exactly once, to be written into the cookie; only
    its digest is persisted.

    A user with exactly one membership gets it selected immediately — there is
    nothing to choose, so a mandatory extra round-trip would be ceremony. With
    two or more the server does **not** guess: picking wrong would post
    documents into the wrong legal entity.
    """
    settings = get_settings()
    now = _now()
    raw_token = generate_session_token()

    memberships = list(session.scalars(select(Membership).where(Membership.user_id == user.id)))
    active_organization_id = memberships[0].organization_id if len(memberships) == 1 else None

    user_session = UserSession(
        user_id=user.id,
        token_hash=hash_session_token(raw_token),
        active_organization_id=active_organization_id,
        created_at=now,
        last_used_at=now,
        expires_at=now + dt.timedelta(seconds=settings.session_absolute_seconds),
        user_agent=user_agent[:512] if user_agent else None,
        ip_address=ip_address[:45] if ip_address else None,
    )
    session.add(user_session)
    session.commit()
    return raw_token, user_session


def resolve_session(session: Session, raw_token: str | None) -> UserSession:
    """Look up a live session, sliding its idle window.

    Raises `UnauthenticatedError` when the cookie is missing, unknown, past its
    absolute expiry, idle for too long, or belongs to a deactivated user.
    """
    if not raw_token:
        raise UnauthenticatedError

    settings = get_settings()
    user_session = session.scalar(
        select(UserSession).where(UserSession.token_hash == hash_session_token(raw_token))
    )
    if user_session is None:
        raise UnauthenticatedError

    now = _now()
    if user_session.expires_at <= now:
        raise UnauthenticatedError
    if user_session.last_used_at + dt.timedelta(seconds=settings.session_idle_seconds) <= now:
        raise UnauthenticatedError
    if not user_session.user.is_active:
        # Deactivation is authoritative on every request, so it does not require
        # hunting down the user's live sessions.
        raise UnauthenticatedError

    # Only the idle window moves; the absolute expiry never does.
    user_session.last_used_at = now
    session.commit()
    return user_session


def end_session(session: Session, raw_token: str | None) -> None:
    """Revoke a session. Silent when there is nothing to revoke, so logout is idempotent."""
    if not raw_token:
        return

    user_session = session.scalar(
        select(UserSession).where(UserSession.token_hash == hash_session_token(raw_token))
    )
    if user_session is not None:
        session.delete(user_session)
        session.commit()


def list_organizations(session: Session, user: User) -> list[Organization]:
    """Organizations the user is a member of, and only those."""
    return list(
        session.scalars(
            select(Organization)
            .join(Membership, Membership.organization_id == Organization.id)
            .where(Membership.user_id == user.id)
            .order_by(Organization.name)
        )
    )


def _membership_or_forbidden(
    session: Session, user_id: uuid.UUID, organization_id: uuid.UUID
) -> None:
    membership = session.scalar(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
    )
    if membership is None:
        # 403 for a foreign organization and for one that does not exist alike:
        # whether the row exists is not the caller's business.
        raise OrganizationForbiddenError


def set_active_organization(
    session: Session, user_session: UserSession, organization_id: uuid.UUID
) -> Organization:
    """Point the session at an organization the user actually belongs to."""
    _membership_or_forbidden(session, user_session.user_id, organization_id)

    user_session.active_organization_id = organization_id
    session.commit()

    organization = session.get(Organization, organization_id)
    assert organization is not None  # membership implies the row exists
    return organization


def get_active_organization(session: Session, user_session: UserSession) -> Organization | None:
    """Resolve the active organization, re-checking membership every time.

    The session row caches an id, never a permission: revoking a membership must
    take effect on the next request rather than at session expiry.
    """
    if user_session.active_organization_id is None:
        return None

    membership = session.scalar(
        select(Membership).where(
            Membership.user_id == user_session.user_id,
            Membership.organization_id == user_session.active_organization_id,
        )
    )
    if membership is None:
        return None

    return session.get(Organization, user_session.active_organization_id)
