from __future__ import annotations

import math
import struct

from dhvani.eval.pstn import PSTN_RATE_HZ, to_pstn
from dhvani.types import AudioChunk


def _tone(rate: int = 16_000, seconds: float = 0.5) -> list[AudioChunk]:
    n = int(rate * seconds)
    pcm = b"".join(
        struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(n)
    )
    half = len(pcm) // 2
    return [AudioChunk(pcm[:half], rate, 0, False), AudioChunk(pcm[half:], rate, 1, True)]


def test_pstn_is_one_8khz_chunk_of_about_half_the_samples() -> None:
    out = to_pstn(_tone())
    assert len(out) == 1 and out[0].sample_rate == PSTN_RATE_HZ and out[0].is_last
    assert abs(len(out[0].pcm) / 2 - 4_000) <= 4


def test_pstn_is_deterministic_and_changes_the_samples() -> None:
    chunks = _tone()
    assert to_pstn(chunks)[0].pcm == to_pstn(chunks)[0].pcm
    assert to_pstn(chunks)[0].pcm != b"".join(c.pcm for c in chunks)[::4]


def test_empty_input_gives_nothing() -> None:
    assert to_pstn([]) == []
