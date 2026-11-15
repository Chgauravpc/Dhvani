"""3B-9 latency summaries: percentiles and the stage split of a turn.

A turn's stages are consecutive intervals between five instants, so they sum to the
total exactly: clip end (last recorded sample) -> endpoint decision -> final transcript ->
first complete LLM sentence -> first TTS audio byte.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

STAGES = ("endpoint_ms", "stt_ms", "llm_ms", "tts_ms")


def percentile(values: Sequence[float], p: float) -> float:
    """Linear-interpolated percentile (the numpy default), `p` in [0, 100]."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    rank = (len(ordered) - 1) * p / 100.0
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def stage_split(
    clip_end: int, endpoint: int, final: int, sentence: int, first_audio: int
) -> dict[str, float]:
    """Stage durations in ms from five monotonic instants (ns); they sum to `total_ms`.

    An instant earlier than its predecessor is clamped to it (a stage cannot be negative);
    `clamped` counts how many were.
    """
    points = [clip_end, endpoint, final, sentence, first_audio]
    clamped = 0
    fixed = [points[0]]
    for p in points[1:]:
        if p < fixed[-1]:
            clamped += 1
            p = fixed[-1]
        fixed.append(p)
    ms = [(b - a) / 1_000_000 for a, b in zip(fixed, fixed[1:], strict=False)]
    return {**dict(zip(STAGES, ms, strict=True)), "total_ms": sum(ms), "clamped": float(clamped)}


def summarise(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """p50 / p90 of each stage and the total over the records that completed."""
    ok = [r for r in records if not r.get("error")]
    out: dict[str, Any] = {"n_completed": len(ok), "n_failed": len(records) - len(ok)}
    if ok:
        for key in (*STAGES, "total_ms"):
            values = [float(r[key]) for r in ok]
            out[key] = {"p50": percentile(values, 50), "p90": percentile(values, 90)}
    return out
