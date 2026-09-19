"""`python -m dhvani.live` -- the live WebRTC voice agent.

Requires `GROQ_API_KEY`, either exported directly or via a local `.env`
file (see `config.load_dotenv`) that `.gitignore` keeps out of version
control. Downloads faster-whisper's model and the pinned Piper voice on
first run if not already cached (see `docs/specs/phase-1.md`). Then open
http://localhost:8080/ in a browser, grant microphone access, and talk.

This is the one part of Phase 1 that needs manual verification: a real
browser and microphone, which this environment doesn't have (phase-1 spec
section 7's milestone verification is manual for that reason). Everything
this wires together -- the overlapped runner, barge-in, the WebRTC audio
path -- is unit- or integration-tested elsewhere against mocks or a
Python-only loopback; this module is the assembly, not new logic.
"""

from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import web
from aiortc import RTCPeerConnection
from aiortc.mediastreams import MediaStreamTrack

from dhvani.clock import RealClock
from dhvani.config import LatencyBudget, load_dotenv
from dhvani.pipeline.overlapped import OverlappedRunner
from dhvani.pipeline.session import ConversationSession
from dhvani.providers.groq_llm import GroqLLM
from dhvani.providers.piper_tts import DEFAULT_VOICE, PiperTTS, ensure_voice_downloaded
from dhvani.providers.whisper_stt import WhisperSTT
from dhvani.transport.signaling import create_app
from dhvani.transport.webrtc import TTSAudioTrack, receive_audio
from dhvani.vad.endpointer import Endpointer
from dhvani.vad.silero import SileroVad

logger = logging.getLogger("dhvani.live")

WHISPER_MODEL_SIZE = "small"


async def _on_peer_connected(pc: RTCPeerConnection) -> None:
    clock = RealClock()
    stt = WhisperSTT(WHISPER_MODEL_SIZE, clock)
    llm = GroqLLM(clock)
    model_path, config_path = ensure_voice_downloaded(DEFAULT_VOICE)
    tts = PiperTTS(model_path, clock, voice_config_path=config_path)
    runner = OverlappedRunner(stt, llm, tts, clock, LatencyBudget())

    endpointer = Endpointer(SileroVad())
    outbound = TTSAudioTrack(sample_rate=tts.sample_rate)
    pc.addTrack(outbound)

    @pc.on("track")
    def on_track(track: MediaStreamTrack) -> None:
        if track.kind != "audio":
            return
        session = ConversationSession(runner, endpointer, outbound.push)
        asyncio.ensure_future(session.run(receive_audio(track)))
        logger.info("peer connected, conversation session started")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    load_dotenv()
    if not os.environ.get("GROQ_API_KEY"):
        raise SystemExit(
            "GROQ_API_KEY is not set. Get a free key at https://console.groq.com "
            "and export it before running the live demo."
        )

    app = create_app(_on_peer_connected)
    web.run_app(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
