"""Full loopback over a real localhost WebSocket, no external service --
phase-3 spec section 8. Exercises `MockTwilioServer` (7.5) and
`MediaStreamsTransport` (7.4) together over genuine aiohttp sockets, the
same "strongest verification available without the real platform" rationale
as `test_signaling_integration.py`."""

from __future__ import annotations

from array import array

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from dhvani.clock import RealClock
from dhvani.config import LatencyBudget
from dhvani.pipeline.overlapped import OverlappedRunner
from dhvani.pipeline.session import ConversationSession
from dhvani.providers.mock import MockLLM, MockSTT, MockTiming, MockTTS
from dhvani.transport.mediastreams import MediaStreamsTransport
from dhvani.transport.mock_twilio import MockTwilioServer
from dhvani.types import AudioChunk
from dhvani.vad.endpointer import EndpointEvent

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.real_time_loop]


class _AlwaysStartThenEndEndpointer:
    """Speech starts on the first chunk fed, ends after `end_after` more --
    deterministic without a real VAD, same rationale as
    tests/test_conversation_session.py's scripted endpointer."""

    def __init__(self, end_after: int) -> None:
        self._end_after = end_after
        self._count = 0

    def feed(self, chunk: AudioChunk) -> list[EndpointEvent]:
        self._count += 1
        if self._count == 1:
            return [EndpointEvent.SPEECH_STARTED]
        if self._count == 1 + self._end_after:
            return [EndpointEvent.SPEECH_ENDED]
        return []


def _make_runner(clock: RealClock) -> OverlappedRunner:
    stt = MockSTT(
        partials=["hi"],
        final="hi there",
        timing=MockTiming(ttfb_ms=1.0, per_unit_ms=1.0),
        clock=clock,
    )
    llm = MockLLM(response="Hello.", timing=MockTiming(ttfb_ms=1.0, per_unit_ms=1.0), clock=clock)
    tts = MockTTS(timing=MockTiming(ttfb_ms=1.0, per_unit_ms=1.0), clock=clock)
    return OverlappedRunner(stt, llm, tts, clock, LatencyBudget())


async def test_full_loopback_against_a_real_websocket() -> None:
    clock = RealClock()
    tone = array("h", [3000 if i % 20 < 10 else -3000 for i in range(1600)]).tobytes()  # 200ms @ 8k
    mock_server = MockTwilioServer(source_pcm=tone, clock=clock)

    runner = _make_runner(clock)
    endpointer = _AlwaysStartThenEndEndpointer(end_after=3)
    session = ConversationSession(runner, endpointer, lambda _chunk: None)
    transport = MediaStreamsTransport(session, clock)

    app = web.Application()
    app.router.add_get("/mock-twilio", mock_server.handle)

    async with TestClient(TestServer(app)) as client:
        ws = await client.ws_connect("/mock-twilio")
        try:
            await transport.handle(ws)
        finally:
            if not ws.closed:
                await ws.close()

    assert mock_server.stopped_by_peer is False  # the mock stopped the call itself
    assert len(mock_server.received_media_ulaw) > 0
    assert len(mock_server.received_marks) > 0
    assert len(mock_server.received_marks) == len(set(mock_server.received_marks))
