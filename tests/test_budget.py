from __future__ import annotations

import pytest

from dhvani.clock import FakeClock
from dhvani.config import LatencyBudget
from dhvani.telemetry.span import FIRST_AUDIO_OUT, USER_SPEECH_END, TurnTrace
from dhvani.types import Stage

pytestmark = pytest.mark.asyncio


async def test_budget_detects_stage_and_ttfa_violations() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")
    budget = LatencyBudget(
        ttfa_target_ms=500.0,
        stage_budgets_ms={Stage.STT: 100.0},
    )

    trace.mark(USER_SPEECH_END)
    with trace.span(Stage.STT, "final"):
        await clock.sleep(0.25)  # 250ms, over the 100ms STT budget
    trace.mark(FIRST_AUDIO_OUT)  # 250ms TTFA total, under the 500ms target

    violations = budget.violations(trace)

    assert len(violations) == 1
    v = violations[0]
    assert v.stage is Stage.STT
    assert v.budget_ms == 100.0
    assert v.actual_ms == pytest.approx(250.0)
    assert v.over_by_ms == pytest.approx(150.0)


async def test_budget_no_violations_when_within_targets() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")
    budget = LatencyBudget()

    trace.mark(USER_SPEECH_END)
    with trace.span(Stage.STT, "final"):
        await clock.sleep(0.05)
    trace.mark(FIRST_AUDIO_OUT)

    assert budget.violations(trace) == []
