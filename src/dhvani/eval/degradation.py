"""The degradation sweep: WER and STT latency as a function of channel
impairment (phase-3 spec section 7.6). Reuses `eval.wer.corpus_wer` and the
existing telemetry (`SessionTrace` percentiles over `Stage.STT`) -- no
second timing mechanism, same discipline as `eval.model_sweep`.

**Report both axes at every point** (spec section 3): a curve with only WER
would hide the reason this phase exists. Buffer-then-transcribe STT's
latency scales with utterance length (phase-2b spec's own model sweep
measured the shipped `small`/`int8` Whisper default at p50=7.46s), and
telephony callers speak in longer unbroken runs than browser testers do --
a degradation curve that reports only accuracy and hides a multi-second
response time would be exactly the favourable reading this project has
refused everywhere else.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dhvani.audio.channel import ChannelConfig, TelephonyChannel
from dhvani.clock import Clock
from dhvani.eval.audio_io import iter_chunks
from dhvani.eval.datasets import TranscriptExample
from dhvani.eval.wer import corpus_wer
from dhvani.providers.base import STTProvider
from dhvani.telemetry.session import SessionTrace
from dhvani.telemetry.span import TurnTrace
from dhvani.types import Stage


@dataclass(frozen=True, slots=True)
class DegradationPoint:
    label: str
    wer: float
    stt_p50_ms: float
    stt_p90_ms: float
    frames_lost: int
    n_utterances: int


async def _transcribe_one(
    example: TranscriptExample, config: ChannelConfig, stt: STTProvider, clock: Clock
) -> tuple[str, TurnTrace, int]:
    source_rate_hz = example.audio_chunks[0].sample_rate if example.audio_chunks else 16000
    # A fresh channel per example -- packet-loss and jitter draws from one
    # utterance never leak into the next one's, so `frames_lost` sums to an
    # honest per-example count regardless of `examples`' order.
    channel = TelephonyChannel(config, source_rate_hz=source_rate_hz, clock=clock)
    trace = TurnTrace(clock)
    hypothesis = ""
    degraded = channel.stream(iter_chunks(example.audio_chunks))
    async for transcript in stt.stream(degraded, trace=trace):
        if transcript.is_final:
            hypothesis = transcript.text
    return hypothesis, trace, channel.stats.frames_lost


async def run_degradation_sweep(
    examples: Sequence[TranscriptExample],
    configs: Sequence[ChannelConfig],
    stt: STTProvider,
    clock: Clock,
) -> list[DegradationPoint]:
    """Transcribes `examples` once per `ChannelConfig`, scoring corpus WER
    and reading STT latency off a `SessionTrace` built from that config's
    per-utterance traces -- the same pattern as `eval.model_sweep.run_sweep`,
    swept over channel impairment instead of model size/quantization."""
    points: list[DegradationPoint] = []
    for config in configs:
        session = SessionTrace()
        pairs: list[tuple[str, str]] = []
        total_frames_lost = 0

        for example in examples:
            hypothesis, trace, frames_lost = await _transcribe_one(example, config, stt, clock)
            session.add(trace)
            pairs.append((example.ground_truth_text, hypothesis))
            total_frames_lost += frames_lost

        wer_result = corpus_wer(pairs)
        stt_percentiles = session.percentiles(Stage.STT)

        points.append(
            DegradationPoint(
                label=config.label,
                wer=wer_result.wer,
                stt_p50_ms=stt_percentiles.p50_ms,
                stt_p90_ms=stt_percentiles.p90_ms,
                frames_lost=total_frames_lost,
                n_utterances=len(examples),
            )
        )
    return points


def render_table(points: Sequence[DegradationPoint]) -> str:
    """Markdown table for RESULTS.md -- both axes at every point, per the
    module docstring."""
    header = "| config | wer | stt_p50_ms | stt_p90_ms | frames_lost | n |"
    separator = "|---|---|---|---|---|---|"
    rows = [header, separator]
    for p in points:
        rows.append(
            f"| {p.label} | {p.wer:.1%} | {p.stt_p50_ms:.1f} | {p.stt_p90_ms:.1f} "
            f"| {p.frames_lost} | {p.n_utterances} |"
        )
    return "\n".join(rows)
