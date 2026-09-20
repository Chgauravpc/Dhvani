"""Decode an on-disk audio file into 16kHz mono `AudioChunk`s for eval.

Not in the phase-2 spec's original file layout -- added because a real
downloaded VoiceAgentBench audio file turned out to need it: its manifest
names it `1_audio.wav`, but its actual bytes are an MP3 stream (`ID3` tag,
`Lavf60.16.100` encoder signature, confirmed by reading the file, not the
extension). `av` (PyAV) is already a transitive dependency via `aiortc`
and already used for exactly this kind of resampling in
`transport/webrtc.py`'s `InboundResampler` -- this reuses that pattern for
a file instead of a live track, rather than adding a new audio dependency.
"""

from __future__ import annotations

import dataclasses
import io
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import BinaryIO

import av
from av.audio.resampler import AudioResampler

from dhvani.types import AudioChunk

TARGET_SAMPLE_RATE = 16000
"""Matches `dhvani.providers.whisper_stt.EXPECTED_SAMPLE_RATE`."""


def _decode(source: str | BinaryIO, target_sample_rate: int) -> list[AudioChunk]:
    container = av.open(source, mode="r")
    try:
        stream = container.streams.audio[0]
        resampler = AudioResampler(format="s16", layout="mono", rate=target_sample_rate)
        chunks: list[AudioChunk] = []
        for frame in container.decode(stream):
            for out_frame in resampler.resample(frame):
                pcm = bytes(out_frame.planes[0])
                if pcm:
                    chunks.append(
                        AudioChunk(pcm=pcm, sample_rate=target_sample_rate, seq=len(chunks))
                    )
    finally:
        container.close()

    if chunks:
        chunks[-1] = dataclasses.replace(chunks[-1], is_last=True)
    return chunks


def decode_audio_file_to_chunks(
    path: Path, target_sample_rate: int = TARGET_SAMPLE_RATE
) -> list[AudioChunk]:
    """Decode any container/codec PyAV supports to mono 16-bit PCM chunks
    at `target_sample_rate`, regardless of the file's extension or its
    original sample rate/channel count."""
    return _decode(str(path), target_sample_rate)


def decode_audio_bytes_to_chunks(
    data: bytes, target_sample_rate: int = TARGET_SAMPLE_RATE
) -> list[AudioChunk]:
    """Same as `decode_audio_file_to_chunks`, for audio held in memory --
    e.g. a Hugging Face `Audio()` feature's embedded bytes (Svarah,
    LAHAJA), which arrive already-decoded-from-parquet but still
    container/codec-encoded (typically WAV or FLAC)."""
    return _decode(io.BytesIO(data), target_sample_rate)


async def iter_chunks(chunks: Sequence[AudioChunk]) -> AsyncIterator[AudioChunk]:
    """Wraps an in-memory chunk list as the `AsyncIterator[AudioChunk]`
    every `STTProvider.stream` expects -- eval code decodes a whole file
    up front rather than genuinely streaming it."""
    for chunk in chunks:
        yield chunk
