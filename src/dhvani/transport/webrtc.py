"""aiortc peer connection glue: inbound browser audio -> 16kHz mono
AudioChunks, and an outbound track that plays back the agent's AudioChunks.

Frame-format notes, verified against the installed `aiortc==1.15.0` source
(`aiortc/codecs/opus.py`), not assumed: `OpusEncoder` carries its own
internal `AudioResampler`, so the outbound track only needs to hand it some
valid `AudioFrame` (any sample rate/layout, correct `pts`/`time_base`) --
no manual resampling to 48kHz/stereo is needed on the way out. `OpusDecoder`,
however, always decodes to s16/stereo/48000, so inbound frames are resampled
down to 16kHz mono here explicitly, using the same real-time pacing pattern
as aiortc's own built-in `AudioStreamTrack` (`aiortc/mediastreams.py`).
"""

from __future__ import annotations

import asyncio
import fractions
from collections.abc import AsyncIterator

from aiortc import MediaStreamTrack
from aiortc.mediastreams import AUDIO_PTIME
from av import AudioFrame
from av.audio.resampler import AudioResampler

from dhvani.types import AudioChunk

INBOUND_SAMPLE_RATE = 16000


class InboundResampler:
    """Converts aiortc's decoded audio frames into 16kHz mono `AudioChunk`s."""

    def __init__(self) -> None:
        self._resampler = AudioResampler(format="s16", layout="mono", rate=INBOUND_SAMPLE_RATE)
        self._seq = 0

    def resample(self, frame: AudioFrame) -> list[AudioChunk]:
        chunks = []
        for out_frame in self._resampler.resample(frame):
            pcm = bytes(out_frame.planes[0])
            chunks.append(AudioChunk(pcm=pcm, sample_rate=INBOUND_SAMPLE_RATE, seq=self._seq))
            self._seq += 1
        return chunks


async def receive_audio(track: MediaStreamTrack) -> AsyncIterator[AudioChunk]:
    """Reads an inbound aiortc audio track, yielding 16kHz mono `AudioChunk`s
    until the track ends."""
    resampler = InboundResampler()
    while True:
        try:
            frame = await track.recv()
        except Exception:  # noqa: BLE001 -- aiortc signals track end via MediaStreamError
            return
        if not isinstance(frame, AudioFrame):
            continue
        for chunk in resampler.resample(frame):
            yield chunk


class TTSAudioTrack(MediaStreamTrack):
    """Outbound track that plays back `AudioChunk`s pushed via `push()`.

    Lives for the whole session, not one turn: when nothing has been pushed,
    `recv()` emits silence rather than blocking or ending, so the RTP stream
    stays continuous between turns.
    """

    kind = "audio"

    def __init__(self, sample_rate: int) -> None:
        super().__init__()
        self._sample_rate = sample_rate
        self._queue: asyncio.Queue[AudioChunk] = asyncio.Queue()
        self._buffer = b""
        self._timestamp = 0
        self._start: float | None = None
        self._samples_per_frame = int(AUDIO_PTIME * sample_rate)
        self._frame_bytes = self._samples_per_frame * 2  # 16-bit samples

    def push(self, chunk: AudioChunk) -> None:
        self._queue.put_nowait(chunk)

    async def recv(self) -> AudioFrame:
        while len(self._buffer) < self._frame_bytes:
            try:
                chunk = await asyncio.wait_for(self._queue.get(), timeout=AUDIO_PTIME)
                self._buffer += chunk.pcm
            except TimeoutError:
                # Nothing to say right now -- pad with silence instead of
                # stalling the RTP stream.
                self._buffer += b"\x00" * (self._frame_bytes - len(self._buffer))

        frame_bytes, self._buffer = (
            self._buffer[: self._frame_bytes],
            self._buffer[self._frame_bytes :],
        )

        frame = AudioFrame(format="s16", layout="mono", samples=self._samples_per_frame)
        frame.planes[0].update(frame_bytes)
        frame.sample_rate = self._sample_rate
        frame.time_base = fractions.Fraction(1, self._sample_rate)
        frame.pts = self._timestamp
        self._timestamp += self._samples_per_frame

        loop = asyncio.get_event_loop()
        if self._start is None:
            self._start = loop.time()
        else:
            wait = self._start + (self._timestamp / self._sample_rate) - loop.time()
            if wait > 0:
                await asyncio.sleep(wait)

        return frame
