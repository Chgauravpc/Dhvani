from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from dhvani.clock import FakeClock
from dhvani.config import LatencyBudget
from dhvani.pipeline.sequential import SequentialRunner
from dhvani.providers.mock import MockLLM, MockSTT, MockTiming, MockTTS
from dhvani.telemetry.span import (
    FINAL_TRANSCRIPT,
    FIRST_AUDIO_OUT,
    FIRST_LLM_TOKEN,
    FIRST_PARTIAL,
    USER_SPEECH_END,
)
from dhvani.types import AudioChunk

pytestmark = pytest.mark.asyncio


async def _one_audio_chunk() -> AsyncIterator[AudioChunk]:
    yield AudioChunk(pcm=b"\x00\x00" * 160, sample_rate=16000, seq=0, is_last=True)


def _make_runner(clock: FakeClock) -> SequentialRunner:
    stt = MockSTT(
        partials=["hi"],
        final="hi there",
        timing=MockTiming(ttfb_ms=100.0, per_unit_ms=50.0),
        clock=clock,
    )
    llm = MockLLM(
        response="hello world",
        timing=MockTiming(ttfb_ms=150.0, per_unit_ms=50.0),
        clock=clock,
    )
    tts = MockTTS(timing=MockTiming(ttfb_ms=80.0, per_unit_ms=20.0), clock=clock)
    return SequentialRunner(stt, llm, tts, clock, LatencyBudget())


async def test_sequential_baseline_ttfa_approximately_sums_stage_times() -> None:
    clock = FakeClock()
    runner = _make_runner(clock)

    result = await runner.run_turn(_one_audio_chunk())

    # STT: 100 + 50 (partial, final) = 150ms
    # LLM: 150 + 50 (2 tokens "hello"/"world") + 50 (final delta) = 250ms
    # TTS: 80ms (single-item text iterator -> one chunk)
    expected_ttfa_ms = 150.0 + 250.0 + 80.0
    assert result.trace.ttfa_ms == pytest.approx(expected_ttfa_ms)


async def test_sequential_trace_has_all_reserved_marks_in_order() -> None:
    clock = FakeClock()
    runner = _make_runner(clock)

    result = await runner.run_turn(_one_audio_chunk())

    names = [m.name for m in result.trace.marks]
    expected = [
        USER_SPEECH_END,
        FIRST_PARTIAL,
        FINAL_TRANSCRIPT,
        FIRST_LLM_TOKEN,
        FIRST_AUDIO_OUT,
    ]
    assert names == expected
    assert result.transcript == "hi there"
    assert result.response_text == "hello world"
    assert len(result.audio) == 1
