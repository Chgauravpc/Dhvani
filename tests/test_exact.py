"""Exact-lookup canonicalisation (3B-14 / 3B-15)."""

from __future__ import annotations

from dhvani.entity.exact import canonicalise_exact
from dhvani.entity.lexicon import DEFAULT_LEXICON


def test_replaces_a_word_bounded_curated_variant_with_the_canonical_form() -> None:
    result = canonicalise_exact("please link my aadhar card today", DEFAULT_LEXICON)
    assert result.rewrites, "a curated variant should be found"
    assert result.rewrites[0].original.lower().startswith("aadhar")
    assert result.text.startswith("please link my ")
    assert result.text.endswith(" today")
    assert "aadhar" not in result.text.lower().replace(result.rewrites[0].canonical.lower(), "")


def test_leaves_text_without_an_entity_untouched() -> None:
    text = "the company has many helpful youngsters"
    result = canonicalise_exact(text, DEFAULT_LEXICON)
    assert (result.text, result.rewrites) == (text, [])


def test_does_not_rewrite_inside_a_longer_word() -> None:
    for text in ("a company", "pandemic", "helpful"):
        assert canonicalise_exact(text, DEFAULT_LEXICON).rewrites == []


def test_devanagari_variant_is_canonicalised() -> None:
    result = canonicalise_exact("मेरा आधार कार्ड बनवाना है", DEFAULT_LEXICON)
    assert result.rewrites
    assert result.text != "मेरा आधार कार्ड बनवाना है"


def test_is_idempotent() -> None:
    once = canonicalise_exact("my pan card and aadhar card", DEFAULT_LEXICON).text
    assert canonicalise_exact(once, DEFAULT_LEXICON).text == once
