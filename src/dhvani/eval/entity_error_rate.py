"""F2 -- Entity Error Rate: does `dhvani-entity` recover ASR's mangling of
lexicon entity mentions, and at what cost to text it should leave alone?

Scored with exact (case-folded) match on the *canonical* form, never with
`phonetic_key` (phase-2 spec section 6.7): the corrector matches by
phonetic key, so a scorer using the same key would let a weak key pass its
own test. `corruption_rate` is always reported alongside the EER, on a
disjoint "clean" arm (examples with no lexicon entity at all) -- an EER
number alone only measures recall, and can't see a corrector that recovers
entities while also mangling clean text.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dhvani.clock import Clock
from dhvani.entity.corrector import EntityCorrector
from dhvani.entity.lexicon import DomainLexicon
from dhvani.entity.mentions import mentioned_entities
from dhvani.eval.audio_io import iter_chunks
from dhvani.eval.datasets import TranscriptExample
from dhvani.providers.base import STTProvider
from dhvani.telemetry.span import TurnTrace


@dataclass(frozen=True, slots=True)
class EerReport:
    split: str
    """"dev" while tuning the threshold, "test" for the reported run --
    phase-2 spec section 6.7's "tune on dev, report on test" rule."""
    threshold: float

    n_entity_mentions: int
    eer_before: float
    eer_after: float

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
    examples: Sequence[TranscriptExample], stt: STTProvider, clock: Clock
) -> list[TranscribedExample]:
    """Transcribes each example once with `stt`.

    Split out from `compute_entity_error_rate` so a threshold sweep (spec
    section 6.7: tune on dev, report on test) can reuse the same
    transcriptions across every threshold tried instead of re-running STT
    once per threshold -- the raw transcript doesn't depend on the
    correction threshold, only the scoring does.
    """
    return [
        TranscribedExample(
            ground_truth_text=example.ground_truth_text,
            raw_text=await _transcribe(example, stt, clock),
        )
        for example in examples
    ]


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
    n_wrong_before = 0
    n_wrong_after = 0
    n_clean = 0
    n_corrupted = 0

    for item in transcribed:
        mentioned = _mentioned_entities(item.ground_truth_text, lexicon)
        raw_text = item.raw_text
        corrected_text = corrector.correct(raw_text).text

        if mentioned:
            raw_lower = raw_text.lower()
            corrected_lower = corrected_text.lower()
            for canonical in mentioned:
                n_mentions += 1
                canonical_lower = canonical.lower()
                if canonical_lower not in raw_lower:
                    n_wrong_before += 1
                if canonical_lower not in corrected_lower:
                    n_wrong_after += 1
        else:
            n_clean += 1
            if corrected_text != raw_text:
                n_corrupted += 1

    eer_before = n_wrong_before / n_mentions if n_mentions else 0.0
    eer_after = n_wrong_after / n_mentions if n_mentions else 0.0
    corruption_rate = n_corrupted / n_clean if n_clean else 0.0

    return EerReport(
        split=split,
        threshold=corrector.threshold,
        n_entity_mentions=n_mentions,
        eer_before=eer_before,
        eer_after=eer_after,
        n_clean_examples=n_clean,
        corruption_rate=corruption_rate,
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
