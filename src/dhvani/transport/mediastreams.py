"""Twilio Media Streams protocol: pure message parse/serialize functions,
plus a thin aiohttp binding over `ConversationSession` -- split the way
`vad/endpointer.py` is split, for the same reason (pure logic stays
unit-testable without a socket).

**Verified against Twilio's own published reference**
(https://www.twilio.com/docs/voice/media-streams/websocket-messages), not
assumed, per phase-3 spec section 5's rule to verify every provider/platform
API before coding against it. The message shapes below are quoted directly
from that page:

- `connected`: `{"event": "connected", "protocol": "Call", "version": "1.0.0"}`
- `start`: `{"event": "start", "sequenceNumber": "1", "start": {"accountSid":
  ..., "streamSid": ..., "callSid": ..., "tracks": ["inbound"], "mediaFormat":
  {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
  "customParameters": {...}}, "streamSid": ...}`
- `media` (inbound, from Twilio): `{"event": "media", "sequenceNumber": ...,
  "media": {"track": "inbound", "chunk": ..., "timestamp": ..., "payload":
  <base64 mu-law>}, "streamSid": ...}`
- `stop`: `{"event": "stop", "sequenceNumber": ..., "stop": {"accountSid":
  ..., "callSid": ...}, "streamSid": ...}`
- `dtmf`: `{"event": "dtmf", "streamSid": ..., "sequenceNumber": ...,
  "dtmf": {"track": "inbound_track", "digit": "1"}}`
- `mark` (inbound -- Twilio echoes a mark back once that audio finishes
  playing, bidirectional streaming only): `{"event": "mark", "sequenceNumber":
  ..., "streamSid": ..., "mark": {"name": ...}}`
- Outbound `media`: `{"event": "media", "streamSid": ..., "media":
  {"payload": <base64 mu-law>}}` -- no `track`/`chunk`/`timestamp`, unlike
  the inbound shape with the same event name.
- Outbound `mark`: `{"event": "mark", "streamSid": ..., "mark": {"name": ...}}`
- Outbound `clear`: `{"event": "clear", "streamSid": ...}` -- Twilio never
  sends this to a server; it exists only in the outbound direction, to flush
  Twilio's own playback buffer for barge-in.

One finding worth flagging: `media`'s inbound and outbound shapes share an
event name but differ in fields (inbound carries `track`/`chunk`/`timestamp`,
outbound doesn't), and the same is true in reverse for `mark` versus the
Twilio-echoed `mark` (the echo adds `sequenceNumber`, harmless since it's
never read here). `MediaMessage` below models the union of both shapes with
optional fields, so one parser handles whichever direction's frame it is
handed -- convenient for `mock_twilio.py` (section 7.5), which has to
interpret the *outbound* messages the code under test sends to it, using the
same parser real code uses for Twilio's *inbound* messages.
"""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from aiohttp import WSMsgType

from dhvani.audio import mulaw
from dhvani.audio.resample import Resampler, resample
from dhvani.clock import Clock
from dhvani.types import AudioChunk

if TYPE_CHECKING:
    from typing import Protocol

    from dhvani.pipeline.session import ConversationSession

    class _WSMessageLike(Protocol):
        type: WSMsgType
        data: str

    class _WebSocketLike(Protocol):
        """What `MediaStreamsTransport` needs from a WebSocket -- satisfied
        structurally by both `aiohttp.web.WebSocketResponse` (the real
        server-side connection Twilio opens against us) and
        `aiohttp.ClientWebSocketResponse` (what a test client connects
        with, e.g. against `mock_twilio.MockTwilioServer`). Declared as a
        Protocol rather than hard-coding the server type so a test can
        drive this class from either side of a real socket."""

        async def send_str(self, data: str) -> None: ...
        def __aiter__(self) -> AsyncIterator[_WSMessageLike]: ...


TWILIO_SAMPLE_RATE_HZ = 8000
"""Twilio Media Streams audio is always mu-law at 8kHz mono -- fixed by the
protocol, not negotiated."""

PIPELINE_SAMPLE_RATE_HZ = 16000
"""What the rest of the pipeline expects inbound audio at (matches
`WhisperSTT.EXPECTED_SAMPLE_RATE` and `Endpointer`'s default `sample_rate`).
Not imported from either -- `transport` stays independent of `providers`."""


class MediaStreamsEvent(StrEnum):
    CONNECTED = "connected"
    START = "start"
    MEDIA = "media"
    STOP = "stop"
    MARK = "mark"
    DTMF = "dtmf"
    CLEAR = "clear"


class MediaStreamsProtocolError(Exception):
    """Raised by `parse_inbound` on a message that doesn't match the
    published protocol shape."""


@dataclass(frozen=True, slots=True)
class MediaFormat:
    encoding: str
    sample_rate_hz: int
    channels: int


@dataclass(frozen=True, slots=True)
class ConnectedMessage:
    protocol: str
    version: str


