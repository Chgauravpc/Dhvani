"""Real WebRTC round-trip, entirely in-process: two `RTCPeerConnection`s
(one standing in for "the browser") negotiated over a direct SDP exchange,
no network signaling needed. This is the strongest verification available
without a real browser + microphone (phase-1 spec section 7's "milestone
verification" is manual for that reason) -- it proves the actual encode/
decode/resample path works, not just that the code type-checks.
"""

from __future__ import annotations

import asyncio

import numpy as np
import pytest
from aiortc import RTCPeerConnection
from aiortc.mediastreams import MediaStreamTrack

from dhvani.transport.webrtc import TTSAudioTrack, receive_audio
from dhvani.types import AudioChunk

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _negotiate(pc1: RTCPeerConnection, pc2: RTCPeerConnection) -> None:
    offer = await pc1.createOffer()
    await pc1.setLocalDescription(offer)
    await pc2.setRemoteDescription(pc1.localDescription)
    answer = await pc2.createAnswer()
    await pc2.setLocalDescription(answer)
    await pc1.setRemoteDescription(pc2.localDescription)


async def test_outbound_track_survives_encode_decode_round_trip() -> None:
    """Our TTSAudioTrack -> Opus encode -> Opus decode -> a real received
    frame on the other side, with recognizable (non-silent) audio."""
    pc1 = RTCPeerConnection()
    pc2 = RTCPeerConnection()
    track_started = asyncio.Event()

    tts_track = TTSAudioTrack(sample_rate=22050)
    pc1.addTrack(tts_track)

    received: list[AudioChunk] = []

    def total_bytes() -> int:
        return sum(len(c.pcm) for c in received)

    # 300ms of 16kHz mono s16 audio -- enough to prove real, sustained
    # signal is flowing, however the resampler happens to batch its output.
    target_bytes = int(0.3 * 16000 * 2)

    @pc2.on("track")
    def on_track(track: MediaStreamTrack) -> None:
        async def consume() -> None:
            track_started.set()
            async for chunk in receive_audio(track):
                received.append(chunk)
                if total_bytes() >= target_bytes:
                    return

        asyncio.ensure_future(consume())

    try:
        await _negotiate(pc1, pc2)
        await asyncio.wait_for(track_started.wait(), timeout=10)

        # Push a real tone (not silence) so we can assert signal arrived.
        samples = (np.sin(2 * np.pi * 440 * np.arange(22050) / 22050) * 10000).astype(np.int16)
        tts_track.push(AudioChunk(pcm=samples.tobytes(), sample_rate=22050, seq=0))

        # ICE/DTLS negotiation on this machine takes a few real seconds even
        # for a loopback connection with no STUN server configured; give it
        # generous room rather than chase that further here.
        for _ in range(150):
            if total_bytes() >= target_bytes:
                break
            await asyncio.sleep(0.1)

        assert total_bytes() >= target_bytes
        assert all(c.sample_rate == 16000 for c in received)
        peak = max(int(np.abs(np.frombuffer(c.pcm, dtype=np.int16)).max()) for c in received)
        assert peak > 500, f"expected real signal, got peak amplitude {peak}"
    finally:
        await pc1.close()
        await pc2.close()
