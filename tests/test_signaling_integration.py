"""Real HTTP signaling round trip against a running aiohttp server, using a
second real RTCPeerConnection as the "browser" -- same rationale as the
webrtc loopback test: the strongest verification available without an
actual browser + microphone (phase-1 spec section 7).

Uses a lightweight echo-tone `on_peer_connected` here rather than the full
real-provider pipeline in `dhvani.live`, so this stays fast and only tests
the signaling layer itself (the pipeline is already covered elsewhere).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest
from aiohttp.test_utils import TestClient, TestServer
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamTrack

from dhvani.transport.signaling import create_app
from dhvani.transport.webrtc import TTSAudioTrack, receive_audio
from dhvani.types import AudioChunk

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.real_time_loop]


async def test_offer_endpoint_completes_a_real_webrtc_negotiation(tmp_path: Path) -> None:
    track_started = asyncio.Event()

    async def on_peer_connected(pc: RTCPeerConnection) -> None:
        outbound = TTSAudioTrack(sample_rate=22050)
        pc.addTrack(outbound)
        outbound.push(
            AudioChunk(
                pcm=(np.ones(22050, dtype=np.int16) * 10000).tobytes(),
                sample_rate=22050,
                seq=0,
            )
        )

    web_dir = tmp_path
    (web_dir / "index.html").write_text("<html><body>ok</body></html>")

    app = create_app(on_peer_connected, web_dir=web_dir)
    browser_pc = RTCPeerConnection()
    received: list[AudioChunk] = []

    @browser_pc.on("track")
    def on_track(track: MediaStreamTrack) -> None:
        async def consume() -> None:
            track_started.set()
            async for chunk in receive_audio(track):
                received.append(chunk)
                if sum(len(c.pcm) for c in received) >= 3200:  # 100ms @ 16kHz
                    return

        asyncio.ensure_future(consume())

    try:
        async with TestClient(TestServer(app)) as client:
            index_resp = await client.get("/")
            assert index_resp.status == 200
            assert "ok" in await index_resp.text()

            browser_pc.addTransceiver("audio", direction="recvonly")
            offer = await browser_pc.createOffer()
            await browser_pc.setLocalDescription(offer)

            resp = await client.post(
                "/offer",
                json={
                    "sdp": browser_pc.localDescription.sdp,
                    "type": browser_pc.localDescription.type,
                },
            )
            assert resp.status == 200
            answer = await resp.json()
            assert answer["type"] == "answer"

            await browser_pc.setRemoteDescription(
                RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
            )

            await asyncio.wait_for(track_started.wait(), timeout=15)
            for _ in range(150):
                if sum(len(c.pcm) for c in received) >= 3200:
                    break
                await asyncio.sleep(0.1)

            assert sum(len(c.pcm) for c in received) >= 3200
            peak = max(int(np.abs(np.frombuffer(c.pcm, dtype=np.int16)).max()) for c in received)
            assert peak > 500
    finally:
        await browser_pc.close()
