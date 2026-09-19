from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from dhvani.clock import FakeClock
from dhvani.config import LatencyBudget
from dhvani.pipeline.overlapped import OverlappedRunner
from dhvani.pipeline.session import ConversationSession
from dhvani.providers.mock import MockLLM, MockSTT, MockTiming, MockTTS
from dhvani.types import AudioChunk
from dhvani.vad.endpointer import EndpointEvent

pytestmark = pytest.mark.asyncio


class _ScriptedEndpointer:
    """Returns pre-scripted events per call, independent of chunk content --
    Endpointer's own windowing/threshold logic is tested separately in
    test_endpointer.py; this isolates ConversationSession's turn-taking."""

    def __init__(self, events_by_call: dict[int, list[EndpointEvent]]) -> None:
        self._events_by_call = events_by_call
        self._call_index = 0

    def feed(self, chunk: AudioChunk) -> list[EndpointEvent]:
        events = self._events_by_call.get(self._call_index, [])
        self._call_index += 1
        return events


def _chunk(seq: int) -> AudioChunk:
    return AudioChunk(pcm=b"\x00\x00", sample_rate=16000, seq=seq)


def _make_runner(clock: FakeClock, response: str) -> OverlappedRunner:
    stt = MockSTT(
        partials=["hi"],
        final="hi there",
        timing=MockTiming(ttfb_ms=10.0, per_unit_ms=10.0),
        clock=clock,
    )
    llm = MockLLM(response=response, timing=MockTiming(ttfb_ms=10.0, per_unit_ms=10.0), clock=clock)
    tts = MockTTS(timing=MockTiming(ttfb_ms=10.0, per_unit_ms=10.0), clock=clock)
    return OverlappedRunner(stt, llm, tts, clock, LatencyBudget())


async def test_single_turn_runs_and_pushes_audio_to_sink() -> None:
    clock = FakeClock()
    runner = _make_runner(clock, "Hello there.")
    endpointer = _ScriptedEndpointer(
        {0: [EndpointEvent.SPEECH_STARTED], 1: [EndpointEvent.SPEECH_ENDED]}
    )
    pushed: list[AudioChunk] = []
    session = ConversationSession(runner, endpointer, pushed.append)

    async def audio() -> AsyncIterator[AudioChunk]:
        yield _chunk(0)
        yield _chunk(1)

    await session.run(audio())

    assert len(session.session_trace.turns) == 1
    assert len(pushed) > 0


async def test_barge_in_mid_playback_starts_a_second_turn() -> None:
    clock = FakeClock()
    runner = _make_runner(clock, "One. Two. Three.")
    endpointer = _ScriptedEndpointer(
        {
            0: [EndpointEvent.SPEECH_STARTED],
            1: [EndpointEvent.SPEECH_ENDED],
            2: [EndpointEvent.SPEECH_STARTED],  # barge-in, mid TTS playback
            3: [EndpointEvent.SPEECH_ENDED],
        }
    )
    pushed: list[AudioChunk] = []
    session = ConversationSession(runner, endpointer, pushed.append)

    async def audio() -> AsyncIterator[AudioChunk]:
        yield _chunk(0)
        yield _chunk(1)
        # Let turn 1 progress past STT (~20ms) and LLM's first sentence
        # (~10ms) into TTS (first audio chunk at ~40ms), before interrupting.
        await clock.sleep(0.045)
        yield _chunk(2)
        yield _chunk(3)

    await session.run(audio())

    assert len(session.session_trace.turns) == 2
    first_turn, second_turn = session.session_trace.turns
    tts_spans = [s for s in first_turn.spans if s.stage.value == "tts"]
    assert tts_spans and all(not s.is_open for s in tts_spans)
    assert any("CancelledError" in str(s.attrs.get("error", "")) for s in tts_spans)
    assert second_turn.ttfa_ms is not None


async def test_no_speech_produces_no_turns() -> None:
    clock = FakeClock()
    runner = _make_runner(clock, "unused")
    endpointer = _ScriptedEndpointer({})
    pushed: list[AudioChunk] = []
    session = ConversationSession(runner, endpointer, pushed.append)

    async def audio() -> AsyncIterator[AudioChunk]:
        yield _chunk(0)
        yield _chunk(1)

    await session.run(audio())

    assert session.session_trace.turns == []
    assert pushed == []
