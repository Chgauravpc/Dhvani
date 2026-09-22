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

Since phase 2, STT output also passes through `CorrectedSTT` (F2's
`dhvani-entity` post-ASR corrector) before reaching the LLM -- a drop-in
`STTProvider` wrap, so this is still assembly, not new logic here either.
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
from dhvani.entity.corrector import EntityCorrector
from dhvani.entity.lexicon import DEFAULT_LEXICON
from dhvani.pipeline.overlapped import OverlappedRunner
from dhvani.pipeline.session import ConversationSession
from dhvani.providers.corrected_stt import CorrectedSTT
from dhvani.providers.groq_llm import GroqLLM
from dhvani.providers.piper_tts import DEFAULT_VOICE, PiperTTS, ensure_voice_downloaded
from dhvani.providers.whisper_stt import WhisperSTT
from dhvani.transport.signaling import OnPeerConnected, create_app
from dhvani.transport.webrtc import TTSAudioTrack, receive_audio
from dhvani.vad.endpointer import Endpointer
from dhvani.vad.silero import SileroVad

logger = logging.getLogger("dhvani.live")

WHISPER_MODEL_SIZE = os.environ.get("DHVANI_WHISPER_MODEL", "tiny")
"""Live-demo operating point, decided in phase-3 spec section 2.3: this
used to default to "small" on the reasoning that transcription quality is
the project's whole point. Phase 2B's real model sweep against Svarah
(`phase-2b.md` section 12) put a number on what that cost: `small`/`int8`
measured at p50=7.46s STT latency, roughly 9x Phase 0's own 200ms STT
stage budget, before LLM/TTS latency is even added -- not a viable choice
for a live conversational demo where a caller is waiting on the line.
`tiny`/`float32` (below) measured at p50=1.55s, WER 27.9% vs. `small`'s
14.6% -- a real accuracy cost, accepted here for latency a caller can
actually sit through. Override with DHVANI_WHISPER_MODEL for a different
tradeoff."""

WHISPER_COMPUTE_TYPE = os.environ.get("DHVANI_WHISPER_COMPUTE_TYPE", "float32")
"""Paired with WHISPER_MODEL_SIZE above -- `tiny`/`float32` was the
sweep's stated operating point, not `tiny`/`int8`, per phase-2b.md
section 12's own reasoning."""


def _make_peer_handler(runner: OverlappedRunner, tts_sample_rate: int) -> OnPeerConnected:
    """Build the per-connection handler around providers loaded once.

    `runner` (and the STT/LLM/TTS providers inside it) is shared across every
    connection -- loading faster-whisper's model and the Piper voice is
    seconds-to-tens-of-seconds of blocking work, and doing it per connection
    would both repeat that cost on every reconnect and block the aiohttp
    event loop during the SDP handshake itself (an earlier version did
    exactly this, and its own automated browser check timed out waiting for
    the connection because the handshake never completed in time -- fixed by
    moving all model loading to `main()`, before `web.run_app`, where there
    is no event loop yet to block). Only the endpointer is per-connection:
    Silero VAD carries recurrent state across calls, so it must not be
    shared between simultaneous callers.
    """

    async def on_peer_connected(pc: RTCPeerConnection) -> None:
        endpointer = Endpointer(SileroVad())
        outbound = TTSAudioTrack(sample_rate=tts_sample_rate)
        pc.addTrack(outbound)

        @pc.on("track")
        def on_track(track: MediaStreamTrack) -> None:
            if track.kind != "audio":
                return
            session = ConversationSession(runner, endpointer, outbound.push)
            task = asyncio.ensure_future(session.run(receive_audio(track)))
            # A bare ensure_future() only surfaces an exception at garbage
            # collection time (via asyncio's default handler), which can be
            # long after it happened, or never, if the process exits first.
            # Log it immediately instead -- a session dying silently is a
            # real bug the previous version of this file could hide.
            task.add_done_callback(_log_session_exception)
            logger.info("peer connected, conversation session started")

    return on_peer_connected


def _log_session_exception(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.exception("conversation session crashed", exc_info=exc)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    load_dotenv()
    if not os.environ.get("GROQ_API_KEY"):
        raise SystemExit(
            "GROQ_API_KEY is not set. Get a free key at https://console.groq.com "
            "and export it before running the live demo."
        )

    logger.info("loading models (faster-whisper, Piper voice) -- once, at startup...")
    clock = RealClock()
    stt = CorrectedSTT(
        WhisperSTT(WHISPER_MODEL_SIZE, clock, compute_type=WHISPER_COMPUTE_TYPE),
        EntityCorrector(DEFAULT_LEXICON),
    )
    llm = GroqLLM(clock)
    model_path, config_path = ensure_voice_downloaded(DEFAULT_VOICE)
    tts = PiperTTS(model_path, clock, voice_config_path=config_path)
    runner = OverlappedRunner(stt, llm, tts, clock, LatencyBudget())
    logger.info("models loaded, starting server on http://localhost:8080/")

    app = create_app(_make_peer_handler(runner, tts.sample_rate))
    web.run_app(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
