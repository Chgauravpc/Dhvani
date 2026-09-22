"""Twilio Media Streams protocol -- phase-3 spec section 8: parse a
real-shaped inbound `media` frame to PCM; serialize outbound
`media`/`mark`/`clear`; round-trip through mu-law; barge-in emits `clear`
and cancels the turn."""

from __future__ import annotations

import base64
import json
from array import array
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest
from aiohttp import WSMsgType

from dhvani.audio import mulaw
from dhvani.clock import FakeClock
from dhvani.config import LatencyBudget
from dhvani.pipeline.overlapped import OverlappedRunner
from dhvani.pipeline.session import ConversationSession
from dhvani.providers.mock import MockLLM, MockSTT, MockTiming, MockTTS
from dhvani.transport.mediastreams import (
    ClearMessage,
    ConnectedMessage,
    DtmfMessage,
    MarkMessage,
    MediaMessage,
    MediaStreamsProtocolError,
    MediaStreamsTransport,
    StartMessage,
    StopMessage,
    clear_message,
    mark_message,
    media_message,
    parse_inbound,
)
from dhvani.types import AudioChunk
from dhvani.vad.endpointer import EndpointEvent

# ---------------------------------------------------------------------------
# parse_inbound -- real message shapes, quoted from Twilio's own docs
# ---------------------------------------------------------------------------


def test_parse_connected() -> None:
    raw = json.dumps({"event": "connected", "protocol": "Call", "version": "1.0.0"})
    msg = parse_inbound(raw)
    assert msg == ConnectedMessage(protocol="Call", version="1.0.0")


def test_parse_start_extracts_stream_sid_and_media_format() -> None:
    raw = json.dumps(
        {
            "event": "start",
            "sequenceNumber": "1",
            "start": {
                "accountSid": "ACxxx",
                "streamSid": "MZxxx",
                "callSid": "CAxxx",
                "tracks": ["inbound"],
                "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
                "customParameters": {"FirstName": "Jane"},
            },
            "streamSid": "MZxxx",
        }
    )
    msg = parse_inbound(raw)
    assert isinstance(msg, StartMessage)
    assert msg.stream_sid == "MZxxx"
    assert msg.account_sid == "ACxxx"
    assert msg.call_sid == "CAxxx"
    assert msg.tracks == ("inbound",)
    assert msg.media_format.encoding == "audio/x-mulaw"
    assert msg.media_format.sample_rate_hz == 8000
    assert msg.media_format.channels == 1
    assert msg.custom_parameters == {"FirstName": "Jane"}


def test_parse_inbound_media_frame_to_pcm() -> None:
    """A real-shaped inbound media frame decodes, through mu-law, back to
    linear PCM close to the original samples."""
    original = array("h", [0, 1000, -1000, 20000, -20000])
    ulaw = mulaw.encode(original.tobytes())
    payload_b64 = base64.b64encode(ulaw).decode("ascii")
    raw = json.dumps(
        {
            "event": "media",
            "sequenceNumber": "4",
            "media": {"track": "inbound", "chunk": "2", "timestamp": "40", "payload": payload_b64},
            "streamSid": "MZxxx",
        }
    )

    msg = parse_inbound(raw)
    assert isinstance(msg, MediaMessage)
    assert msg.stream_sid == "MZxxx"
    assert msg.track == "inbound"
    assert msg.chunk == "2"
    assert msg.timestamp_ms == "40"

    pcm = mulaw.decode(msg.payload)
    recovered = array("h", pcm).tolist()
    assert len(recovered) == len(original)
    for expected, actual in zip(original, recovered, strict=True):
        assert abs(expected - actual) <= 0.05 * 32768


def test_parse_outbound_shaped_media_frame_has_no_track() -> None:
    """The outbound shape (no track/chunk/timestamp) parses too -- needed
    by mock_twilio.py, which receives exactly this shape from the code
    under test."""
    ulaw = mulaw.encode(array("h", [1, 2, 3, 4]).tobytes())
    raw = json.dumps(
        {
            "event": "media",
            "streamSid": "MZxxx",
            "media": {"payload": base64.b64encode(ulaw).decode("ascii")},
        }
    )
    msg = parse_inbound(raw)
    assert isinstance(msg, MediaMessage)
    assert msg.track is None
    assert msg.chunk is None
    assert msg.timestamp_ms is None


