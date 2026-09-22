"""Pinned expected values for `eval.wer` -- phase-2b spec section 7:
normalization choices move WER by several points, so exact values are
asserted, not approximate ones."""

from __future__ import annotations

from dhvani.eval.wer import WerResult, corpus_wer, normalize, word_error_rate


def test_exact_match_is_zero_wer() -> None:
    result = word_error_rate("the cat sat on the mat", "the cat sat on the mat")
    assert result == WerResult(
        wer=0.0, substitutions=0, deletions=0, insertions=0, reference_words=6
    )


def test_single_deletion() -> None:
    result = word_error_rate("the cat sat on the mat", "the cat sat on mat")
    assert result.substitutions == 0
    assert result.deletions == 1
    assert result.insertions == 0
    assert result.reference_words == 6
    assert result.wer == 1 / 6


def test_single_substitution() -> None:
    result = word_error_rate("aadhaar card is required", "adhar card is required")
    assert result.substitutions == 1
    assert result.deletions == 0
    assert result.insertions == 0
    assert result.reference_words == 4
    assert result.wer == 0.25


def test_single_insertion() -> None:
    result = word_error_rate("please submit the form", "please kindly submit the form")
    assert result.substitutions == 0
    assert result.deletions == 0
    assert result.insertions == 1
    assert result.reference_words == 4
    assert result.wer == 0.25


def test_completely_different_is_all_substitutions() -> None:
    result = word_error_rate("a b c", "d e f")
    assert result.substitutions == 3
    assert result.deletions == 0
    assert result.insertions == 0
    assert result.wer == 1.0


def test_empty_reference_and_hypothesis_is_zero() -> None:
    result = word_error_rate("", "")
    assert result.wer == 0.0
    assert result.reference_words == 0


def test_empty_reference_nonempty_hypothesis_is_one() -> None:
    result = word_error_rate("", "hello")
    assert result.wer == 1.0
    assert result.reference_words == 0


def test_normalize_lowercases() -> None:
    assert normalize("HELLO World") == normalize("hello world") == "hello world"


def test_normalize_strips_punctuation() -> None:
    assert normalize("Hello, world!") == "hello world"


def test_normalize_strips_devanagari_danda() -> None:
    assert normalize("नमस्ते।") == "नमस्ते"


def test_normalize_collapses_whitespace() -> None:
    assert normalize("hello    world\n\tagain") == "hello world again"


def test_normalize_nfc_equivalence() -> None:
    precomposed = "café"  # é as a single codepoint
    decomposed = "café"  # e + combining acute accent
    assert precomposed != decomposed  # sanity: genuinely different byte sequences
    assert normalize(precomposed) == normalize(decomposed) == precomposed


def test_word_error_rate_normalizes_before_aligning() -> None:
    result = word_error_rate("The CAT, sat!", "the cat sat")
    assert result.wer == 0.0


def test_corpus_wer_sums_edits_not_averages_per_utterance_rates() -> None:
    pairs = [
        ("please submit the form", "please kindly submit the form"),  # 1 edit / 4 ref words
        ("a b", "c d"),  # 2 edits / 2 ref words
    ]
    naive_average = (0.25 + 1.0) / 2  # what averaging per-utterance WER would give
    result = corpus_wer(pairs)
    assert result.reference_words == 6
    assert result.substitutions == 2
    assert result.insertions == 1
    assert result.deletions == 0
    assert result.wer == 0.5
    assert result.wer != naive_average


def test_corpus_wer_empty_is_zero() -> None:
    result = corpus_wer([])
    assert result.wer == 0.0
    assert result.reference_words == 0
