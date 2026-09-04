"""Issue 19 — the idempotency mechanism.

Acceptance criteria under test:
- a replay with an identical payload returns the stored response and executes nothing;
- the same key with a different payload returns 409;
- a missing key returns 422.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from app.core.errors import DomainValidationError
from app.core.idempotency import (
    IdempotencyConflictError,
    require_idempotency_key,
    run_idempotent,
)
from app.models.idempotency import IdempotencyRecord

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from app.models.identity import Organization

ENDPOINT = "POST /api/v1/goods-receipts/{id}/post"


class Recorder:
    """A command that counts how many times it actually ran."""

    def __init__(self, body: dict[str, Any] | None = None, status: int = 200) -> None:
        self.calls = 0
        self._body = body if body is not None else {"ok": True}
        self._status = status

    def __call__(self) -> tuple[int, dict[str, Any]]:
        self.calls += 1
        return self._status, self._body


@pytest.fixture
def organization(organization_factory: Callable[[str], Organization]) -> Organization:
    return organization_factory("ФОП Ідемпотентність")


def run(
    session: Session,
    organization: Organization,
    command: Recorder,
    *,
    key: str = "key-1",
    payload: dict[str, Any] | None = None,
    endpoint: str = ENDPOINT,
):  # noqa: ANN201 - returns the outcome dataclass
    return run_idempotent(
        session,
        organization=organization,
        endpoint=endpoint,
        key=key,
        payload=payload if payload is not None else {"version": 1},
        execute=command,
    )


# --------------------------------------------------------------------------- #
# First execution and replay
# --------------------------------------------------------------------------- #


def test_the_first_call_executes(db_session: Session, organization: Organization) -> None:
    command = Recorder({"receipt": "posted"}, status=201)

    outcome = run(db_session, organization, command)

    assert command.calls == 1
    assert outcome.status_code == 201
    assert outcome.body == {"receipt": "posted"}
    assert outcome.replayed is False


def test_a_replay_returns_the_stored_response_and_executes_nothing(
    db_session: Session, organization: Organization
) -> None:
    """The whole point: a retried request must not do the work twice.

    A client that times out and retries has no way to know whether the first
    attempt landed. If the replay re-executed, that retry would create a second
    stock movement out of one delivery.
    """
    command = Recorder({"receipt": "posted"}, status=201)
    run(db_session, organization, command)

    outcome = run(db_session, organization, command)

    assert command.calls == 1
    assert outcome.status_code == 201
    assert outcome.body == {"receipt": "posted"}
    assert outcome.replayed is True


def test_the_stored_response_survives_a_different_command(
    db_session: Session, organization: Organization
) -> None:
    # The record is the source of truth for a replay, not whatever the caller
    # would compute today.
    first = Recorder({"answer": "original"})
    run(db_session, organization, first)

    second = Recorder({"answer": "different"})
    outcome = run(db_session, organization, second)

    assert second.calls == 0
    assert outcome.body == {"answer": "original"}


# --------------------------------------------------------------------------- #
# Conflicts
# --------------------------------------------------------------------------- #


def test_the_same_key_with_a_different_payload_is_409(
    db_session: Session, organization: Organization
) -> None:
    """Not a replay — a mistake, and one worth refusing loudly.

    Reusing a key for different work means the client's key generation is
    broken. Returning the first response would silently answer a question that
    was never asked.
    """
    command = Recorder()
    run(db_session, organization, command, payload={"version": 1})

    with pytest.raises(IdempotencyConflictError) as caught:
        run(db_session, organization, command, payload={"version": 2})

    assert caught.value.status_code == 409
    assert caught.value.code == "idempotency_conflict"
    assert command.calls == 1


def test_payload_key_order_does_not_change_the_fingerprint(
    db_session: Session, organization: Organization
) -> None:
    # JSON object order is not meaningful, so the fingerprint is taken over a
    # canonical form. Otherwise an equivalent retry would look like a conflict.
    command = Recorder()
    run(db_session, organization, command, payload={"a": 1, "b": 2})

    outcome = run(db_session, organization, command, payload={"b": 2, "a": 1})

    assert outcome.replayed is True
    assert command.calls == 1


# --------------------------------------------------------------------------- #
# Scope
# --------------------------------------------------------------------------- #


def test_a_different_key_executes_again(db_session: Session, organization: Organization) -> None:
    command = Recorder()
    run(db_session, organization, command, key="key-1")

    run(db_session, organization, command, key="key-2")

    assert command.calls == 2


def test_keys_are_scoped_per_organization(
    db_session: Session,
    organization: Organization,
    organization_factory: Callable[[str], Organization],
) -> None:
    # Two tenants generating the same key must not collide. Client-supplied
    # values are not globally unique and cannot be assumed to be.
    other = organization_factory("ФОП Інша")
    command = Recorder()
    run(db_session, organization, command, key="shared")

    run(db_session, other, command, key="shared")

    assert command.calls == 2


def test_keys_are_scoped_per_endpoint(db_session: Session, organization: Organization) -> None:
    command = Recorder()
    run(db_session, organization, command, endpoint="POST /a")

    run(db_session, organization, command, endpoint="POST /b")

    assert command.calls == 2


# --------------------------------------------------------------------------- #
# Failure does not burn the key
# --------------------------------------------------------------------------- #


def test_a_failed_command_leaves_the_key_reusable(
    db_session: Session, organization: Organization
) -> None:
    """A command that raised did not happen, so its key must stay available.

    Burning the key on failure would leave the client unable to retry the very
    request that failed — the one case retrying exists for.
    """

    def explode() -> tuple[int, dict[str, Any]]:
        raise RuntimeError("posting blew up")

    # Rolled back to a savepoint rather than with `session.rollback()`: a full
    # rollback would also discard the organization this test created, and the
    # retry would then fail on a foreign key for reasons that have nothing to do
    # with idempotency.
    savepoint = db_session.begin_nested()
    with pytest.raises(RuntimeError):
        run_idempotent(
            db_session,
            organization=organization,
            endpoint=ENDPOINT,
            key="retry-me",
            payload={"version": 1},
            execute=explode,
        )
    savepoint.rollback()

    command = Recorder()
    outcome = run(db_session, organization, command, key="retry-me")

    assert command.calls == 1
    assert outcome.replayed is False


def test_a_stored_record_is_written_once(db_session: Session, organization: Organization) -> None:
    command = Recorder()
    run(db_session, organization, command)
    run(db_session, organization, command)

    records = (
        db_session.query(IdempotencyRecord)
        .filter(IdempotencyRecord.organization_id == organization.id)
        .all()
    )
    assert len(records) == 1
    assert records[0].response_status == 200


# --------------------------------------------------------------------------- #
# The header
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("header", [None, "", "   "])
def test_a_missing_or_blank_key_is_422(header: str | None) -> None:
    with pytest.raises(DomainValidationError) as caught:
        require_idempotency_key(header)

    assert caught.value.status_code == 422


def test_an_over_long_key_is_422() -> None:
    # Bounded so a client cannot use the header as free storage, and so the
    # value always fits the column that has to hold it.
    with pytest.raises(DomainValidationError):
        require_idempotency_key("k" * 300)


def test_a_reasonable_key_is_accepted() -> None:
    assert require_idempotency_key("  01J8Z2-abc  ") == "01J8Z2-abc"
