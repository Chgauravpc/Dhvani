"""Real TTS via Piper, consuming the sentence-by-sentence text stream directly.

Piper synthesizes per call, which is exactly what lets this provider start
speaking the first sentence while `OverlappedRunner`'s background LLM task is
still producing the rest -- see phase-1 spec section 6.3.

`piper.voice.PiperVoice.synthesize()` returns Piper's *own* `AudioChunk`
dataclass, which name-collides with `dhvani.types.AudioChunk` -- imported
here aliased to avoid the collision (phase-1 spec section 10).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from huggingface_hub import hf_hub_download
from piper import PiperVoice
from piper.voice import AudioChunk as PiperAudioChunk

from dhvani.clock import Clock
from dhvani.telemetry.span import FIRST_AUDIO_OUT, TurnTrace
from dhvani.types import AudioChunk, Stage

DEFAULT_VOICE = "hi_IN-priyamvada-medium"
"""Pinned per phase-1 spec section 9 -- one of three hi_IN "medium" voices on
rhasspy/piper-voices; no strong reason preferred the other two."""

_VOICES_REPO = "rhasspy/piper-voices"


def _voice_repo_path(voice: str) -> str:
    lang_region, speaker, quality = voice.split("-")
    lang_code = lang_region.split("_")[0]
    return f"{lang_code}/{lang_region}/{speaker}/{quality}/{voice}"


def ensure_voice_downloaded(
    voice: str = DEFAULT_VOICE, cache_dir: Path | None = None
) -> tuple[Path, Path]:
    """Download `voice`'s model + config from rhasspy/piper-voices if not
    already cached locally, and return (model_path, config_path).

    `piper-tts==1.8.0` ships no download helper of its own (phase-1 spec
    section 10), so this uses `huggingface_hub` directly.
    """
    base = _voice_repo_path(voice)
    cache_dir_str = str(cache_dir) if cache_dir is not None else None
    model_path = hf_hub_download(_VOICES_REPO, f"{base}.onnx", cache_dir=cache_dir_str)
    config_path = hf_hub_download(_VOICES_REPO, f"{base}.onnx.json", cache_dir=cache_dir_str)
    return Path(model_path), Path(config_path)


class PiperTTS:
    name = "piper"

    def __init__(
        self,
        voice_model_path: Path,
        clock: Clock,
        voice_config_path: Path | None = None,
    ) -> None:
        self._voice = PiperVoice.load(voice_model_path, config_path=voice_config_path)
        self.sample_rate = self._voice.config.sample_rate
        self._clock = clock

    async def stream(
        self, text: AsyncIterator[str], *, trace: TurnTrace
    ) -> AsyncIterator[AudioChunk]:
        async with trace.aspan(Stage.TTS, self.name):
            seq = 0
            first_chunk = True
            async for sentence in text:
                piper_chunks: list[PiperAudioChunk] = await asyncio.to_thread(
                    self._synthesize, sentence
                )
                for piper_chunk in piper_chunks:
                    if first_chunk:
                        trace.mark(FIRST_AUDIO_OUT)
                        first_chunk = False
                    yield AudioChunk(
                        pcm=piper_chunk.audio_int16_bytes,
                        sample_rate=piper_chunk.sample_rate,
                        seq=seq,
                    )
                    seq += 1

    def _synthesize(self, sentence: str) -> list[PiperAudioChunk]:
        return list(self._voice.synthesize(sentence))
