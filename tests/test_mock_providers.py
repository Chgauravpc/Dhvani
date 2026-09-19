from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from dhvani.clock import FakeClock
from dhvani.providers.base import ProviderError
from dhvani.providers.mock import MockLLM, MockSTT, MockTiming, MockTTS
from dhvani.telemetry.span import TurnTrace
from dhvani.types import AudioChunk, Message, ToolCall

pytestmark = pytest.mark.asyncio


async def _one_audio_chunk() -> AsyncIterator[AudioChunk]:
    yield AudioChunk(pcm=b"\x00\x00" * 160, sample_rate=16000, seq=0, is_last=True)


async def test_mock_stt_honours_declared_timing() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")
    stt = MockSTT(
        partials=["a", "ab"],
        final="ab",
        timing=MockTiming(ttfb_ms=100.0, per_unit_ms=50.0),
        clock=clock,
    )

    start_ns = clock.now_ns()
    timings_ms: list[float] = []
    async for _ in stt.stream(_one_audio_chunk(), trace=trace):
        timings_ms.append((clock.now_ns() - start_ns) / 1_000_000)

    assert timings_ms == pytest.approx([100.0, 150.0, 200.0])


async def test_mock_llm_tool_calls_before_final() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")
    call = ToolCall(id="1", name="lookup", arguments={})
    llm = MockLLM(
        response="hi there",
        timing=MockTiming(ttfb_ms=10.0, per_unit_ms=10.0),
        clock=clock,
        tool_calls=[call],
    )

    deltas = [d async for d in llm.stream([Message(role="user", content="hi")], trace=trace)]

    # Whitespace-preserving: concatenating text deltas reproduces "hi there".
    assert deltas[0].text == "hi "
    assert deltas[1].text == "there"
    assert "".join(d.text for d in deltas[:2]) == "hi there"
    assert deltas[2].tool_call == call
    assert deltas[3].is_final


async def test_mock_tts_emits_silence_chunks() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")
    tts = MockTTS(timing=MockTiming(ttfb_ms=50.0, per_unit_ms=20.0), clock=clock)

    async def text() -> AsyncIterator[str]:
        yield "hello"
        yield "world"

    chunks = [c async for c in tts.stream(text(), trace=trace)]

    assert len(chunks) == 2
    assert all(set(c.pcm) == {0} for c in chunks)
    assert [c.seq for c in chunks] == [0, 1]


async def test_mock_provider_cancellation_closes_span_and_reraises() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")
    stt = MockSTT(
        partials=["a", "b", "c"],
        final="abc",
        timing=MockTiming(ttfb_ms=100.0, per_unit_ms=100.0),
        clock=clock,
    )
    started = asyncio.Event()

    async def consume() -> None:
        async for _ in stt.stream(_one_audio_chunk(), trace=trace):
            started.set()

    task = asyncio.create_task(consume())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not trace.spans[0].is_open
    assert "CancelledError" in str(trace.spans[0].attrs["error"])


async def test_mock_provider_fail_after_raises_provider_error() -> None:
    clock = FakeClock()
    trace = TurnTrace(clock, turn_id="t1")
    stt = MockSTT(
        partials=["a", "b", "c"],
        final="abc",
        timing=MockTiming(ttfb_ms=10.0, per_unit_ms=10.0),
        clock=clock,
        fail_after=2,
    )

    emitted = 0
    with pytest.raises(ProviderError):
        async for _ in stt.stream(_one_audio_chunk(), trace=trace):
            emitted += 1

    assert emitted == 2
