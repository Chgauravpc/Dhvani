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
    """Every canonical entity with at least one lexicon variant appearing
    as a case-insensitive substring of `text`. An entity mentioned more
    than once in the same example still counts once -- this mirrors the
    section 2A entity-density gate's own per-example counting, and keeps
    "how many mentions" answering "how many (example, entity) pairs",
    not "how many raw string occurrences"."""
    lowered = text.lower()
    return {
        canonical
        for canonical, _script, variant in lexicon.all_variants()
        if variant.lower() in lowered
    }


async def _transcribe(example: TranscriptExample, stt: STTProvider, clock: Clock) -> str:
    trace = TurnTrace(clock)
    final_text = ""
    async for transcript in stt.stream(iter_chunks(example.audio_chunks), trace=trace):
        if transcript.is_final:
            final_text = transcript.text
    return final_text


async def compute_entity_error_rate(
    examples: Sequence[TranscriptExample],
    lexicon: DomainLexicon,
    stt: STTProvider,
    corrector: EntityCorrector,
    clock: Clock,
    split: str,
) -> EerReport:
    """Transcribes `examples` with `stt`, corrects each transcript with
    `corrector`, and scores both entity recovery and corruption.

    Entity-bearing arm: examples whose ground truth mentions at least one
    lexicon entity. For each mention, checks whether the canonical form
    ended up present in the raw transcript and in the corrected one.

    Clean arm: examples whose ground truth mentions none. Runs the
    corrector anyway and counts how many come back changed at all.
    """
    n_mentions = 0
    n_wrong_before = 0
    n_wrong_after = 0
    n_clean = 0
    n_corrupted = 0

    for example in examples:
        mentioned = _mentioned_entities(example.ground_truth_text, lexicon)
        raw_text = await _transcribe(example, stt, clock)
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
