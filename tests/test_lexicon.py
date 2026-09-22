from __future__ import annotations

from dhvani.entity.lexicon import (
    DEFAULT_LEXICON,
    DEVANAGARI,
    LATIN,
    TAMIL,
    DomainLexicon,
    LexiconEntry,
)


def test_default_lexicon_has_about_twenty_entries() -> None:
    assert 15 <= len(DEFAULT_LEXICON) <= 25


def test_find_returns_entry_by_canonical_name() -> None:
    entry = DEFAULT_LEXICON.find("Aadhaar")
    assert entry is not None
    assert "aadhaar" in entry.variants[LATIN]


def test_find_returns_none_for_unknown_canonical() -> None:
    assert DEFAULT_LEXICON.find("Not A Real Entity") is None


def test_all_variants_yields_canonical_script_variant_triples() -> None:
    lexicon = DomainLexicon(
        [
            LexiconEntry(
                canonical="Aadhaar",
                variants={DEVANAGARI: ("आधार",), LATIN: ("aadhaar", "aadhar")},
            )
        ]
    )
    triples = list(lexicon.all_variants())
    assert ("Aadhaar", DEVANAGARI, "आधार") in triples
    assert ("Aadhaar", LATIN, "aadhaar") in triples
    assert ("Aadhaar", LATIN, "aadhar") in triples
    assert len(triples) == 3


def test_every_entry_has_at_least_devanagari_and_latin_variants() -> None:
    for entry in DEFAULT_LEXICON:
        assert entry.variants.get(DEVANAGARI), f"{entry.canonical} missing devanagari"
        assert entry.variants.get(LATIN), f"{entry.canonical} missing latin"


def test_tamil_variants_are_non_empty_where_present() -> None:
    for entry in DEFAULT_LEXICON:
        tamil = entry.variants.get(TAMIL)
        if tamil is not None:
            assert all(v.strip() for v in tamil)
