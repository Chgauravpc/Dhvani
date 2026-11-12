from __future__ import annotations

import pytest

from dhvani.clock import FakeClock
from dhvani.entity.corrector import EntityCorrector
from dhvani.entity.lexicon import DEVANAGARI, LATIN, DomainLexicon, LexiconEntry
from dhvani.eval.datasets import TranscriptExample
from dhvani.eval.entity_error_rate import (
    EerReport,
    TranscribedExample,
    compute_entity_error_rate,
    score_transcripts,
    transcribe_examples,
)
from dhvani.providers.mock import MockSTT, MockTiming
from dhvani.types import AudioChunk

pytestmark = pytest.mark.asyncio

_LEXICON = DomainLexicon(
    [
        LexiconEntry(
            canonical="Aadhaar",
            variants={
                LATIN: ("aadhaar", "aadhar", "adhaar"),
                DEVANAGARI: ("आधार कार्ड",),
            },
        ),
        LexiconEntry(canonical="UPI", variants={LATIN: ("upi",)}),
        LexiconEntry(canonical="PAN card", variants={LATIN: ("pan card",)}),
    ]
)
_SILENCE = (AudioChunk(pcm=b"\x00\x00" * 160, sample_rate=16000, seq=0, is_last=True),)


def _example(ground_truth: str) -> TranscriptExample:
    return TranscriptExample(audio_chunks=_SILENCE, ground_truth_text=ground_truth)


def _stt(final_text: str, clock: FakeClock) -> MockSTT:
    return MockSTT(
        partials=[], final=final_text, timing=MockTiming(ttfb_ms=1.0, per_unit_ms=1.0), clock=clock
    )


async def test_eer_zero_when_asr_gets_the_entity_right() -> None:
    clock = FakeClock()
    corrector = EntityCorrector(_LEXICON, threshold=0.82)
    report = await compute_entity_error_rate(
        [_example("please check my aadhaar status")],
        _LEXICON,
        _stt("please check my Aadhaar status", clock),
        corrector,
        clock,
        split="test",
    )
    assert report.n_entity_mentions == 1
    assert report.canonical_miss_before == pytest.approx(0.0)
    assert report.canonical_miss_after == pytest.approx(0.0)


async def test_eer_before_counts_a_mangled_entity_asr_missed() -> None:
    clock = FakeClock()
    corrector = EntityCorrector(_LEXICON, threshold=0.82)
    report = await compute_entity_error_rate(
        [_example("please check my aadhaar status")],
        _LEXICON,
        _stt("please check my adhar status", clock),  # ASR mangled it, but correctable
        corrector,
        clock,
        split="test",
    )
    assert report.canonical_miss_before == pytest.approx(1.0)
    assert report.canonical_miss_after == pytest.approx(0.0)  # the corrector recovers it


async def test_eer_after_stays_wrong_when_correction_is_too_weak() -> None:
    """ "adar" (missing the h) scores 0.889 against the lexicon's "adhar"
    phonetic key (verified directly) -- a threshold above that correctly
    declines to touch it, so it stays wrong after "correction."""
    clock = FakeClock()
    strict_corrector = EntityCorrector(_LEXICON, threshold=0.95)
    report = await compute_entity_error_rate(
        [_example("please check my aadhaar status")],
        _LEXICON,
        _stt("please check my adar status", clock),
        strict_corrector,
        clock,
        split="test",
    )
    assert report.canonical_miss_before == pytest.approx(1.0)
    assert report.canonical_miss_after == pytest.approx(1.0)


async def test_multiple_entities_in_one_example_count_as_multiple_mentions() -> None:
    clock = FakeClock()
    corrector = EntityCorrector(_LEXICON, threshold=0.82)
    report = await compute_entity_error_rate(
        [_example("link my aadhaar to upi")],
        _LEXICON,
        _stt("link my Aadhaar to UPI", clock),
        corrector,
        clock,
        split="test",
    )
    assert report.n_entity_mentions == 2


async def test_clean_example_with_no_corruption() -> None:
    clock = FakeClock()
    corrector = EntityCorrector(_LEXICON, threshold=0.82)
    report = await compute_entity_error_rate(
        [_example("the weather is nice today")],
        _LEXICON,
        _stt("the weather is nice today", clock),
        corrector,
        clock,
        split="test",
    )
    assert report.n_entity_mentions == 0
    assert report.n_clean_examples == 1
    assert report.corruption_rate == pytest.approx(0.0)


async def test_clean_example_that_the_corrector_falsely_alters() -> None:
    """A permissive threshold can turn an unrelated word into a false
    correction on text that had no real entity at all -- corruption_rate
    exists specifically to catch this."""
    clock = FakeClock()
    lenient_corrector = EntityCorrector(_LEXICON, threshold=0.3)
    report = await compute_entity_error_rate(
        [_example("the weather is nice today")],
        _LEXICON,
        _stt("the weather is nice today", clock),
        lenient_corrector,
        clock,
        split="test",
    )
    assert report.n_clean_examples == 1
    assert report.corruption_rate == pytest.approx(1.0)


