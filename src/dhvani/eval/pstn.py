"""The `pstn` condition of 3B-18 / 3B-20: an 8 kHz narrowband G.711 mu-law phone leg.

No packet loss, no jitter (those are `pstn+loss`, not run): the audio is band-limited
to 8 kHz with the project's resampler and passed through a mu-law encode/decode, and it
**stays at 8 kHz** (sent to the ASR as an 8 kHz mono WAV, the rate a phone network
carries), rather than being upsampled back. Deterministic: same input, same output.
"""

from __future__ import annotations

from collections.abc import Sequence

from dhvani.audio import mulaw
from dhvani.audio.resample import Resampler
from dhvani.types import AudioChunk

PSTN_RATE_HZ = 8_000


def to_pstn(chunks: Sequence[AudioChunk]) -> list[AudioChunk]:
    """One row's audio through the phone leg, as a single 8 kHz chunk."""
    if not chunks:
        return []
    rate = chunks[0].sample_rate
    pcm = b"".join(c.pcm for c in chunks)
    narrow = Resampler(rate, PSTN_RATE_HZ).process(pcm)
    narrow = mulaw.decode(mulaw.encode(narrow))
    return [AudioChunk(pcm=narrow, sample_rate=PSTN_RATE_HZ, seq=0, is_last=True)]
