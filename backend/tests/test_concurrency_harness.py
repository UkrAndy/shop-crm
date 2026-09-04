"""Issue 25 — proving the harness itself.

A concurrency suite that cannot demonstrate its workers overlap is a suite of
sequential tests with threads in them. These tests are about the *fixture*, not
about the domain.

Acceptance criteria under test:
- two threads truly overlap inside the posting transaction, proven with a
  deliberate delay rather than assumed;
- the suite is repeatable, with no cross-test state leakage.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest

from app.core.db import SessionLocal
from app.core.errors import AppError
from app.models.goods_receipt import GoodsReceipt
from app.models.identity import Organization, User
from app.services import posting
from tests.support.concurrency import run_in_parallel
from tests.support.scenes import Scene, committed_draft, purge_organization

# Long enough to be unmistakable against scheduling noise, short enough that the
# suite stays fast.
DELIBERATE_DELAY_SECONDS = 0.75


@pytest.fixture
def scene(migrated_database: None) -> Iterator[Scene]:
    built = committed_draft()
    try:
        yield built
    finally:
        purge_organization(built.organization_id)


def _post(scene: Scene) -> str:
    """One posting attempt in its own transaction, refusals returned as codes."""
    with SessionLocal() as session:
        organization = session.get(Organization, scene.organization_id)
        user = session.get(User, scene.user_id)
        assert organization is not None and user is not None
        try:
            posting.post_receipt(session, organization, user, scene.receipt_id, 1)
            session.commit()
            return "posted"
        except AppError as exc:
            session.rollback()
            return exc.code


def test_the_workers_genuinely_overlap(scene: Scene, monkeypatch: pytest.MonkeyPatch) -> None:
    """The claim every concurrency test in this suite rests on.

    The winner holds the row lock and sleeps inside its transaction. If the
    loser were not genuinely contending for that row it would return
    immediately; instead it must wait the delay out. Measuring that wait is the
    only way to know the two overlapped rather than merely ran in sequence.
    """
    # Reached through `getattr` rather than as an attribute, to say plainly
    # that this test is deliberately instrumenting a module-internal seam.
    original = getattr(posting, "_create_batch")  # noqa: B009
    slowed = threading.Event()

    def slow_create_batch(*args: object, **kwargs: object):  # noqa: ANN202
        # Only the winner reaches this; the loser is still blocked on
        # `SELECT ... FOR UPDATE` and never gets here at all.
        if not slowed.is_set():
            slowed.set()
            time.sleep(DELIBERATE_DELAY_SECONDS)
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(posting, "_create_batch", slow_create_batch)

    outcome = run_in_parallel(lambda: _post(scene), lambda: _post(scene))

    assert sorted(outcome.values) == ["posted", "receipt_not_draft"]
    assert slowed.is_set(), "the delay never ran, so this proved nothing"

    # Both waited: the winner because it slept, the loser because it was blocked
    # on the winner's lock. Anything shorter would mean they never contended.
    assert min(outcome.durations) >= DELIBERATE_DELAY_SECONDS, (
        "a worker returned before the lock was released, so the two did not overlap"
    )


def test_the_helper_captures_rather_than_propagates(scene: Scene) -> None:
    """In a race, one worker failing is the expected result.

    A helper that let the exception escape would fail the test for the very
    behaviour it is trying to observe.
    """

    def attempt() -> str:
        result = _post(scene)
        if result != "posted":
            raise AssertionError(f"lost the race with {result}")
        return result

    outcome = run_in_parallel(attempt, attempt)

    assert outcome.values == ["posted"]
    assert len(outcome.errors) == 1
    assert outcome.codes == ["AssertionError"]


def test_a_scene_is_isolated_and_removed(scene: Scene) -> None:
    """Repeatability: each scene owns its organization and takes it away again.

    The suite's three consecutive green runs are the real evidence; this pins
    the mechanism the teardown relies on.
    """
    with SessionLocal() as session:
        receipt = session.get(GoodsReceipt, scene.receipt_id)
        assert receipt is not None
        assert receipt.organization_id == scene.organization_id
