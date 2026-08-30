"""Issue 13 — optimistic locking under genuine parallelism.

Every other test in this file's neighbourhood runs inside one transaction that
is rolled back. That is the right default, but it cannot express a race: two
statements in one transaction never contend. These tests therefore commit for
real, on independent connections, and clean up after themselves.

Acceptance criterion: **the test must fail if optimistic locking is removed.**
Verified deliberately — see the Issue 13 notes in the backlog.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import NamedTuple

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm.exc import StaleDataError

from app.core.db import SessionLocal
from app.core.errors import VersionConflictError
from app.models.catalog import Product
from app.models.identity import Organization
from app.schemas.product import ProductUpdate
from app.services import catalog

# Generous: it only has to outlast a row lock held for a single UPDATE. If it is
# ever hit, the test has found a deadlock, which is a result worth failing on.
BARRIER_TIMEOUT_SECONDS = 10


class Fixture(NamedTuple):
    organization_id: uuid.UUID
    product_id: uuid.UUID


@pytest.fixture
def committed_product(migrated_database: None) -> Iterator[Fixture]:
    """A product that really exists, on its own organization, deleted afterwards.

    Committed rather than rolled back: threads on separate connections cannot
    see each other's uncommitted work, so a transactional fixture would make the
    race untestable. Its own organization keeps the blast radius to one cascade.
    """
    with SessionLocal() as session:
        organization = Organization(name=f"ФОП Конкуренція {uuid.uuid4()}")
        session.add(organization)
        session.flush()
        product = Product(
            organization_id=organization.id,
            name="Спірний товар",
            unit="шт",
            purchase_price=Decimal("10.00"),
        )
        session.add(product)
        session.commit()
        fixture = Fixture(organization_id=organization.id, product_id=product.id)

    try:
        yield fixture
    finally:
        with SessionLocal() as session:
            # Products cascade from the organization.
            session.execute(delete(Organization).where(Organization.id == fixture.organization_id))
            session.commit()


def _run_in_parallel(*targets: object) -> None:
    threads = [threading.Thread(target=target) for target in targets]  # type: ignore[arg-type]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    for thread in threads:
        assert not thread.is_alive(), "a worker did not finish — likely a deadlock"


def test_two_concurrent_updates_leave_exactly_one_winner(committed_product: Fixture) -> None:
    """Both readers hold version 1; exactly one commit may succeed.

    The barrier is what makes this a race rather than two sequential updates:
    neither thread writes until both have read. Without it the first could
    finish before the second even loads, and the test would pass while proving
    nothing.
    """
    barrier = threading.Barrier(2, timeout=BARRIER_TIMEOUT_SECONDS)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt(new_name: str) -> None:
        with SessionLocal() as session:
            product = session.get(Product, committed_product.product_id)
            assert product is not None
            assert product.version == 1

            barrier.wait()

            product.name = new_name
            try:
                session.commit()
                result = "won"
            except StaleDataError:
                session.rollback()
                result = "lost"

            with lock:
                outcomes.append(result)

    _run_in_parallel(lambda: attempt("Перемога A"), lambda: attempt("Перемога B"))

    assert sorted(outcomes) == ["lost", "won"]

    with SessionLocal() as session:
        product = session.get(Product, committed_product.product_id)
        assert product is not None
        # One increment, not two: the loser wrote nothing at all.
        assert product.version == 2
        assert product.name in {"Перемога A", "Перемога B"}


def test_the_loser_gets_the_error_that_becomes_409(committed_product: Fixture) -> None:
    """Through the service layer, so the mapping to the HTTP contract is covered.

    `VersionConflictError` is what the exception handler turns into 409, so
    asserting its `status_code` here ties the concurrency behaviour to the
    documented contract rather than to an internal exception name.
    """
    barrier = threading.Barrier(2, timeout=BARRIER_TIMEOUT_SECONDS)
    errors: list[VersionConflictError] = []
    successes: list[str] = []
    lock = threading.Lock()

    def attempt(new_name: str) -> None:
        with SessionLocal() as session:
            organization = session.get(Organization, committed_product.organization_id)
            assert organization is not None
            # Load through the service, exactly as the endpoint does.
            product = catalog.get_product(session, organization, committed_product.product_id)
            version = product.version

            barrier.wait()

            try:
                catalog.update_product(
                    session,
                    organization,
                    committed_product.product_id,
                    ProductUpdate(version=version, name=new_name),
                )
                with lock:
                    successes.append(new_name)
            except VersionConflictError as exc:
                with lock:
                    errors.append(exc)

    _run_in_parallel(lambda: attempt("Сервіс A"), lambda: attempt("Сервіс B"))

    assert len(successes) == 1
    assert len(errors) == 1
    assert errors[0].status_code == 409
    assert errors[0].code == "version_conflict"


def test_concurrent_creates_do_not_collide(committed_product: Fixture) -> None:
    """Distinct products are not in contention and both must succeed.

    The counterpart to the tests above: optimistic locking must not turn
    unrelated concurrent writes into failures, or it would be trading
    correctness for throughput nobody asked to lose.
    """
    barrier = threading.Barrier(2, timeout=BARRIER_TIMEOUT_SECONDS)
    created: list[uuid.UUID] = []
    lock = threading.Lock()

    def attempt(name: str) -> None:
        with SessionLocal() as session:
            product = Product(
                organization_id=committed_product.organization_id,
                name=name,
                unit="шт",
                purchase_price=Decimal("1.00"),
            )
            session.add(product)
            barrier.wait()
            session.commit()
            with lock:
                created.append(product.id)

    _run_in_parallel(lambda: attempt("Паралель A"), lambda: attempt("Паралель B"))

    assert len(created) == 2

    with SessionLocal() as session:
        names = set(
            session.scalars(
                select(Product.name).where(
                    Product.organization_id == committed_product.organization_id
                )
            )
        )
    assert {"Паралель A", "Паралель B"} <= names
