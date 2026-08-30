"""At-most-once execution for commands that must not be repeated.

The PRD makes `Idempotency-Key` mandatory on the posting command. A client whose
request times out cannot know whether it landed; without this, its retry would
turn one delivery into two stock movements.

**The whole mechanism is one unique constraint plus one transaction.** The
reservation row is inserted inside the same transaction as the command, so:

- if the command fails, the rollback takes the reservation with it and the key
  stays usable — which matters, because the request that failed is exactly the
  one a client will retry;
- if two requests arrive at once, PostgreSQL makes the second wait on the unique
  index. When the first commits, the second's insert raises a unique violation
  and it reads the stored response instead of executing. When the first rolls
  back, the second's insert succeeds and it does the work.

No locking of our own, no in-flight state machine, no polling.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Header
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, DomainValidationError
from app.models.idempotency import IdempotencyRecord
from app.models.identity import Organization

# Long enough for a UUID or a ULID with room to spare, short enough that the
# header cannot be used as free storage — and it must fit the column.
MAX_KEY_LENGTH = 255

# The one constraint whose violation means "this key is already taken".
UNIQUE_CONSTRAINT = "uq_idempotency_records_scope"


class IdempotencyConflictError(AppError):
    """The same key, used for different work.

    409 rather than a replay: reusing a key for a different payload means the
    client's key generation is broken, and answering with the first response
    would silently answer a question that was never asked.
    """

    status_code = 409
    code = "idempotency_conflict"
    message = "This Idempotency-Key was already used for a different request."


class MissingIdempotencyKeyError(DomainValidationError):
    code = "idempotency_key_required"
    message = "The Idempotency-Key header is required for this operation."


def require_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    """FastAPI dependency: the header, validated.

    Mandatory rather than optional-with-a-default. A generated fallback would
    make every request unique, which is the same as having no idempotency at all
    while looking like it is switched on.
    """
    value = (idempotency_key or "").strip()
    if not value:
        raise MissingIdempotencyKeyError
    if len(value) > MAX_KEY_LENGTH:
        raise DomainValidationError(f"Idempotency-Key must be at most {MAX_KEY_LENGTH} characters.")
    return value


def fingerprint(payload: dict[str, Any]) -> str:
    """A stable digest of the request.

    `sort_keys` matters: JSON object order carries no meaning, so an otherwise
    identical retry that serialised its fields in another order must not look
    like a conflict.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IdempotentOutcome:
    status_code: int
    body: dict[str, Any]
    replayed: bool


def run_idempotent(
    session: Session,
    *,
    organization: Organization,
    endpoint: str,
    key: str,
    payload: dict[str, Any],
    execute: Callable[[], tuple[int, dict[str, Any]]],
) -> IdempotentOutcome:
    """Run `execute` at most once for this (organization, endpoint, key).

    `execute` returns the status code and the JSON-serialisable body that a
    replay will hand back verbatim — the record is the source of truth for a
    replay, not whatever the caller would compute today.

    The caller owns the transaction and commits; this function does not, so the
    command and its reservation stand or fall together.
    """
    digest = fingerprint(payload)

    record = IdempotencyRecord(
        organization_id=organization.id,
        endpoint=endpoint,
        key=key,
        request_fingerprint=digest,
        # Placeholders until the command has run. They are never observable:
        # nothing outside this transaction can see the row until it commits, and
        # by then they have been replaced.
        response_status=0,
        response_body={},
    )

    try:
        # A savepoint, so losing this race does not poison the caller's
        # transaction — it still has a replay to return.
        with session.begin_nested():
            session.add(record)
    except IntegrityError as exc:
        # Only *our* unique constraint means "somebody already holds this key".
        # A foreign-key violation or anything else is a different problem, and
        # disguising it as an idempotency replay would hide a real bug behind a
        # 200. Let it surface.
        if UNIQUE_CONSTRAINT not in str(exc.orig):
            raise
        return _replay(
            session, organization=organization, endpoint=endpoint, key=key, digest=digest
        )

    status_code, body = execute()
    record.response_status = status_code
    record.response_body = body
    return IdempotentOutcome(status_code=status_code, body=body, replayed=False)


def _replay(
    session: Session,
    *,
    organization: Organization,
    endpoint: str,
    key: str,
    digest: str,
) -> IdempotentOutcome:
    existing = session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.organization_id == organization.id,
            IdempotencyRecord.endpoint == endpoint,
            IdempotencyRecord.key == key,
        )
    )
    if existing is None:
        # The unique constraint fired, so a row exists — unless the transaction
        # that created it has since rolled back, in which case the key is free
        # again and the caller should simply try once more.
        raise IdempotencyConflictError(
            "This Idempotency-Key is being used by another request. Retry shortly."
        )

    if existing.request_fingerprint != digest:
        raise IdempotencyConflictError

    return IdempotentOutcome(
        status_code=existing.response_status, body=existing.response_body, replayed=True
    )