@dataclass(frozen=True, slots=True)
class StartMessage:
    stream_sid: str
    account_sid: str
    call_sid: str
    tracks: tuple[str, ...]
    media_format: MediaFormat
    custom_parameters: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class MediaMessage:
    """A `media` frame, either direction -- see the module docstring for why
    `track`/`chunk`/`timestamp_ms` are optional: Twilio's inbound frames
    carry them, a server's own outbound frames don't."""

    stream_sid: str
    payload: bytes
    """Base64-decoded, still mu-law encoded, 8kHz mono -- not yet PCM."""
    track: str | None = None
    chunk: str | None = None
    timestamp_ms: str | None = None


@dataclass(frozen=True, slots=True)
class StopMessage:
    stream_sid: str
    account_sid: str
    call_sid: str


@dataclass(frozen=True, slots=True)
class MarkMessage:
    stream_sid: str
    name: str


@dataclass(frozen=True, slots=True)
class DtmfMessage:
    stream_sid: str
    track: str
    digit: str


@dataclass(frozen=True, slots=True)
class ClearMessage:
    stream_sid: str


InboundMessage = (
    ConnectedMessage
    | StartMessage
    | MediaMessage
    | StopMessage
    | MarkMessage
    | DtmfMessage
    | ClearMessage
)