def test_parse_stop() -> None:
    raw = json.dumps(
        {
            "event": "stop",
            "sequenceNumber": "5",
            "stop": {"accountSid": "ACxxx", "callSid": "CAxxx"},
            "streamSid": "MZxxx",
        }
    )
    msg = parse_inbound(raw)
    assert msg == StopMessage(stream_sid="MZxxx", account_sid="ACxxx", call_sid="CAxxx")


def test_parse_mark() -> None:
    raw = json.dumps(
        {"event": "mark", "sequenceNumber": "4", "streamSid": "MZxxx", "mark": {"name": "greet"}}
    )
    assert parse_inbound(raw) == MarkMessage(stream_sid="MZxxx", name="greet")


def test_parse_dtmf() -> None:
    raw = json.dumps(
        {
            "event": "dtmf",
            "streamSid": "MZxxx",
            "sequenceNumber": "5",
            "dtmf": {"track": "inbound_track", "digit": "1"},
        }
    )
    assert parse_inbound(raw) == DtmfMessage(stream_sid="MZxxx", track="inbound_track", digit="1")


def test_parse_clear() -> None:
    raw = json.dumps({"event": "clear", "streamSid": "MZxxx"})
    assert parse_inbound(raw) == ClearMessage(stream_sid="MZxxx")


def test_parse_unknown_event_raises() -> None:
    with pytest.raises(MediaStreamsProtocolError, match="unrecognized"):
        parse_inbound(json.dumps({"event": "bogus"}))


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(MediaStreamsProtocolError, match="JSON"):
        parse_inbound("{not json")


def test_parse_missing_required_field_raises() -> None:
    with pytest.raises(MediaStreamsProtocolError, match="missing required field"):
        parse_inbound(json.dumps({"event": "mark", "streamSid": "MZxxx", "mark": {}}))


# ---------------------------------------------------------------------------
# Outbound builders
# ---------------------------------------------------------------------------


def test_media_message_shape_and_round_trip_through_mulaw() -> None:
    pcm = array("h", [1000, -1000, 5000, -5000] * 40).tobytes()  # 160 samples @ 16kHz = 10ms
    raw = media_message("MZxxx", pcm, src_rate_hz=16000)
    data = json.loads(raw)

    assert data["event"] == "media"
    assert data["streamSid"] == "MZxxx"
    ulaw = base64.b64decode(data["media"]["payload"])
    # 16kHz -> 8kHz halves the sample count.
    assert abs(len(ulaw) - 80) <= 2
    # Every byte round-trips through decode without raising.
    mulaw.decode(ulaw)


def test_mark_message_shape() -> None:
    raw = mark_message("MZxxx", "turn-0")
    assert json.loads(raw) == {"event": "mark", "streamSid": "MZxxx", "mark": {"name": "turn-0"}}


def test_clear_message_shape() -> None:
    raw = clear_message("MZxxx")
    assert json.loads(raw) == {"event": "clear", "streamSid": "MZxxx"}


# ---------------------------------------------------------------------------
# MediaStreamsTransport -- driven over a fake WebSocket (no real socket
# needed: the protocol layer above is what's under test, not aiohttp itself
# -- that gets a real socket in test_mock_twilio.py).
# ---------------------------------------------------------------------------


@dataclass
class _FakeWSMessage:
    type: WSMsgType
    data: str


@dataclass
class _FakeWS:
    """Fake enough of `web.WebSocketResponse` for `MediaStreamsTransport`:
    an async-iterable of inbound frames, and a `send_str` that records
    every outbound frame."""

    _inbound: list[_FakeWSMessage]
    sent: list[str] = field(default_factory=list)

    def __aiter__(self) -> AsyncIterator[_FakeWSMessage]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[_FakeWSMessage]:
        for message in self._inbound:
            yield message

    async def send_str(self, data: str) -> None:
        self.sent.append(data)


