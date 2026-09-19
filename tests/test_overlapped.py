from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from dhvani.clock import FakeClock
from dhvani.config import LatencyBudget
from dhvani.pipeline.overlapped import BargeInError, OverlappedRunner
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


def _providers(clock: FakeClock, response: str) -> tuple[MockSTT, MockLLM, MockTTS]:
    stt = MockSTT(
        partials=["hi"],
        final="hi there",
        timing=MockTiming(ttfb_ms=50.0, per_unit_ms=30.0),
        clock=clock,
    )
    llm = MockLLM(
        response=response,
        timing=MockTiming(ttfb_ms=100.0, per_unit_ms=60.0),
        clock=clock,
    )
    tts = MockTTS(timing=MockTiming(ttfb_ms=80.0, per_unit_ms=20.0), clock=clock)
    return stt, llm, tts


async def test_overlapped_ttfa_beats_sequential_for_a_multi_sentence_reply() -> None:
    response = "First sentence here. Second sentence follows. Third and final one."

    seq_clock = FakeClock()
    seq_stt, seq_llm, seq_tts = _providers(seq_clock, response)
    seq_runner = SequentialRunner(seq_stt, seq_llm, seq_tts, seq_clock, LatencyBudget())
    seq_result = await seq_runner.run_turn(_one_audio_chunk())

    ovl_clock = FakeClock()
    ovl_stt, ovl_llm, ovl_tts = _providers(ovl_clock, response)
    ovl_runner = OverlappedRunner(ovl_stt, ovl_llm, ovl_tts, ovl_clock, LatencyBudget())
    ovl_result = await ovl_runner.run_turn(_one_audio_chunk())

    assert seq_result.trace.ttfa_ms is not None
    assert ovl_result.trace.ttfa_ms is not None
    # FakeClock makes these exact and reproducible: sequential is ~956.0ms,
    # overlapped ~419.2ms, a ~536.8ms improvement. Assert a floor comfortably
    # below that (not just "any improvement"), so a regression that
    # collapses the overlap benefit to a few ms -- e.g. reintroducing an
    # accidental full-response wait before TTS starts -- fails loudly
    # instead of squeaking through on a 1ns margin.
    improvement_ms = seq_result.trace.ttfa_ms - ovl_result.trace.ttfa_ms
    assert improvement_ms >= 400.0, (
        f"expected overlap to save >= 400ms, saved only {improvement_ms:.1f}ms"
    )
    # Same provider timings, same content -- only the overlap should differ.
    assert ovl_result.response_text == seq_result.response_text == response


async def test_overlapped_trace_has_all_reserved_marks_in_order() -> None:
    clock = FakeClock()
    stt, llm, tts = _providers(clock, "Hello world. How are you?")
    runner = OverlappedRunner(stt, llm, tts, clock, LatencyBudget())

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
    assert len(result.audio) > 0


async def test_barge_in_cancels_llm_and_tts_and_closes_their_spans() -> None:
    clock = FakeClock()
    # Short, separately-punctuated sentences so the first one is ready (and
    # TTS has started synthesizing) well before the trigger below fires --
    # a single late period (e.g. one long sentence) would mean TTS is still
    # waiting on its very first sentence at that point, and (since the span
    # now opens only once real work starts, not at generator creation --
    # see PiperTTS/MockTTS) there would be no TTS span yet to cancel.
    stt, llm, tts = _providers(clock, "One. Two. Three. Four. Five.")
    runner = OverlappedRunner(stt, llm, tts, clock, LatencyBudget())
    barge_in = asyncio.Event()

    async def trigger_after_first_chunk() -> None:
        # Give the pipeline a moment to produce at least one audio chunk
        # before the user "interrupts".
        await clock.sleep(0.3)
        barge_in.set()

    trigger_task = asyncio.create_task(trigger_after_first_chunk())

    with pytest.raises(BargeInError) as exc_info:
        await runner.run_turn(_one_audio_chunk(), barge_in=barge_in)

    await trigger_task

    trace = exc_info.value.trace
    llm_spans = [s for s in trace.spans if s.stage.value == "llm"]
    tts_spans = [s for s in trace.spans if s.stage.value == "tts"]
    assert llm_spans and all(not s.is_open for s in llm_spans)
    assert tts_spans and all(not s.is_open for s in tts_spans)
    assert any("CancelledError" in str(s.attrs.get("error", "")) for s in llm_spans + tts_spans)


async def test_no_barge_in_event_runs_to_completion() -> None:
    clock = FakeClock()
    stt, llm, tts = _providers(clock, "Just a short reply.")
    runner = OverlappedRunner(stt, llm, tts, clock, LatencyBudget())

    result = await runner.run_turn(_one_audio_chunk(), barge_in=None)

    assert result.response_text == "Just a short reply."