def parse_inbound(raw: str) -> InboundMessage:
    """Parse one WebSocket text frame into a typed message. Pure, no I/O.

    Raises `MediaStreamsProtocolError` on invalid JSON, an unrecognized
    `event`, or a recognized event missing a field the published shape
    requires.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MediaStreamsProtocolError(f"not valid JSON: {exc}") from exc

    event = data.get("event")
    try:
        if event == MediaStreamsEvent.CONNECTED:
            return ConnectedMessage(protocol=data["protocol"], version=data["version"])
        if event == MediaStreamsEvent.START:
            start = data["start"]
            fmt = start["mediaFormat"]
            return StartMessage(
                stream_sid=start["streamSid"],
                account_sid=start["accountSid"],
                call_sid=start["callSid"],
                tracks=tuple(start["tracks"]),
                media_format=MediaFormat(
                    encoding=fmt["encoding"],
                    sample_rate_hz=fmt["sampleRate"],
                    channels=fmt["channels"],
                ),
                custom_parameters=dict(start.get("customParameters", {})),
            )
        if event == MediaStreamsEvent.MEDIA:
            media = data["media"]
            return MediaMessage(
                stream_sid=data["streamSid"],
                payload=base64.b64decode(media["payload"]),
                track=media.get("track"),
                chunk=media.get("chunk"),
                timestamp_ms=media.get("timestamp"),
            )
        if event == MediaStreamsEvent.STOP:
            stop = data["stop"]
            return StopMessage(
                stream_sid=data["streamSid"],
                account_sid=stop["accountSid"],
                call_sid=stop["callSid"],
            )
        if event == MediaStreamsEvent.MARK:
            return MarkMessage(stream_sid=data["streamSid"], name=data["mark"]["name"])
        if event == MediaStreamsEvent.DTMF:
            dtmf = data["dtmf"]
            return DtmfMessage(
                stream_sid=data["streamSid"], track=dtmf["track"], digit=dtmf["digit"]
            )
        if event == MediaStreamsEvent.CLEAR:
            return ClearMessage(stream_sid=data["streamSid"])
    except KeyError as exc:
        raise MediaStreamsProtocolError(f"message missing required field {exc}") from exc

    raise MediaStreamsProtocolError(f"unrecognized event type: {event!r}")


def _media_json(stream_sid: str, ulaw_payload_b64: str) -> str:
    return json.dumps(
        {"event": "media", "streamSid": stream_sid, "media": {"payload": ulaw_payload_b64}}
    )


def media_message(stream_sid: str, pcm: bytes, src_rate_hz: int) -> str:
    """Build one outbound `media` message: `pcm` (at `src_rate_hz`)
    resampled to 8kHz and mu-law encoded, base64, per the published outbound
    shape. Pure, no I/O -- one-shot, with no resampler state carried to the
    next call.

    That statelessness is fine for a single self-contained buffer (a test
    fixture, a short prompt) but wrong for a live stream of many small TTS
    chunks: calling this function once per chunk restarts `Resampler`
    interpolation every time, reintroducing the exact frame-boundary
    discontinuity `audio.resample.Resampler` exists to avoid.
    `MediaStreamsTransport` does not use this function on its outbound hot
    path for that reason -- it holds one persistent `Resampler` across a
    call's chunks instead. This function stays for one-shot use and as the
    pure, directly-testable reference for the outbound shape.
    """
    narrowband = resample(pcm, src_rate_hz, TWILIO_SAMPLE_RATE_HZ)
    ulaw = mulaw.encode(narrowband)
    return _media_json(stream_sid, base64.b64encode(ulaw).decode("ascii"))


def mark_message(stream_sid: str, name: str) -> str:
    """Build one outbound `mark` message."""
    return json.dumps({"event": "mark", "streamSid": stream_sid, "mark": {"name": name}})


def clear_message(stream_sid: str) -> str:
    """Build the outbound `clear` message that flushes Twilio's playback
    buffer -- how barge-in is implemented over this transport (spec section
    7.4: `clear`, not local cancellation)."""
    return json.dumps({"event": "clear", "streamSid": stream_sid})


class MediaStreamsTransport:
    """Thin aiohttp binding: drives one `ConversationSession` over one
    Twilio Media Streams WebSocket connection.

    Construct a fresh `ConversationSession` (and a fresh
    `MediaStreamsTransport` wrapping it) per call, the same way
    `transport.signaling.create_app`'s `on_peer_connected` builds fresh
    session state per browser connection -- one Media Streams WebSocket is
    one phone call.

    Reassigns `session`'s `_audio_sink` and `_on_barge_in` for the lifetime
    of this connection (see `pipeline.session.ConversationSession`'s
    docstring for why `on_barge_in` exists): both are ordinary instance
    attributes and this reassignment is scoped entirely to `handle()`, which
    owns the only reference to `ws`. Wiring them at construction time isn't
    possible -- the session has to exist before there is a WebSocket to
    send `clear`/`media`/`mark` frames on.
    """

    def __init__(self, session: ConversationSession, clock: Clock) -> None:
        self._session = session
        self._clock = clock
        self._outbound_resampler: Resampler | None = None

    async def handle(self, ws: _WebSocketLike) -> None:
        stream_sid_holder: dict[str, str] = {}
        outstanding_marks: list[str] = []
        mark_seq = 0
        pending_sends: set[asyncio.Task[None]] = set()

        def send(payload: str) -> None:
            task = asyncio.ensure_future(ws.send_str(payload))
            pending_sends.add(task)
            task.add_done_callback(pending_sends.discard)

        def audio_sink(chunk: AudioChunk) -> None:
            nonlocal mark_seq
            stream_sid = stream_sid_holder.get("sid")
            if stream_sid is None:
                return  # no `start` yet -- nothing to address the frame to

            if (
                self._outbound_resampler is None
                or self._outbound_resampler.src_rate_hz != chunk.sample_rate
            ):
                self._outbound_resampler = Resampler(chunk.sample_rate, TWILIO_SAMPLE_RATE_HZ)
            narrowband = self._outbound_resampler.process(chunk.pcm)
            ulaw = mulaw.encode(narrowband)
            send(_media_json(stream_sid, base64.b64encode(ulaw).decode("ascii")))

            mark_name = f"turn-{mark_seq}"
            mark_seq += 1
            outstanding_marks.append(mark_name)
            send(mark_message(stream_sid, mark_name))

        def on_barge_in() -> None:
            stream_sid = stream_sid_holder.get("sid")
            if stream_sid is not None:
                send(clear_message(stream_sid))
            outstanding_marks.clear()
            if self._outbound_resampler is not None:
                self._outbound_resampler.reset()

        self._session._audio_sink = audio_sink  # noqa: SLF001 -- see class docstring
        self._session._on_barge_in = on_barge_in  # noqa: SLF001

        try:
            await self._session.run(self._inbound_audio(ws, stream_sid_holder, outstanding_marks))
        finally:
            if pending_sends:
                await asyncio.gather(*pending_sends, return_exceptions=True)

    @staticmethod
    async def _inbound_audio(
        ws: _WebSocketLike,
        stream_sid_holder: dict[str, str],
        outstanding_marks: list[str],
    ) -> AsyncIterator[AudioChunk]:
        """The one reader of `ws`: yields `AudioChunk`s for genuine `media`
        frames and handles every other inbound event as a side effect,
        since aiohttp's WebSocket iterator can only be consumed once."""
        inbound_resampler = Resampler(TWILIO_SAMPLE_RATE_HZ, PIPELINE_SAMPLE_RATE_HZ)
        seq = 0
        async for ws_message in ws:
            if ws_message.type != WSMsgType.TEXT:
                continue
            try:
                message = parse_inbound(ws_message.data)
            except MediaStreamsProtocolError:
                continue  # malformed frame -- skip it rather than drop the call

            if isinstance(message, StartMessage):
                stream_sid_holder["sid"] = message.stream_sid
            elif isinstance(message, MediaMessage):
                if message.track not in (None, "inbound"):
                    continue  # ignore Twilio's own echo of our outbound track
                pcm_8k = mulaw.decode(message.payload)
                pcm_wide = inbound_resampler.process(pcm_8k)
                if pcm_wide:
                    yield AudioChunk(pcm=pcm_wide, sample_rate=PIPELINE_SAMPLE_RATE_HZ, seq=seq)
                    seq += 1
            elif isinstance(message, MarkMessage):
                if message.name in outstanding_marks:
                    outstanding_marks.remove(message.name)
            elif isinstance(message, StopMessage):
                return
            # ConnectedMessage / DtmfMessage / ClearMessage: nothing to do.
