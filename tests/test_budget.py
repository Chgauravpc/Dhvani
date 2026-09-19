from __future__ import annotations

import os
from pathlib import Path

import pytest

from dhvani.clock import FakeClock
from dhvani.config import LatencyBudget, load_dotenv
from dhvani.telemetry.span import FIRST_AUDIO_OUT, USER_SPEECH_END, TurnTrace
from dhvani.types import Stage


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_budget_no_violations_when_within_targets() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")
    budget = LatencyBudget()

    trace.mark(USER_SPEECH_END)
    with trace.span(Stage.STT, "final"):
        await clock.sleep(0.05)
    trace.mark(FIRST_AUDIO_OUT)

    assert budget.violations(trace) == []


def test_load_dotenv_sets_unset_variables(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text('FOO=bar\n# a comment\n\nQUOTED="baz qux"\n')
    assert "FOO" not in os.environ and "QUOTED" not in os.environ

    try:
        load_dotenv(env_file)
        assert os.environ["FOO"] == "bar"
        assert os.environ["QUOTED"] == "baz qux"
    finally:
        os.environ.pop("FOO", None)
        os.environ.pop("QUOTED", None)


def test_load_dotenv_never_overrides_existing_env(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=from_file\n")
    os.environ["FOO"] = "from_real_env"

    try:
        load_dotenv(env_file)
        assert os.environ["FOO"] == "from_real_env"
    finally:
        os.environ.pop("FOO", None)


def test_load_dotenv_missing_file_is_a_noop(tmp_path: Path) -> None:
    load_dotenv(tmp_path / "does_not_exist.env")
