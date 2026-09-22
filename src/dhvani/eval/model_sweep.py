"""Workstream B -- WER-against-latency Pareto sweep over Whisper model size
and quantization (phase-2b spec section B.2). The project's only model-level
work: not "which model is best" (a Pareto curve has no single best), but a
stated operating point with a reason.

Latency comes from the **existing telemetry** -- `SessionTrace.percentiles`
(Phase 0) over each utterance's `Stage.STT` span -- never a second timing
mechanism. WER comes from `eval.wer.corpus_wer`, aggregated the same
sum-of-edits way as everywhere else in this project.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dhvani.clock import Clock
from dhvani.eval.audio_io import iter_chunks
from dhvani.eval.datasets import TranscriptExample
from dhvani.eval.wer import corpus_wer
from dhvani.providers.whisper_stt import WhisperSTT
from dhvani.telemetry.session import SessionTrace
from dhvani.telemetry.span import TurnTrace
from dhvani.types import Stage


@dataclass(frozen=True, slots=True)
class SweepPoint:
    model_size: str  # "tiny" | "base" | "small"
    compute_type: str  # "int8" | "float32"
    wer: float
    stt_p50_ms: float
    stt_p90_ms: float
    realtime_factor: float
    """Total STT wall time / total audio duration across the swept examples;
    < 1 is faster than realtime."""
    n_utterances: int


async def _transcribe_one(
    example: TranscriptExample, stt: WhisperSTT, clock: Clock
) -> tuple[str, TurnTrace]:
    trace = TurnTrace(clock)
    hypothesis = ""
    async for transcript in stt.stream(iter_chunks(example.audio_chunks), trace=trace):
        if transcript.is_final:
            hypothesis = transcript.text
    return hypothesis, trace


async def run_sweep(
    examples: Sequence[TranscriptExample],
    model_sizes: Sequence[str],
    compute_types: Sequence[str],
    clock: Clock,
) -> list[SweepPoint]:
    """Transcribes `examples` once per (model_size, compute_type) grid cell
    with a fresh `WhisperSTT`, scoring corpus WER and reading STT latency off
    a `SessionTrace` built from that run's per-utterance traces."""
    points: list[SweepPoint] = []
    for model_size in model_sizes:
        for compute_type in compute_types:
            stt = WhisperSTT(model_size, clock, compute_type=compute_type)
            session = SessionTrace()
            pairs: list[tuple[str, str]] = []
            total_audio_ms = 0.0

            for example in examples:
                hypothesis, trace = await _transcribe_one(example, stt, clock)
                session.add(trace)
                pairs.append((example.ground_truth_text, hypothesis))
                total_audio_ms += sum(chunk.duration_ms for chunk in example.audio_chunks)

            wer_result = corpus_wer(pairs)
            stt_percentiles = session.percentiles(Stage.STT)
            total_stt_ms = sum(t.stage_total_ms(Stage.STT) for t in session.turns)
            realtime_factor = total_stt_ms / total_audio_ms if total_audio_ms else 0.0

            points.append(
                SweepPoint(
                    model_size=model_size,
                    compute_type=compute_type,
                    wer=wer_result.wer,
                    stt_p50_ms=stt_percentiles.p50_ms,
                    stt_p90_ms=stt_percentiles.p90_ms,
                    realtime_factor=realtime_factor,
                    n_utterances=len(examples),
                )
            )
    return points


def _dominates(a: SweepPoint, b: SweepPoint) -> bool:
    """True if `a` is at least as good as `b` on both WER and p50 latency,
    and strictly better on at least one -- the standard Pareto-domination
    rule. Two points with identical (wer, stt_p50_ms) dominate neither
    other; both stay on the front."""
    not_worse = a.wer <= b.wer and a.stt_p50_ms <= b.stt_p50_ms
    strictly_better = a.wer < b.wer or a.stt_p50_ms < b.stt_p50_ms
    return not_worse and strictly_better


def pareto_front(points: Sequence[SweepPoint]) -> list[SweepPoint]:
    """Points not dominated on both WER and p50 latency (lower is better on
    each axis)."""
    return [
        p for p in points if not any(_dominates(other, p) for other in points if other is not p)
    ]


def render_table(points: Sequence[SweepPoint]) -> str:
    """Markdown table, Pareto-optimal rows marked, for RESULTS.md."""
    front_ids = {id(p) for p in pareto_front(points)}
    header = (
        "| model_size | compute_type | wer | stt_p50_ms | stt_p90_ms "
        "| realtime_factor | n | pareto |"
    )
    separator = "|---|---|---|---|---|---|---|---|"
    rows = [header, separator]
    for p in points:
        marker = "yes" if id(p) in front_ids else ""
        rows.append(
            f"| {p.model_size} | {p.compute_type} | {p.wer:.1%} | {p.stt_p50_ms:.1f} "
            f"| {p.stt_p90_ms:.1f} | {p.realtime_factor:.2f} | {p.n_utterances} | {marker} |"
        )
    return "\n".join(rows)
