from __future__ import annotations

from dhvani.entity.corrector import EntityCorrector
from dhvani.entity.lexicon import DEFAULT_LEXICON, DEVANAGARI, LATIN, DomainLexicon, LexiconEntry

_LEXICON = DomainLexicon(
    [
        LexiconEntry(
            canonical="Aadhaar",
            variants={
                DEVANAGARI: ("आधार",),
                LATIN: ("aadhaar", "aadhar", "adhaar"),
            },
        ),
        LexiconEntry(canonical="UPI", variants={LATIN: ("upi",)}),
        LexiconEntry(canonical="EPFO", variants={LATIN: ("epfo",)}),
    ]
)


def test_correct_replaces_a_misspelled_entity_mention() -> None:
    corrector = EntityCorrector(_LEXICON, threshold=0.82)
    result = corrector.correct("please check my adhar status")
    assert "Aadhaar" in result.text
    assert len(result.corrections) == 1
    assert result.corrections[0].canonical_entity == "Aadhaar"


def test_correct_leaves_unrelated_text_untouched() -> None:
    corrector = EntityCorrector(_LEXICON, threshold=0.82)
    result = corrector.correct("the weather is nice today")
    assert result.text == "the weather is nice today"
    assert result.corrections == []


def test_correct_preserves_surrounding_text_exactly() -> None:
    corrector = EntityCorrector(_LEXICON, threshold=0.82)
    result = corrector.correct("hello please check my adhar right now thanks")
    assert result.text.startswith("hello please check ")
    assert result.text.endswith(" right now thanks")


def test_correct_reports_span_matching_the_original_text() -> None:
    corrector = EntityCorrector(_LEXICON, threshold=0.82)
    text = "my adhar please"
    result = corrector.correct(text)
    (correction,) = result.corrections
    start, end = correction.span
    assert text[start:end] == correction.original


def test_correct_matches_a_single_word_acronym() -> None:
    corrector = EntityCorrector(_LEXICON, threshold=0.82)
    result = corrector.correct("check my upi balance")
    assert "UPI" in result.text


def test_correct_handles_empty_text() -> None:
    corrector = EntityCorrector(_LEXICON, threshold=0.82)
    result = corrector.correct("")
    assert result.text == ""
    assert result.corrections == []


def test_higher_threshold_declines_a_weak_match() -> None:
    """ "epf" is close to "epfo" but not identical -- a strict threshold
    should decline it while a lenient one accepts it, exercising the
    documented recovery-vs-corruption tradeoff."""
    lenient = EntityCorrector(_LEXICON, threshold=0.5)
    strict = EntityCorrector(_LEXICON, threshold=0.99)

    lenient_result = lenient.correct("my epf balance")
    strict_result = strict.correct("my epf balance")

    assert any(c.canonical_entity == "EPFO" for c in lenient_result.corrections)
    assert strict_result.corrections == []


def test_known_corruption_case_is_pinned() -> None:
    """Documents the greedy-widest-window corruption case from the
    corrector's own docstring, against the real `DEFAULT_LEXICON` (whose
    longest variant, "Pradhan Mantri Awas Yojana", pushes the shared
    `max_window_words` up to 4 words and is what actually produces this):
    "my adhar card" pulls in the unrelated word "my" because the lexicon's
    own "aadhar card" Latin variant scores above threshold against the
    whole three-word span. Pinned so a future change to the matching
    algorithm has to notice it changed this, not silently drift."""
    corrector = EntityCorrector(DEFAULT_LEXICON, threshold=0.82)
    result = corrector.correct("please update my adhar card details")
    assert result.text == "please update Aadhaar details"
    (correction,) = result.corrections
    assert correction.original == "my adhar card"
