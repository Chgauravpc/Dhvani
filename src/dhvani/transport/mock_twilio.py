"""A server that speaks the Twilio Media Streams protocol well enough to
test against with no Twilio account (phase-3 spec section 7.5): sends
`connected`/`start`, replays PCM as `media` frames at 20ms cadence, and
records every message the code under test sends back so a test can assert
on it -- outbound `media` payloads, `mark` names, and `clear` calls.

Not a Twilio emulator in general -- no DTMF injection, no multi-track mixing.
Just enough of the wire protocol for `MediaStreamsTransport` (7.4) to be
exercised over a real localhost WebSocket instead of mocked in-process.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from dataclasses import dataclass, field

from aiohttp import web

from dhvani.audio import mulaw
from dhvani.clock import Clock
from dhvani.transport.mediastreams import (
    ClearMessage,
    MarkMessage,
    MediaMessage,
    MediaStreamsProtocolError,
    StopMessage,
    parse_inbound,
)

FRAME_MS = 20.0
SAMPLES_PER_FRAME = 160  # 20ms @ 8kHz


def _connected_message() -> str:
    return json.dumps({"event": "connected", "protocol": "Call", "version": "1.0.0"})


def _start_message(stream_sid: str, account_sid: str, call_sid: str) -> str:
    return json.dumps(
        {
            "event": "start",
            "sequenceNumber": "1",
            "start": {
                "accountSid": account_sid,
                "streamSid": stream_sid,
                "callSid": call_sid,
                "tracks": ["inbound"],
                "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
                "customParameters": {},
            },
            "streamSid": stream_sid,
        }
    )


def _stop_message(stream_sid: str, account_sid: str, call_sid: str) -> str:
    return json.dumps(
        {
            "event": "stop",
            "sequenceNumber": "last",
            "stop": {"accountSid": account_sid, "callSid": call_sid},
            "streamSid": stream_sid,
        }
    )


def _inbound_media_message(stream_sid: str, ulaw: bytes, chunk: int) -> str:
    return json.dumps(
        {
            "event": "media",
            "sequenceNumber": str(chunk + 2),
            "media": {
                "track": "inbound",
                "chunk": str(chunk),
                "timestamp": str(chunk * int(FRAME_MS)),
                "payload": base64.b64encode(ulaw).decode("ascii"),
            },
            "streamSid": stream_sid,
        }
    )


@dataclass
class MockTwilioServer:
    """Plays Twilio's side of the Media Streams protocol against whatever
    connects to `handle`.

    `source_pcm` is 16-bit mono PCM at `source_rate_hz`; it is mu-law
    encoded at construction (real Twilio audio arrives already encoded, so
    the replay path doesn't need a resampler -- pass 8kHz PCM to keep the
    fixture simple, or any rate and it will alias, which is fine for a
    protocol test that isn't measuring WER).
    """

    source_pcm: bytes
    clock: Clock
    stream_sid: str = "MZtest00000000000000000000000000"
    account_sid: str = "ACtest00000000000000000000000000"
    call_sid: str = "CAtest00000000000000000000000000"

    received_media_ulaw: list[bytes] = field(default_factory=list, init=False)
    received_marks: list[str] = field(default_factory=list, init=False)
    clear_count: int = field(default=0, init=False)
    stopped_by_peer: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._ulaw = mulaw.encode(self.source_pcm)

    async def handle(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        await ws.send_str(_connected_message())
        await ws.send_str(_start_message(self.stream_sid, self.account_sid, self.call_sid))

        sender_task = asyncio.ensure_future(self._send_frames(ws))
        try:
            async for ws_message in ws:
                if ws_message.type != web.WSMsgType.TEXT:
                    continue
                try:
                    message = parse_inbound(ws_message.data)
                except MediaStreamsProtocolError:
                    continue
                if isinstance(message, MediaMessage):
                    self.received_media_ulaw.append(message.payload)
                elif isinstance(message, MarkMessage):
                    self.received_marks.append(message.name)
                elif isinstance(message, ClearMessage):
                    self.clear_count += 1
                elif isinstance(message, StopMessage):
                    self.stopped_by_peer = True
                    return ws
        finally:
            sender_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sender_task
        return ws

    async def _send_frames(self, ws: web.WebSocketResponse) -> None:
        frame_bytes = SAMPLES_PER_FRAME  # mu-law: one byte per sample
        for chunk_index in range(0, len(self._ulaw), frame_bytes):
            await self.clock.sleep(FRAME_MS / 1000.0)
            frame = self._ulaw[chunk_index : chunk_index + frame_bytes]
            await ws.send_str(
                _inbound_media_message(self.stream_sid, frame, chunk_index // frame_bytes)
            )
        await ws.send_str(_stop_message(self.stream_sid, self.account_sid, self.call_sid))
