"""Shared pytest fixtures.

Async tests default to `VirtualTimeLoop` (via the `pytest_asyncio_loop_factories`
hook), so `FakeClock` and plain `asyncio.sleep` calls both resolve instantly in
real time.

Tests that do genuine network I/O (real TCP sockets, not just asyncio.sleep)
must opt out with `@pytest.mark.real_time_loop`: `VirtualTimeLoop` fast-
forwards to the next *scheduled callback* whenever nothing is immediately
ready, which is exactly right for a timer-only workload, but wrong once a
real OS-level socket is involved -- it has no way to know a real connection
attempt is still in flight, so it can jump straight past a connector's
timeout and report a spurious `ConnectionTimeoutError` on the very first
request. Discovered when the aiohttp signaling integration test failed that
way on a loopback server that a plain script (no custom loop) connects to
instantly.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from dhvani.clock import VirtualTimeLoop

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pytest import Config, Item


def pytest_asyncio_loop_factories(config: Config, item: Item) -> Mapping[str, object] | None:
    if item.get_closest_marker("real_time_loop") is not None:
        return {"real_time": asyncio.new_event_loop}
    return {"virtual_time": VirtualTimeLoop}