async def test_report_carries_split_and_threshold() -> None:
    clock = FakeClock()
    corrector = EntityCorrector(_LEXICON, threshold=0.75)
    report = await compute_entity_error_rate(
        [_example("no entity here")],
        _LEXICON,
        _stt("no entity here", clock),
        corrector,
        clock,
        split="dev",
    )
    assert report.split == "dev"
    assert report.threshold == pytest.approx(0.75)


async def test_transcribe_then_score_matches_compute_entity_error_rate() -> None:
    """The threshold-sweep path (transcribe_examples once, score_transcripts
    per threshold) must produce the same numbers as the single-call
    convenience function -- it's a performance split, not a behavior
    change."""
    clock = FakeClock()
    examples = [
        _example("please check my aadhaar status"),
        _example("the weather is nice today"),
    ]
    corrector = EntityCorrector(_LEXICON, threshold=0.82)

    direct = await compute_entity_error_rate(
        examples, _LEXICON, _stt("please check my adhar status", clock), corrector, clock, "test"
    )

    transcribed = await transcribe_examples(
        examples, _stt("please check my adhar status", clock), clock
    )
    via_sweep = score_transcripts(transcribed, _LEXICON, corrector, split="test")

    assert via_sweep == direct


async def test_score_transcripts_reused_across_thresholds() -> None:
    """The whole point of splitting transcription from scoring: one
    transcription pass, multiple thresholds scored from it."""
    clock = FakeClock()
    examples = [_example("please check my aadhaar status")]
    transcribed = await transcribe_examples(
        examples, _stt("please check my adar status", clock), clock
    )

    lenient = score_transcripts(
        transcribed, _LEXICON, EntityCorrector(_LEXICON, threshold=0.5), "dev"
    )
    strict = score_transcripts(
        transcribed, _LEXICON, EntityCorrector(_LEXICON, threshold=0.95), "dev"
    )

    assert lenient.canonical_miss_after == pytest.approx(0.0)
    assert strict.canonical_miss_after == pytest.approx(1.0)


# --- phase-3b 3B-2: recognition vs canonicalization -------------------------


def _score(ground_truth: str, asr_output: str, threshold: float = 0.99) -> EerReport:
    """Scores one already-transcribed example. Threshold 0.99 makes the
    corrector all but inert, so before/after differences come from it only
    where a test wants them."""
    return score_transcripts(
        [TranscribedExample(ground_truth_text=ground_truth, raw_text=asr_output)],
        _LEXICON,
        EntityCorrector(_LEXICON, threshold=threshold),
        split="test",
    )


async def test_correct_devanagari_output_is_recognised_but_not_canonical() -> None:
    """Sep 23 audit A2: the old scorer marked this an ASR failure."""
    report = _score("मेरा आधार कार्ड खो गया", "मेरा आधार कार्ड खो गया")
    assert report.n_entity_mentions == 1
    assert report.recognition_eer_before == pytest.approx(0.0)
    assert report.canonical_miss_before == pytest.approx(1.0)


async def test_variant_spelling_is_recognised_but_not_canonical() -> None:
    report = _score("check my aadhar status", "check my aadhar status")
    assert report.recognition_eer_before == pytest.approx(0.0)
    assert report.canonical_miss_before == pytest.approx(1.0)


async def test_company_is_not_a_pan_mention() -> None:
    """Sep 23 audit A1: "company" fired the PAN variant as a substring."""
    report = _score("i work at a software company", "i work at a software company")
    assert report.n_entity_mentions == 0
    assert report.n_clean_examples == 1


async def test_canonical_inside_a_longer_word_does_not_count() -> None:
    report = _score("pay by upi", "pay by upipay")
    assert report.recognition_eer_before == pytest.approx(1.0)
    assert report.canonical_miss_before == pytest.approx(1.0)


async def test_canonical_output_is_both_recognised_and_canonical() -> None:
    report = _score("check my aadhar status", "check my Aadhaar status")
    assert report.recognition_eer_before == pytest.approx(0.0)
    assert report.canonical_miss_before == pytest.approx(0.0)


async def test_unrecognised_mention_counts_against_both_rates() -> None:
    report = _score("check my aadhaar status", "check my adar status")
    assert report.recognition_eer_before == pytest.approx(1.0)
    assert report.canonical_miss_before == pytest.approx(1.0)


async def test_paired_counts_record_what_the_corrector_fixed_and_broke() -> None:
    transcribed = [
        # wrong -> right: "adhar" is fixable at a permissive threshold
        TranscribedExample(ground_truth_text="check my aadhaar", raw_text="check my adhar"),
        # right before and after: untouched
        TranscribedExample(ground_truth_text="pay by upi", raw_text="pay by UPI"),
    ]
    report = score_transcripts(
        transcribed, _LEXICON, EntityCorrector(_LEXICON, threshold=0.82), split="test"
    )
    assert report.n_entity_mentions == 2
    assert report.recognition_fixed == 1
    assert report.recognition_broken == 0
    assert report.canonical_fixed == 1
    assert report.canonical_broken == 0
