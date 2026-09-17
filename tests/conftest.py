"""Shared pytest fixtures.

All async tests run on `VirtualTimeLoop` (via the `pytest_asyncio_loop_factories`
hook), so `FakeClock` and plain `asyncio.sleep` calls both resolve instantly in
real time. Tests that need genuine wall-clock behavior are not expected in this
suite — Phase 0 has none.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dhvani.clock import VirtualTimeLoop

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pytest import Config, Item


def pytest_asyncio_loop_factories(config: Config, item: Item) -> Mapping[str, object] | None:
    return {"virtual_time": VirtualTimeLoop}
