from __future__ import annotations

import pytest

from dhvani.clock import FakeClock
from dhvani.telemetry.session import Percentiles, SessionTrace, _percentiles
from dhvani.telemetry.span import TurnTrace
from dhvani.types import Stage


@pytest.mark.asyncio
async def test_percentiles_known_inputs() -> None:
    values = [float(v) for v in range(1, 101)]  # 1..100
    p = _percentiles(values)

    assert p.n == 100
    assert p.p50_ms == pytest.approx(50.0, abs=1.0)
    assert p.p90_ms == pytest.approx(90.0, abs=1.0)
    assert p.p99_ms == pytest.approx(99.0, abs=1.0)
    assert p.max_ms == 100.0


def test_percentiles_degenerate_empty() -> None:
    p = _percentiles([])
    assert p == Percentiles(n=0, p50_ms=0.0, p90_ms=0.0, p99_ms=0.0, max_ms=0.0)


def test_percentiles_degenerate_single() -> None:
    p = _percentiles([42.0])
    assert p == Percentiles(n=1, p50_ms=42.0, p90_ms=42.0, p99_ms=42.0, max_ms=42.0)


@pytest.mark.asyncio
async def test_session_percentiles_over_turns() -> None:
    clock = FakeClock()
    session = SessionTrace(session_id="s1")

    for dur_s in (0.1, 0.2, 0.3):
        trace = TurnTrace(clock, turn_id=f"turn-{dur_s}")
        with trace.span(Stage.STT, "final"):
            await clock.sleep(dur_s)
        session.add(trace)

    p = session.percentiles(Stage.STT)
    assert p.n == 3
    assert p.max_ms == pytest.approx(300.0)
