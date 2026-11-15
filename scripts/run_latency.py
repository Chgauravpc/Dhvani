"""3B-9: end of speech -> first agent audio byte, real providers, real time.

    uv run python scripts/run_latency.py --arm whisper-tiny
    SARVAM_API_KEY=... uv run python scripts/run_latency.py --arm sarvam-realtime   # about Rs 3

Protocol: `docs/runs/3b-9-preregistration.md`. 50 utterances (the first 50 of the committed
Gram Vaani sample, `results/gramvaani_sample.json`, up to 10 s each) plus one warm-up that is
logged and excluded. Each is played at real time as 8 kHz mu-law telephone audio (the 3B-18
`pstn` leg). Both arms use the same LLM (Groq, default model) and TTS (Piper Hindi voice):

- `whisper-tiny`: replayed audio -> local Silero endpointer (500 ms of silence) -> local
  faster-whisper `tiny`/`int8` on the collected audio.
- `sarvam-realtime`: replayed audio streamed live to Sarvam's realtime WebSocket (mulaw,
  8 kHz) with server-side VAD (`silence_duration_ms=500`); the first `transcript.final`.

Instants (monotonic): end of speech (last Silero-voiced window of the clip) -> endpoint decision ->
final transcript -> first complete LLM sentence -> first TTS audio byte. Per-utterance rows go
to `results/latency/3b9_<arm>.jsonl` (no transcript text), resumable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import numpy as np

from dhvani.audio.resample import Resampler
from dhvani.clock import RealClock
from dhvani.config import load_dotenv
from dhvani.eval.audio_io import decode_audio_file_to_chunks, iter_chunks
from dhvani.eval.latency import stage_split
from dhvani.eval.pstn import to_pstn
from dhvani.pipeline.overlapped import _split_ready_sentence
from dhvani.providers.base import ProviderError
from dhvani.providers.groq_llm import GroqLLM
from dhvani.providers.piper_tts import DEFAULT_VOICE, PiperTTS, ensure_voice_downloaded
from dhvani.providers.sarvam_realtime_stt import SarvamRealtimeSTT
from dhvani.providers.whisper_stt import WhisperSTT
from dhvani.telemetry.span import TurnTrace
from dhvani.types import AudioChunk, Message
from dhvani.vad.endpointer import WINDOW_SAMPLES, Endpointer, EndpointEvent
from dhvani.vad.silero import SileroVad

DATA_DIR = Path("D:/Desktop/Projects/Dhvani_data/gramvaani_dev/GV_Dev_5h/Audio")
CHUNK_MS = 20
TAIL_S = 4.0
MAX_CLIP_S = 10.0


def speech_end_s(pcm16k: bytes) -> float:
    """End of speech in a clip: the end of the last 32 ms window Silero scores >= 0.5, computed
    offline over the whole clip (a fresh model). Trailing silence after it is the user being
    quiet, which the endpointer must wait out, so it counts toward the endpoint stage."""
    samples = np.frombuffer(pcm16k, dtype=np.int16).astype(np.float32) / 32768.0
    vad = SileroVad()
    last = -1
    for k in range(len(samples) // WINDOW_SAMPLES):
        if vad.probability(samples[k * WINDOW_SAMPLES : (k + 1) * WINDOW_SAMPLES]) >= 0.5:
            last = k
    return (last + 1) * WINDOW_SAMPLES / 16000


class Replay:
    """Plays one clip at real time as 20 ms chunks, then silence, until abandoned.

    `clip_end_ns` is the instant the last *speech* of the clip is delivered (`speech_end_s`)."""

    def __init__(self, pcm: bytes, rate: int, clock: RealClock, speech_end: float) -> None:
        self._pcm, self._rate, self._clock = pcm, rate, clock
        self._step = rate * CHUNK_MS // 1000 * 2
        self.start_ns = clock.now_ns()
        self.clip_end_ns = self.start_ns + int(speech_end * 1e9)

    async def __aiter__(self) -> AsyncIterator[AudioChunk]:
        total = len(self._pcm) + int(TAIL_S * self._rate * 2)
        for k in range((total + self._step - 1) // self._step):
            seg = self._pcm[k * self._step : (k + 1) * self._step]
            seg = seg + bytes(self._step - len(seg))
            yield AudioChunk(pcm=seg, sample_rate=self._rate, seq=k)
            target = self.start_ns + (k + 1) * CHUNK_MS * 1_000_000
            await asyncio.sleep(max(0.0, (target - self._clock.now_ns()) / 1e9))


async def _llm_to_tts(
    transcript: str, llm: GroqLLM, tts: PiperTTS, clock: RealClock
) -> tuple[int, int]:
    """(first complete sentence ready, first TTS audio byte), ns."""
    trace = TurnTrace(clock)
    sentence: str | None = None
    buffer = ""
    agen = llm.stream([Message(role="user", content=transcript)], trace=trace)
    async for delta in agen:
        buffer += delta.text or ""
        sentence, buffer = _split_ready_sentence(buffer)
        if sentence is not None:
            break
    await agen.aclose()
    if sentence is None:
        sentence = buffer.strip()
    if not sentence:
        raise ProviderError("empty LLM reply")
    t_sentence = clock.now_ns()

    async def one() -> AsyncIterator[str]:
        yield sentence  # type: ignore[misc]

    t_audio = 0
    tts_stream = tts.stream(one(), trace=trace)
    async for chunk in tts_stream:
        if chunk.pcm:
            t_audio = clock.now_ns()
            break
    await tts_stream.aclose()
    if not t_audio:
        raise ProviderError("TTS produced no audio")
    return t_sentence, t_audio


async def _turn_whisper(
    pcm8: bytes, stt: WhisperSTT, llm: GroqLLM, tts: PiperTTS, clock: RealClock
) -> dict[str, Any]:
    pcm16 = Resampler(8000, 16000).process(pcm8)
    replay = Replay(pcm16, 16000, clock, speech_end_s(pcm16))
    endpointer = Endpointer(SileroVad(), min_silence_ms=500)
    collected: list[AudioChunk] = []
    t_endpoint = 0
    async for chunk in replay:
        collected.append(chunk)
        if EndpointEvent.SPEECH_ENDED in endpointer.feed(chunk):
            t_endpoint = clock.now_ns()
            break
    if not t_endpoint:
        raise ProviderError("endpointer never fired")
    text = ""
    async for tr in stt.stream(iter_chunks(collected), trace=TurnTrace(clock)):
        if tr.is_final:
            text = tr.text
    t_final = clock.now_ns()
    if not text.strip():
        raise ProviderError("empty_transcript")
    t_sentence, t_audio = await _llm_to_tts(text, llm, tts, clock)
    return {
        **stage_split(replay.clip_end_ns, t_endpoint, t_final, t_sentence, t_audio),
        "transcript_chars": len(text),
    }


async def _turn_sarvam(
    pcm8: bytes, stt: SarvamRealtimeSTT, llm: GroqLLM, tts: PiperTTS, clock: RealClock
) -> dict[str, Any]:
    replay = Replay(pcm8, 8000, clock, speech_end_s(Resampler(8000, 16000).process(pcm8)))
    text = ""
    async for tr in stt.stream(replay.__aiter__(), trace=TurnTrace(clock)):
        if tr.is_final:
            text = tr.text
    t_final = clock.now_ns()
    t_vad_end = stt.event_time_ns("vad.speech_end")
    t_server_final = stt.event_time_ns("transcript.final") or t_final
    if not text.strip() or t_vad_end is None:
        raise ProviderError("empty_transcript" if not text.strip() else "no vad.speech_end event")
    t_sentence, t_audio = await _llm_to_tts(text, llm, tts, clock)
    return {
        **stage_split(replay.clip_end_ns, t_vad_end, t_server_final, t_sentence, t_audio),
        "transcript_chars": len(text),
    }


def _done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {json.loads(line)["uttid"] for line in path.read_text("utf-8").splitlines() if line}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=["whisper-tiny", "sarvam-realtime"], required=True)
    parser.add_argument("--n", type=int, default=50)
    args = parser.parse_args()
    load_dotenv()
    clock = RealClock()
    sample = json.loads(Path("results/gramvaani_sample.json").read_text("utf-8"))["items"]
    picked = [i for i in sample if i["seconds"] <= MAX_CLIP_S][: args.n + 1]
    warmup, items = picked[0], picked[1:]
    llm = GroqLLM(clock)
    model_path, config_path = ensure_voice_downloaded(DEFAULT_VOICE)
    tts = PiperTTS(model_path, clock, voice_config_path=config_path)
    whisper = WhisperSTT("tiny", clock, compute_type="int8") if args.arm == "whisper-tiny" else None
    sarvam = SarvamRealtimeSTT(clock) if args.arm == "sarvam-realtime" else None
    out_path = Path(f"results/latency/3b9_{args.arm}.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = _done(out_path)
    with out_path.open("a", encoding="utf-8") as out:
        for item in [warmup, *items]:
            uttid, is_warmup = item["uttid"], item is warmup
            if uttid in done:
                continue
            chunks = decode_audio_file_to_chunks(DATA_DIR / f"{uttid}.mp3", 16_000)
            pcm8 = to_pstn(chunks)[0].pcm
            row: dict[str, Any] = {
                "uttid": uttid,
                "arm": args.arm,
                "warmup": is_warmup,
                "clip_s": len(pcm8) / 2 / 8000,
            }
            try:
                if whisper is not None:
                    row |= await _turn_whisper(pcm8, whisper, llm, tts, clock)
                else:
                    assert sarvam is not None
                    row |= await _turn_sarvam(pcm8, sarvam, llm, tts, clock)
            except ProviderError as exc:
                row["error"] = str(exc)[:200]
                if "402" in str(exc) or "1003" in str(exc):
                    out.write(json.dumps(row) + "\n")
                    print(f"stopped (credit/quota): {exc}"[:300], flush=True)
                    return 3
            out.write(json.dumps(row) + "\n")
            out.flush()
            print(
                f"{uttid} {'warmup ' if is_warmup else ''}"
                + (
                    f"total {row['total_ms']:.0f} ms"
                    if "total_ms" in row
                    else f"ERR {row['error']}"
                ),
                flush=True,
            )
            await asyncio.sleep(1.0)
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
