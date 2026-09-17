"""Time source abstraction.

Every stage of the pipeline takes a `Clock` instead of touching wall-clock
time directly. Never call `time.perf_counter()` or `asyncio.sleep()` outside
this module.
"""

from __future__ import annotations

import asyncio
import time
from typing import Protocol


class Clock(Protocol):
    """Source of monotonic time and sleep, injectable for deterministic tests."""

    def now_ns(self) -> int:
        """Current time in nanoseconds. Not wall-clock-comparable across clocks."""
        ...

    async def sleep(self, seconds: float) -> None:
        """Suspend the current task for `seconds`."""
        ...


class RealClock:
    """Wall-clock time via `time.perf_counter_ns` and `asyncio.sleep`."""

    def now_ns(self) -> int:
        return time.perf_counter_ns()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class VirtualTimeLoop(asyncio.SelectorEventLoop):
    """A `SelectorEventLoop` whose `time()` is virtual.

    When nothing is immediately runnable, the base event loop would normally
    block in the selector for real wall-clock time until the next scheduled
    callback is due. This override instead fast-forwards the virtual clock
    straight to that callback's deadline, so `asyncio.sleep()` and
    `call_later()` resolve instantly in real time while still firing in the
    correct relative order.

    This is the same technique CPython's own asyncio test loop
    (`Lib/test/test_asyncio/utils.py::TestLoop`) uses. It relies on
    `BaseEventLoop`'s private `_ready` / `_scheduled` queues, which is why the
    two lines below carry `type: ignore[attr-defined]`: there is no public API
    for "what's the next scheduled deadline," and this is the standard
    workaround for building a virtual-time asyncio loop.
    """

    def __init__(self) -> None:
        super().__init__()
        self._virtual_time_s = 0.0

    def time(self) -> float:
        return self._virtual_time_s

    def _run_once(self) -> None:
        if not self._ready:  # type: ignore[attr-defined]
            scheduled = [h for h in self._scheduled if not h._cancelled]  # type: ignore[attr-defined]
            if scheduled:
                next_when = min(h._when for h in scheduled)
                if next_when > self._virtual_time_s:
                    self._virtual_time_s = next_when
        super()._run_once()  # type: ignore[misc]  # typeshed omits this private method


class VirtualTimeLoopPolicy(asyncio.DefaultEventLoopPolicy):
    """Event loop policy that hands out `VirtualTimeLoop` instances.

    Install via the `event_loop_policy` fixture in `tests/conftest.py` so that
    `pytest-asyncio` runs a test's whole event loop on virtual time.
    """

    def new_event_loop(self) -> asyncio.AbstractEventLoop:
        return VirtualTimeLoop()


class FakeClock:
    """Deterministic virtual time for tests.

    Requires running inside a `VirtualTimeLoop` (see `VirtualTimeLoopPolicy`
    above) — it has no state of its own and simply reads the running loop's
    virtual clock. Because that loop fast-forwards through idle periods
    instead of sleeping in real time, a simulated 800ms turn completes in
    single-digit milliseconds of real time, with exactly reproducible
    recorded durations across runs, and concurrent sleepers wake in the
    correct relative order because the loop, not this class, orders them.
    """

    def now_ns(self) -> int:
        return int(asyncio.get_running_loop().time() * 1_000_000_000)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
