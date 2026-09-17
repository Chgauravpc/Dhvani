from __future__ import annotations

import asyncio
import time

import pytest

from dhvani.clock import FakeClock

pytestmark = pytest.mark.asyncio


async def test_fake_clock_determinism() -> None:
    """Two identical runs on FakeClock give identical recorded durations."""

    async def run_once() -> int:
        clock = FakeClock()
        start_ns = clock.now_ns()
        await clock.sleep(0.1)
        await clock.sleep(0.25)
        return clock.now_ns() - start_ns

    first = await run_once()
    second = await run_once()

    assert first == second
    assert first == 350_000_000  # 0.1s + 0.25s in ns, exact under virtual time


async def test_fake_clock_completes_fast_in_real_time() -> None:
    """An 800ms simulated turn must complete in single-digit ms of real time."""
    clock = FakeClock()
    real_start_s = time.perf_counter()
    await clock.sleep(0.8)
    real_elapsed_ms = (time.perf_counter() - real_start_s) * 1000

    assert clock.now_ns() == 800_000_000
    assert real_elapsed_ms < 50


async def test_sleep_ordering_concurrent_sleepers() -> None:
    """Concurrent sleepers with different durations wake in deadline order."""
    clock = FakeClock()
    order: list[str] = []

    async def sleeper(name: str, seconds: float) -> None:
        await clock.sleep(seconds)
        order.append(name)

    await asyncio.gather(
        sleeper("c", 0.3),
        sleeper("a", 0.1),
        sleeper("b", 0.2),
    )

    assert order == ["a", "b", "c"]
