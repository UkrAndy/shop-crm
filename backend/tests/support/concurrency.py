"""Running things genuinely in parallel, and proving that they were.

Two statements in one transaction never contend, so every test that means to
exercise a race has to open its own connections and commit for real. This module
holds the mechanics so the tests can hold the argument.

**The barrier is not decoration.** Without it, the first worker can finish before
the second has even started, and the test passes while proving nothing. Every
helper here rendezvouses the workers before the interesting part.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Generous enough to outlast a row lock held for one statement. If it is ever
# reached, the test has found a deadlock — which is a result worth failing on
# rather than waiting out.
DEFAULT_TIMEOUT_SECONDS = 15.0


@dataclass
class ParallelOutcome:
    """What each worker returned, and how long it took.

    Durations are kept because "did these actually overlap?" is a question about
    time, and answering it by inspection is guesswork.
    """

    # `list[...]` as the factory rather than bare `list`, so the element type
    # survives into the annotation instead of degrading to `Unknown`.
    values: list[Any] = field(default_factory=list[Any])
    errors: list[BaseException] = field(default_factory=list[BaseException])
    durations: list[float] = field(default_factory=list[float])

    @property
    def codes(self) -> list[str]:
        """Error codes for anything that raised an `AppError`-shaped exception.

        Useful because a race's interesting outcome is usually *which* refusal
        the loser got, not that it raised at all.
        """
        return sorted(getattr(error, "code", type(error).__name__) for error in self.errors)


def run_in_parallel(
    *workers: Callable[[], Any],
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> ParallelOutcome:
    """Start every worker at the same instant and collect what happened.

    Each worker waits on a shared barrier first, so the interesting part of all
    of them begins together. Exceptions are captured rather than propagated —
    in a race, one worker failing is usually the expected result, and the test
    wants to assert *which* failure.
    """
    barrier = threading.Barrier(len(workers), timeout=timeout)
    outcome = ParallelOutcome()
    guard = threading.Lock()

    def wrap(worker: Callable[[], Any]) -> Callable[[], None]:
        def run() -> None:
            barrier.wait()
            started = time.perf_counter()
            try:
                value = worker()
            except BaseException as error:  # noqa: BLE001 - the point is to capture it
                elapsed = time.perf_counter() - started
                with guard:
                    outcome.errors.append(error)
                    outcome.durations.append(elapsed)
            else:
                elapsed = time.perf_counter() - started
                with guard:
                    outcome.values.append(value)
                    outcome.durations.append(elapsed)

        return run

    threads = [threading.Thread(target=wrap(worker)) for worker in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=timeout * 2)

    for thread in threads:
        assert not thread.is_alive(), "a worker never finished — most likely a deadlock"

    return outcome