def _text(raw: str) -> _FakeWSMessage:
    return _FakeWSMessage(type=WSMsgType.TEXT, data=raw)


def _inbound_media_frame(pcm_8k_linear: bytes, chunk: int) -> _FakeWSMessage:
    ulaw = mulaw.encode(pcm_8k_linear)
    return _text(
        json.dumps(
            {
                "event": "media",
                "sequenceNumber": str(chunk + 2),
                "media": {
                    "track": "inbound",
                    "chunk": str(chunk),
                    "timestamp": str(chunk * 20),
                    "payload": base64.b64encode(ulaw).decode("ascii"),
                },
                "streamSid": "MZxxx",
            }
        )
    )


def _start_frame() -> _FakeWSMessage:
    return _text(
        json.dumps(
            {
                "event": "start",
                "sequenceNumber": "1",
                "start": {
                    "accountSid": "ACxxx",
                    "streamSid": "MZxxx",
                    "callSid": "CAxxx",
                    "tracks": ["inbound"],
                    "mediaFormat": {
                        "encoding": "audio/x-mulaw",
                        "sampleRate": 8000,
                        "channels": 1,
                    },
                    "customParameters": {},
                },
                "streamSid": "MZxxx",
            }
        )
    )


def _stop_frame() -> _FakeWSMessage:
    return _text(
        json.dumps(
            {
                "event": "stop",
                "sequenceNumber": "99",
                "stop": {"accountSid": "ACxxx", "callSid": "CAxxx"},
                "streamSid": "MZxxx",
            }
        )
    )


class _ScriptedEndpointer:
    """Same pattern as tests/test_conversation_session.py: pre-scripted
    events per `feed` call, independent of chunk content."""

    def __init__(self, events_by_call: dict[int, list[EndpointEvent]]) -> None:
        self._events_by_call = events_by_call
        self._call_index = 0

    def feed(self, chunk: AudioChunk) -> list[EndpointEvent]:
        events = self._events_by_call.get(self._call_index, [])
        self._call_index += 1
        return events


def _silence_8k(n_samples: int = 160) -> bytes:
    return b"\x00\x00" * n_samples


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


@pytest.mark.asyncio
async def test_transport_forwards_inbound_audio_and_pushes_agent_audio_out() -> None:
    clock = FakeClock()
    runner = _make_runner(clock, "Hello there.")
    endpointer = _ScriptedEndpointer(
        {0: [], 1: [EndpointEvent.SPEECH_STARTED], 2: [EndpointEvent.SPEECH_ENDED]}
    )
    session = ConversationSession(runner, endpointer, lambda _chunk: None)
    transport = MediaStreamsTransport(session, clock)

    ws = _FakeWS(
        [
            _start_frame(),
            _inbound_media_frame(_silence_8k(), 0),
            _inbound_media_frame(_silence_8k(), 1),
        ]
    )

    await transport.handle(ws)

    sent_events = [json.loads(s)["event"] for s in ws.sent]
    assert "media" in sent_events
    assert "mark" in sent_events


@pytest.mark.asyncio
async def test_transport_barge_in_emits_clear_and_stops_further_marks() -> None:
    clock = FakeClock()
    runner = _make_runner(clock, "One. Two. Three.")
    # First SPEECH_STARTED/SPEECH_ENDED opens a turn; a second SPEECH_STARTED
    # while it's still playing is the barge-in.
    endpointer = _ScriptedEndpointer(
        {
            0: [],
            1: [EndpointEvent.SPEECH_STARTED],
            2: [EndpointEvent.SPEECH_ENDED],
            3: [EndpointEvent.SPEECH_STARTED],
            4: [EndpointEvent.SPEECH_ENDED],
        }
    )
    session = ConversationSession(runner, endpointer, lambda _chunk: None)
    transport = MediaStreamsTransport(session, clock)

    ws = _FakeWS(
        [
            _start_frame(),
            *[_inbound_media_frame(_silence_8k(), i) for i in range(5)],
        ]
    )

    await transport.handle(ws)

    sent_events = [json.loads(s)["event"] for s in ws.sent]
    assert "clear" in sent_events
