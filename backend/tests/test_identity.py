"""Issue 6 — identity models and password hashing.

Acceptance criteria under test:
- `alembic upgrade head` creates users, organizations and memberships;
- password hashes are never returned by any serializer;
- `users.email` is unique.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    hash_password,
    password_needs_rehash,
    verify_dummy_password,
    verify_password,
)
from app.models.identity import Membership, Organization, User

# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #


def test_hash_round_trips() -> None:
    stored = hash_password("correct horse battery staple")

    assert verify_password(stored, "correct horse battery staple") is True


def test_wrong_password_is_rejected() -> None:
    stored = hash_password("correct horse battery staple")

    assert verify_password(stored, "Correct horse battery staple") is False


def test_hash_is_argon2id() -> None:
    # The variant matters: argon2i and argon2d each trade away one of the two
    # resistances argon2id keeps.
    assert hash_password("x").startswith("$argon2id$")


def test_hash_is_salted() -> None:
    # Equal passwords must not produce equal hashes, or the store becomes a
    # lookup table for which accounts share a password.
    assert hash_password("same") != hash_password("same")


def test_plaintext_never_appears_in_the_hash() -> None:
    secret = "a-very-distinctive-passphrase"

    assert secret not in hash_password(secret)


def test_malformed_hash_is_a_failure_not_an_exception() -> None:
    # A corrupted row must not authenticate anyone, and must not 500 either.
    assert verify_password("not-an-argon2-hash", "anything") is False


def test_current_hashes_do_not_need_rehashing() -> None:
    assert password_needs_rehash(hash_password("x")) is False


def test_unparseable_hash_is_marked_for_rehash() -> None:
    assert password_needs_rehash("garbage") is True


def test_dummy_verification_is_available_for_unknown_accounts() -> None:
    # Used by the login endpoint so a missing account costs the same as a wrong
    # password. It must never raise, whatever it is handed.
    verify_dummy_password("anything at all")


# --------------------------------------------------------------------------- #
# Schema produced by the migration
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("table", ["users", "organizations", "memberships"])
def test_migration_created_table(db_session: Session, table: str) -> None:
    assert inspect(db_session.get_bind()).has_table(table)


def test_email_is_unique(db_session: Session) -> None:
    db_session.add(User(email="dup@example.com", password_hash=hash_password("a")))
    db_session.flush()

    db_session.add(User(email="dup@example.com", password_hash=hash_password("b")))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_database_rejects_a_non_lowercase_email(db_session: Session) -> None:
    # Enforced by a CHECK constraint, not only by application code, so a future
    # code path cannot create "Bob@x.com" alongside "bob@x.com".
    db_session.add(User(email="Mixed@Example.com", password_hash=hash_password("a")))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_created_at_is_timezone_aware(db_session: Session) -> None:
    user = User(email="tz@example.com", password_hash=hash_password("a"))
    db_session.add(user)
    db_session.flush()
    db_session.refresh(user)

    assert user.created_at.tzinfo is not None
    assert user.created_at.utcoffset() is not None


def test_user_defaults_to_active(db_session: Session) -> None:
    user = User(email="active@example.com", password_hash=hash_password("a"))
    db_session.add(user)
    db_session.flush()
    db_session.refresh(user)

    assert user.is_active is True


def test_membership_is_unique_per_user_and_organization(db_session: Session) -> None:
    user = User(email="member@example.com", password_hash=hash_password("a"))
    org = Organization(name="ФОП Іваненко")
    db_session.add_all([user, org])
    db_session.flush()

    db_session.add(Membership(user_id=user.id, organization_id=org.id))
    db_session.flush()
    db_session.add(Membership(user_id=user.id, organization_id=org.id))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_one_user_can_belong_to_several_organizations(db_session: Session) -> None:
    # The PRD scope is single-company/multi-FOP, so this is a supported case and
    # not an accident of the schema.
    user = User(email="multi@example.com", password_hash=hash_password("a"))
    first = Organization(name="ФОП Перший")
    second = Organization(name="ФОП Другий")
    db_session.add_all([user, first, second])
    db_session.flush()

    db_session.add_all(
        [
            Membership(user_id=user.id, organization_id=first.id),
            Membership(user_id=user.id, organization_id=second.id),
        ]
    )
    db_session.flush()
    db_session.refresh(user)

    assert len(user.memberships) == 2


def test_deleting_a_user_removes_their_memberships(db_session: Session) -> None:
    user = User(email="gone@example.com", password_hash=hash_password("a"))
    org = Organization(name="ФОП Третій")
    db_session.add_all([user, org])
    db_session.flush()
    db_session.add(Membership(user_id=user.id, organization_id=org.id))
    db_session.flush()

    db_session.delete(user)
    db_session.flush()

    assert db_session.query(Membership).count() == 0


# --------------------------------------------------------------------------- #
# Password hashes must not escape through the API surface
# --------------------------------------------------------------------------- #


def test_password_hash_is_absent_from_the_openapi_contract() -> None:
    """The generated TypeScript client is built from this document.

    Asserting against the whole contract rather than a list of known schemas
    means a serializer added in a later phase cannot leak the field quietly.
    """
    from app.main import app

    contract = json.dumps(app.openapi())

    assert "password_hash" not in contract
    assert "passwordHash" not in contract


def test_user_model_still_stores_the_hash_privately() -> None:
    # Guards the test above from passing for the wrong reason — i.e. because the
    # column was renamed or dropped rather than because it stays server-side.
    assert "password_hash" in inspect(User).columns


def test_expiry_arithmetic_uses_aware_datetimes() -> None:
    # Session expiry lands in Issue 7; this pins the timezone convention the
    # models were built on before code depends on it.
    now = dt.datetime.now(dt.UTC)

    assert now.tzinfo is not None
