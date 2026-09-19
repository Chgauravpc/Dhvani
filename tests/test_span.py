from __future__ import annotations

import asyncio

import pytest

from dhvani.clock import FakeClock
from dhvani.telemetry.span import FIRST_AUDIO_OUT, USER_SPEECH_END, Mark, Span, TurnTrace
from dhvani.types import Stage

pytestmark = pytest.mark.asyncio


async def test_span_records_duration() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")

    with trace.span(Stage.STT, "final") as s:
        await clock.sleep(0.1)

    assert s.duration_ms == pytest.approx(100.0)
    assert not s.is_open


async def test_overlapping_spans_stage_total_is_interval_union() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")

    async def run_span(name: str, delay_s: float, dur_s: float) -> None:
        await clock.sleep(delay_s)
        with trace.span(Stage.LLM, name):
            await clock.sleep(dur_s)

    # [0, 300)ms and [100, 250)ms overlap; the union should be [0, 300)ms =
    # 300ms, not the naive sum of durations (300 + 150 = 450ms).
    await asyncio.gather(
        run_span("a", 0.0, 0.3),
        run_span("b", 0.1, 0.15),
    )

    assert trace.stage_total_ms(Stage.LLM) == pytest.approx(300.0)


async def test_span_exception_closes_span_and_reraises() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")

    with pytest.raises(RuntimeError):
        with trace.span(Stage.TOOL, "call") as s:
            raise RuntimeError("boom")

    assert not s.is_open
    assert s.attrs["error"] == repr(RuntimeError("boom"))


async def test_aspan_cancellation_closes_span_and_reraises() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")
    started = asyncio.Event()

    async def worker() -> None:
        async with trace.aspan(Stage.TTS, "synth"):
            started.set()
            await clock.sleep(10)

    task = asyncio.create_task(worker())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    span = trace.spans[0]
    assert not span.is_open
    assert "CancelledError" in str(span.attrs["error"])


async def test_ttfa_measured_from_user_speech_end() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")

    await clock.sleep(0.05)  # noise before the turn "officially" starts
    trace.mark(USER_SPEECH_END)
    await clock.sleep(0.6)
    trace.mark(FIRST_AUDIO_OUT)

    assert trace.ttfa_ms == pytest.approx(600.0)


async def test_ttfa_is_none_without_first_audio_out() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")
    trace.mark(USER_SPEECH_END)

    assert trace.ttfa_ms is None


async def test_critical_path_includes_spans_still_open_at_first_audio_out() -> None:
    """Regression test for an overlapped trace: STT ends at 80ms, then LLM
    and TTS run concurrently from 80ms to 780ms, with FIRST_AUDIO_OUT at
    380ms (mid-way through both). All three are genuinely on the path to
    first audio -- LLM and TTS being still open past 380ms must not exclude
    them just because they haven't closed yet.
    """
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")
    trace.spans = [
        Span(stage=Stage.STT, name="mock-stt", start_ns=0, end_ns=80_000_000),
        Span(stage=Stage.LLM, name="mock-llm", start_ns=80_000_000, end_ns=780_000_000),
        Span(stage=Stage.TTS, name="mock-tts", start_ns=80_000_000, end_ns=780_000_000),
    ]
    trace.marks = [Mark(name=FIRST_AUDIO_OUT, at_ns=380_000_000)]

    path = trace.critical_path()

    assert {(s.stage, s.name) for s in path} == {
        (Stage.STT, "mock-stt"),
        (Stage.LLM, "mock-llm"),
        (Stage.TTS, "mock-tts"),
    }
