"""F2 -- Entity Error Rate: does `dhvani-entity` recover ASR's mangling of
lexicon entity mentions, and at what cost to text it should leave alone?

Two rates per entity mention (phase-3b item 3B-2), both by word-bounded
exact match on the hand-curated lexicon strings -- never `phonetic_key`
(phase-2 spec section 6.7): the corrector matches by phonetic key, so a
scorer using the same key would let a weak key pass its own test.

- **Recognition EER** -- a mention is correct if *any* curated variant of
  that entity, in any script, appears in the output. The ASR claim: a
  transcript reading `आधार कार्ड` recognised the entity even though it is
  not the Latin canonical `Aadhaar`.
- **Canonical miss rate** -- a mention is correct only if the canonical
  form itself appears. The downstream claim: a tool call needs `Aadhaar`.

Before 3B-2 only the second existed, under the name "EER", which scored
every correct Devanagari transcript as an ASR failure (the Sep 23 audit's
finding A2). Keeping the two apart stops a transliteration step from being
reported as entity *recovery*.

`corruption_rate` is always reported alongside, on a disjoint "clean" arm
(examples with no lexicon entity at all) -- a recovery number alone can't
see a corrector that also mangles clean text.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dhvani.clock import Clock
from dhvani.entity.corrector import EntityCorrector
from dhvani.entity.lexicon import DomainLexicon
from dhvani.entity.mentions import contains_variant, mentioned_entities
from dhvani.eval.audio_io import iter_chunks
from dhvani.eval.datasets import TranscriptExample
from dhvani.eval.transcript_log import TranscriptLog
from dhvani.providers.base import STTProvider
from dhvani.telemetry.span import TurnTrace


@dataclass(frozen=True, slots=True)
class EerReport:
    split: str
    """"dev" while tuning the threshold, "test" for the reported run --
    phase-2 spec section 6.7's "tune on dev, report on test" rule."""
    threshold: float

    n_entity_mentions: int
    recognition_eer_before: float
    recognition_eer_after: float
    canonical_miss_before: float
    canonical_miss_after: float

    n_clean_examples: int
    corruption_rate: float


def _mentioned_entities(text: str, lexicon: DomainLexicon) -> set[str]:
    """Every canonical entity the ground truth mentions, word-bounded and
    deduplicated per example -- the shared definition in
    `dhvani.entity.mentions` (phase-3b item 3B-1), the same one the
    entity-density gate counts with. Before 3B-1 this was a substring test,
    so "company" counted as a PAN card mention."""
    return mentioned_entities(text, lexicon)


async def _transcribe(example: TranscriptExample, stt: STTProvider, clock: Clock) -> str:
    trace = TurnTrace(clock)
    final_text = ""
    async for transcript in stt.stream(iter_chunks(example.audio_chunks), trace=trace):
        if transcript.is_final:
            final_text = transcript.text
    return final_text


@dataclass(frozen=True, slots=True)
class TranscribedExample:
    ground_truth_text: str
    raw_text: str


async def transcribe_examples(
    examples: Sequence[TranscriptExample],
    stt: STTProvider,
    clock: Clock,
    log: TranscriptLog | None = None,
    split: str = "",
) -> list[TranscribedExample]:
    """Transcribes each example once with `stt`.

    Split out from `compute_entity_error_rate` so a threshold sweep (spec
    section 6.7: tune on dev, report on test) can reuse the same
    transcriptions across every threshold tried instead of re-running STT
    once per threshold -- the raw transcript doesn't depend on the
    correction threshold, only the scoring does.

    With a `log` (3B-3), an example already logged for the same
    (dataset, example_id, stt, model) is read from it instead of being
    re-transcribed, and every new transcription is appended to it.
    """
    out: list[TranscribedExample] = []
    for example in examples:
        raw_text = None
        if log is not None:
            raw_text = log.lookup(example.dataset, example.example_id)
        if raw_text is None:
            raw_text = await _transcribe(example, stt, clock)
            if log is not None:
                log.record(
                    dataset=example.dataset,
                    example_id=example.example_id,
                    ground_truth_text=example.ground_truth_text,
                    raw_text=raw_text,
                    split=split,
                )
        out.append(
            TranscribedExample(ground_truth_text=example.ground_truth_text, raw_text=raw_text)
        )
    return out


def score_transcripts(
    transcribed: Sequence[TranscribedExample],
    lexicon: DomainLexicon,
    corrector: EntityCorrector,
    split: str,
) -> EerReport:
    """Same scoring `compute_entity_error_rate` does, from already-
    transcribed text (see `transcribe_examples`) instead of running STT
    again -- what a threshold sweep should call per threshold.
    """
    n_mentions = 0
    n_unrecognised_before = 0
    n_unrecognised_after = 0
    n_noncanonical_before = 0
    n_noncanonical_after = 0
    n_clean = 0
    n_corrupted = 0

    for item in transcribed:
        mentioned = _mentioned_entities(item.ground_truth_text, lexicon)
        raw_text = item.raw_text
        corrected_text = corrector.correct(raw_text).text

        if mentioned:
            recognised_before = mentioned_entities(raw_text, lexicon)
            recognised_after = mentioned_entities(corrected_text, lexicon)
            for canonical in mentioned:
                n_mentions += 1
                n_unrecognised_before += canonical not in recognised_before
                n_unrecognised_after += canonical not in recognised_after
                n_noncanonical_before += not contains_variant(raw_text, canonical)
                n_noncanonical_after += not contains_variant(corrected_text, canonical)
        else:
            n_clean += 1
            if corrected_text != raw_text:
                n_corrupted += 1

    def rate(n: int) -> float:
        return n / n_mentions if n_mentions else 0.0

    return EerReport(
        split=split,
        threshold=corrector.threshold,
        n_entity_mentions=n_mentions,
        recognition_eer_before=rate(n_unrecognised_before),
        recognition_eer_after=rate(n_unrecognised_after),
        canonical_miss_before=rate(n_noncanonical_before),
        canonical_miss_after=rate(n_noncanonical_after),
        n_clean_examples=n_clean,
        corruption_rate=n_corrupted / n_clean if n_clean else 0.0,
    )


async def compute_entity_error_rate(
    examples: Sequence[TranscriptExample],
    lexicon: DomainLexicon,
    stt: STTProvider,
    corrector: EntityCorrector,
    clock: Clock,
    split: str,
) -> EerReport:
    """Convenience: transcribe then score in one call, for a single fixed
    threshold. Entity-bearing arm: examples whose ground truth mentions at
    least one lexicon entity, scored on whether the canonical form ended
    up present in the raw and corrected transcripts. Clean arm: examples
    with no mention, scored on whether correction touched them at all.

    A threshold sweep should call `transcribe_examples` once and
    `score_transcripts` per threshold instead of calling this repeatedly,
    to avoid re-running STT for every threshold.
    """
    transcribed = await transcribe_examples(examples, stt, clock)
    return score_transcripts(transcribed, lexicon, corrector, split)
